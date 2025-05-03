#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Transcript Manager for Youtubingest.

Handles fetching, formatting, caching, and language selection for YouTube video transcripts
using the youtube_transcript_api library. Manages concurrency and errors.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from youtube_transcript_api import (YouTubeTranscriptApi, Transcript,
                                    CouldNotRetrieveTranscript, NoTranscriptFound,
                                    TranscriptsDisabled)

# Imports from this package
from config import config
from exceptions import TimeoutExceededError
from utils import LRUCache
from text_processing import _format_timestamp # Import specific formatting function
from logging_config import StructuredLogger

logger = StructuredLogger(__name__)


class TranscriptManager:
    """Manages fetching, formatting, and caching video transcripts.

    Coordinates transcript retrieval using youtube_transcript_api, handles
    language selection based on preferences, formats transcripts into timed blocks,
    caches results and errors, and limits concurrent fetches using a semaphore.
    """

    def __init__(self):
        """Initialize the transcript manager."""
        # Cache for successfully fetched and formatted transcripts: { (video_id, interval): {lang: 'xx', transcript: '...'} }
        self._final_transcript_cache = LRUCache(maxsize=500, ttl_seconds=3600)
        # Cache for known fetch errors (e.g., disabled, not found) to avoid retrying: { video_id: error_type_name }
        self._transcript_fetch_errors = LRUCache(maxsize=200, ttl_seconds=3600)
        # Semaphore to limit concurrent transcript fetches
        self._semaphore = asyncio.Semaphore(config.TRANSCRIPT_SEMAPHORE_LIMIT)
        # Dictionary to track in-progress fetches for the same video ID to avoid duplicates: { video_id: asyncio.Future }
        self._in_progress: Dict[str, asyncio.Future] = {}
        self._in_progress_lock = asyncio.Lock() # Lock to protect access to _in_progress dict

        # Statistics tracking
        self._stats = {
            "cache_hits_result": 0,
            "cache_hits_error": 0,
            "cache_misses": 0,
            "fetch_attempts": 0,
            "fetch_errors_api": 0, # Errors from youtube_transcript_api
            "fetch_errors_internal": 0, # Errors in our processing/formatting
            "fetch_success_unformatted": 0, # Successfully fetched raw data
            "format_success": 0,
            "format_errors": 0,
            "duplicate_requests_avoided": 0,
            "semaphore_waits_timed_out": 0,
            "fetch_timeouts": 0,
            "format_timeouts": 0,
        }
        logger.info(f"TranscriptManager initialized with semaphore limit: {config.TRANSCRIPT_SEMAPHORE_LIMIT}")


    async def get_transcript(self, video_id: str,
                           default_language: Optional[str] = None,
                           default_audio_language: Optional[str] = None,
                           transcript_interval: Optional[int] = None) -> Optional[Dict[str, str]]:
        """Gets the best available transcript for a video ID.

        Handles caching, concurrency limiting, language selection, error handling,
        and formatting based on the specified interval.

        Args:
            video_id: The YouTube video ID (11 characters).
            default_language: Default language code from video metadata (e.g., 'en', 'fr-CA').
            default_audio_language: Default audio language code from video metadata.
            transcript_interval: Seconds to group transcript lines by (e.g., 10, 30, 60).
                                 If 0, returns full transcript without timestamps.
                                 If None, uses config.DEFAULT_TRANSCRIPT_INTERVAL_SECONDS.

        Returns:
            dict: A dictionary {'language': 'xx', 'transcript': '...'} if successful,
                  otherwise None.
        """
        # Compile regex pattern once for better performance
        video_id_pattern = re.compile(r'^[a-zA-Z0-9_-]{11}$')

        if not video_id or not video_id_pattern.match(video_id):
            logger.warning(f"Invalid video ID format provided to get_transcript: {video_id}")
            return None

        # Use default interval if None is passed
        interval = transcript_interval if transcript_interval is not None else config.DEFAULT_TRANSCRIPT_INTERVAL_SECONDS
        # Ensure interval is non-negative
        interval = max(0, interval)

        cache_key = (video_id, interval)
        log_prefix = f"[{video_id}][Intvl:{interval}]" # Prefix for logs related to this request

        logger.debug(f"{log_prefix} Requesting transcript...")

        # 1. Check Result Cache
        cached_result = await self._final_transcript_cache.get(cache_key)
        if cached_result is not None:
            self._stats["cache_hits_result"] += 1
            logger.debug(f"{log_prefix} Transcript result cache hit.")
            return cached_result

        # 2. Check Error Cache (only need video_id for error cache)
        error_cache_key = video_id
        cached_error_type = await self._transcript_fetch_errors.get(error_cache_key)
        if cached_error_type is not None:
            self._stats["cache_hits_error"] += 1
            logger.debug(f"{log_prefix} Transcript error cache hit ({cached_error_type}). No transcript available.")
            return None # Return None as we know fetching failed previously

        # 3. Handle Concurrent Requests for the same video_id
        async with self._in_progress_lock:
            if video_id in self._in_progress:
                # Another task is already fetching for this video_id, wait for its result
                self._stats["duplicate_requests_avoided"] += 1
                logger.debug(f"{log_prefix} Duplicate request detected. Waiting for existing task...")
                try:
                    # Wait for the future associated with the in-progress task
                    result = await asyncio.wait_for(self._in_progress[video_id], timeout=config.NETWORK_TIMEOUT_SECONDS * 1.5)
                    # Re-check cache after waiting, as the other task might have populated it
                    cached_result_after_wait = await self._final_transcript_cache.get(cache_key)
                    if cached_result_after_wait is not None:
                         logger.debug(f"{log_prefix} Found result in cache after waiting for duplicate task.")
                         return cached_result_after_wait
                    else:
                         # The other task might have failed or had a different interval
                         logger.debug(f"{log_prefix} Returning direct result from duplicate task (may be None).")
                         return result
                except asyncio.TimeoutError:
                     logger.warning(f"{log_prefix} Timed out waiting for duplicate request future.")
                     return None # Timeout waiting for the other task
                except Exception as e_dup:
                     logger.warning(f"{log_prefix} Watched duplicate request failed: {e_dup}")
                     return None # The other task failed

            # If no task is in progress, create a future to signal completion
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._in_progress[video_id] = future
            logger.debug(f"{log_prefix} No duplicate request found. Proceeding with fetch.")

        # 4. Acquire Semaphore and Fetch/Format (if cache miss and not duplicate)
        result: Optional[Dict[str, str]] = None
        error_occurred: Optional[Exception] = None
        acquired_semaphore = False
        try:
            self._stats["cache_misses"] += 1
            logger.debug(f"{log_prefix} Attempting to acquire transcript semaphore...")

            # Use a shorter timeout for acquiring the semaphore
            async with asyncio.timeout(config.NETWORK_TIMEOUT_SECONDS / 2): # Shorter timeout for semaphore acquisition
                await self._semaphore.acquire()
                acquired_semaphore = True
                logger.debug(f"{log_prefix} Transcript semaphore acquired.")

            # --- Perform Fetch and Format ---
            self._stats["fetch_attempts"] += 1
            logger.debug(f"{log_prefix} Fetching and formatting transcript...")

            # Use timeout for the combined fetch/format operation
            async with asyncio.timeout(config.TRANSCRIPT_TIMEOUT_SECONDS * 1.5): # Slightly shorter timeout
                 result, error_occurred = await self._fetch_and_format_transcript(
                     video_id,
                     default_language,
                     default_audio_language,
                     interval,
                     log_prefix
                 )

            # --- Update Caches ---
            if error_occurred:
                # Cache specific error types to prevent retries
                if isinstance(error_occurred, (NoTranscriptFound, TranscriptsDisabled)):
                    # Use gather to update both caches concurrently
                    await asyncio.gather(
                        self._transcript_fetch_errors.put(error_cache_key, type(error_occurred).__name__),
                        self._final_transcript_cache.put(cache_key, None)
                    )
                    logger.debug(f"{log_prefix} Cached known transcript unavailability: {type(error_occurred).__name__}")
                else:
                    # For transient errors, don't cache
                    logger.debug(f"{log_prefix} Not caching transient error result: {type(error_occurred).__name__}")
            elif result is not None:
                # Cache the successful result
                await self._final_transcript_cache.put(cache_key, result)
                logger.debug(f"{log_prefix} Caching successful transcript result.")
            else:
                 # Edge case - we don't know if it's permanent or transient
                 logger.warning(f"{log_prefix} Received None result with no error. Not caching to allow retries.")

        except asyncio.TimeoutError:
            if not acquired_semaphore:
                 self._stats["semaphore_waits_timed_out"] += 1
                 logger.warning(f"{log_prefix} Timed out waiting for transcript semaphore.")
                 error_occurred = TimeoutExceededError("Timeout waiting for transcript semaphore")
            else:
                 # Timeout occurred during fetch/format
                 self._stats["fetch_timeouts"] += 1
                 logger.warning(f"{log_prefix} Timed out during transcript fetch/format.")
                 error_occurred = TimeoutExceededError("Timeout during transcript fetch/format")
            result = None # Ensure result is None on timeout
        except Exception as e:
            # Catch any unexpected errors during the process
            self._stats["fetch_errors_internal"] += 1
            logger.error(f"{log_prefix} Unexpected error in get_transcript: {e}", exc_info=True)
            error_occurred = e
            result = None
        finally:
            # --- Release Semaphore ---
            if acquired_semaphore:
                self._semaphore.release()
                logger.debug(f"{log_prefix} Transcript semaphore released.")

            # --- Resolve Future for Concurrent Requests ---
            async with self._in_progress_lock:
                if video_id in self._in_progress:
                    # Get the future we created earlier
                    in_progress_future = self._in_progress.pop(video_id)
                    # Set the result or exception on the future to unblock waiting tasks
                    if not in_progress_future.done():
                        if error_occurred:
                            in_progress_future.set_exception(error_occurred)
                        else:
                            in_progress_future.set_result(result) # Result can be None here
                    logger.debug(f"{log_prefix} Resolved future for concurrent requests.")

        logger.debug(f"{log_prefix} Finished get_transcript. Returning {'dict' if result else 'None'}.")
        return result


    async def _fetch_and_format_transcript(self, video_id: str, default_language: Optional[str],
                                         default_audio_language: Optional[str],
                                         transcript_interval: int, log_prefix: str) -> Tuple[Optional[Dict], Optional[Exception]]:
        """Internal helper: Fetches, selects the best language, and formats the transcript.

        Runs the blocking youtube_transcript_api calls in an executor.

        Args:
            video_id: YouTube video ID.
            default_language: Default language code from video metadata.
            default_audio_language: Default audio language code from video metadata.
            transcript_interval: Seconds to group transcript lines by.
            log_prefix: Logging prefix string.

        Returns:
            tuple: (transcript_dict, error)
                   - transcript_dict: {'language': 'xx', 'transcript': '...'} or None.
                   - error: Exception object if an error occurred, otherwise None.
        """
        raw_transcript_data: Optional[List[Dict[str, Any]]] = None
        selected_language_code: Optional[str] = None
        selected_transcript_obj: Optional[Transcript] = None
        error: Optional[Exception] = None
        loop = asyncio.get_running_loop()

        try:
            # --- 1. List available transcripts (blocking call) ---
            logger.debug(f"{log_prefix} Listing available transcripts...")
            try:
                list_future = loop.run_in_executor(None, lambda: YouTubeTranscriptApi.list_transcripts(video_id))
                transcript_list = await asyncio.wait_for(list_future, timeout=config.TRANSCRIPT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                 self._stats["fetch_timeouts"] += 1
                 raise TimeoutExceededError(f"Timeout listing transcripts for {video_id}")

            available_langs = {t.language_code: t.language for t in transcript_list}
            logger.info(f"{log_prefix} Found {len(available_langs)} available transcript(s): {list(available_langs.keys())}")

            # --- 2. Select the best transcript based on preferences ---
            preferred_languages = self._get_preferred_languages(default_language, default_audio_language)
            logger.debug(f"{log_prefix} Preferred languages ordered: {preferred_languages}")

            selected_transcript_obj = self._select_best_transcript(transcript_list, preferred_languages)

            if not selected_transcript_obj:
                logger.info(f"{log_prefix} No suitable transcript found matching preferences.")
                # Raise NoTranscriptFound so it can be cached appropriately
                raise NoTranscriptFound(video_id, list(available_langs.keys()), preferred_languages)

            selected_language_code = selected_transcript_obj.language_code
            source_desc = f"{selected_transcript_obj.language} ({'manual' if not selected_transcript_obj.is_generated else 'generated'}) [{selected_language_code}]"
            logger.info(f"{log_prefix} Selected transcript: {source_desc}")

            # --- 3. Fetch the selected transcript data (blocking call) ---
            logger.debug(f"{log_prefix} Fetching transcript data for {selected_language_code}...")
            try:
                fetch_future = loop.run_in_executor(None, selected_transcript_obj.fetch)
                raw_transcript_data = await asyncio.wait_for(fetch_future, timeout=config.TRANSCRIPT_TIMEOUT_SECONDS)
                self._stats["fetch_success_unformatted"] += 1
                logger.debug(f"{log_prefix} Fetch successful. {len(raw_transcript_data)} segments.")
            except asyncio.TimeoutError:
                 self._stats["fetch_timeouts"] += 1
                 raise TimeoutExceededError(f"Timeout fetching transcript data for {video_id} ({selected_language_code})")


            # --- 4. Format the transcript (potentially CPU-bound, run in executor) ---
            if raw_transcript_data:
                logger.debug(f"{log_prefix} Formatting transcript with interval {transcript_interval}s...")
                try:
                    format_future = loop.run_in_executor(
                        None, # Use default executor
                        self._format_transcript_by_blocks_sync,
                        raw_transcript_data,
                        selected_language_code,
                        video_id,
                        source_desc,
                        transcript_interval,
                        log_prefix
                    )
                    formatted_text = await asyncio.wait_for(format_future, timeout=config.TRANSCRIPT_TIMEOUT_SECONDS) # Timeout for formatting
                except asyncio.TimeoutError:
                     self._stats["format_timeouts"] += 1
                     raise TimeoutExceededError(f"Timeout formatting transcript for {video_id} ({selected_language_code})")


                if formatted_text is not None:
                    self._stats["format_success"] += 1
                    logger.info(f"{log_prefix} Formatting successful.")
                    return {"language": selected_language_code, "transcript": formatted_text}, None
                else:
                    # Formatting failed, but fetching succeeded
                    self._stats["format_errors"] += 1
                    logger.warning(f"{log_prefix} Formatting failed for transcript {selected_language_code}.")
                    # Return None result, but capture a generic error
                    error = ValueError(f"Transcript formatting failed for {video_id} ({selected_language_code})")
                    return None, error
            else:
                 # Fetch returned empty data?
                 logger.warning(f"{log_prefix} Fetched transcript data was empty for {selected_language_code}.")
                 error = ValueError(f"Fetched transcript data empty for {video_id} ({selected_language_code})")
                 return None, error


        # --- Error Handling ---
        except (NoTranscriptFound, TranscriptsDisabled) as e_known:
            error = e_known
            self._stats["fetch_errors_api"] += 1
            logger.info(f"{log_prefix} Transcript unavailable: {type(e_known).__name__}")
        except CouldNotRetrieveTranscript as e_retrieve:
            error = e_retrieve
            self._stats["fetch_errors_api"] += 1
            lang_info = f" ({selected_language_code})" if selected_language_code else ""
            logger.warning(f"{log_prefix} Could not retrieve transcript{lang_info}: {e_retrieve}")
        except TimeoutExceededError as e_timeout:
             error = e_timeout
             # Stats incremented where timeout occurred
             logger.warning(f"{log_prefix} Operation timed out: {e_timeout}")
        except Exception as e_unexpected:
            error = e_unexpected
            self._stats["fetch_errors_internal"] += 1
            lang_info = f" ({selected_language_code})" if selected_language_code else ""
            logger.error(f"{log_prefix} Unexpected error during transcript fetch/processing{lang_info}: {e_unexpected}", exc_info=True)

        # Return None result and the captured error
        return None, error


    def _get_preferred_languages(self, default_language: Optional[str], default_audio_language: Optional[str]) -> List[str]:
        """Builds the ordered list of preferred languages for transcript selection."""
        prefs = []
        # Add specific languages from metadata first, if available
        if default_audio_language: prefs.append(default_audio_language)
        if default_language: prefs.append(default_language)
        # Add base languages from metadata (e.g., 'en' from 'en-US')
        if default_audio_language: prefs.append(default_audio_language.split('-')[0])
        if default_language: prefs.append(default_language.split('-')[0])
        # Add configured default languages
        prefs.extend(config.TRANSCRIPT_LANGUAGES)
        # Add English as a final fallback if not already included
        if 'en' not in prefs: prefs.append('en')
        # Return unique list while preserving order
        return list(dict.fromkeys(prefs))


    def _select_best_transcript(self, transcript_list: YouTubeTranscriptApi.list_transcripts,
                                preferred_languages: List[str]) -> Optional[Transcript]:
        """Selects the best available transcript based on language preferences and type (manual preferred).

        Args:
            transcript_list: The list of available Transcript objects.
            preferred_languages: Ordered list of preferred language codes (e.g., ['en-US', 'en', 'fr']).

        Returns:
            Transcript: The best matching Transcript object, or None if no suitable transcript found.
        """
        available_transcripts = list(transcript_list) # Convert iterator to list
        if not available_transcripts:
            return None

        # Separate manual and generated transcripts
        manual_transcripts = {t.language_code: t for t in available_transcripts if not t.is_generated}
        generated_transcripts = {t.language_code: t for t in available_transcripts if t.is_generated}

        # --- Search Strategy ---
        # 1. Exact match in preferred languages (manual first, then generated)
        for lang_code in preferred_languages:
            if lang_code in manual_transcripts: return manual_transcripts[lang_code]
            if lang_code in generated_transcripts: return generated_transcripts[lang_code]

        # 2. Base language match in preferred languages (e.g., match 'en' if 'en-US' preferred) (manual first)
        for lang_pref in preferred_languages:
            base_lang_pref = lang_pref.split('-')[0]
            for code, transcript in manual_transcripts.items():
                if code.split('-')[0] == base_lang_pref: return transcript

        # 3. Base language match in preferred languages (generated)
        for lang_pref in preferred_languages:
            base_lang_pref = lang_pref.split('-')[0]
            for code, transcript in generated_transcripts.items():
                if code.split('-')[0] == base_lang_pref: return transcript

        # 4. Fallback: Any manual transcript (prefer English if available)
        if 'en' in manual_transcripts: return manual_transcripts['en']
        if manual_transcripts: return list(manual_transcripts.values())[0] # Return first available manual

        # 5. Fallback: Any generated transcript (prefer English if available)
        if 'en' in generated_transcripts: return generated_transcripts['en']
        if generated_transcripts: return list(generated_transcripts.values())[0] # Return first available generated

        # Should not be reached if transcript_list was not empty
        return None


    def _format_transcript_by_blocks_sync(self, transcript_data: List[Any],
                                        lang_code: str,  # Used in docstring only
                                        video_id: str,   # Used in docstring only
                                        source_desc: str,  # Used in docstring only
                                        transcript_interval: int, log_prefix: str) -> Optional[str]:
        """Synchronously formats raw transcript data into timed blocks or a single block.

        This method is designed to be run in an executor as it can be CPU-intensive.

        Args:
            transcript_data: Raw transcript data list from youtube_transcript_api (list of FetchedTranscriptSnippet objects).
            lang_code: Language code of the transcript.
            video_id: YouTube video ID (for logging).
            source_desc: Description of transcript source (for logging).
            transcript_interval: Seconds to group transcript lines by (0 for no grouping).
            log_prefix: Logging prefix string.

        Returns:
            str: Formatted transcript text, or None if formatting fails or data is empty.
        """
        logger.debug(f"{log_prefix} Formatting {len(transcript_data)} segments, interval={transcript_interval}s")

        if not transcript_data:
            logger.warning(f"{log_prefix} Formatting: Received empty transcript data.")
            return None

        # Ensure interval is valid
        interval = max(0, transcript_interval)

        try:
            # Pre-allocate memory for cleaned segments to avoid resizing
            cleaned_segments = []
            cleaned_segments_append = cleaned_segments.append  # Local reference for faster access

            # Compile regex pattern once for better performance
            whitespace_pattern = re.compile(r'\s+')

            # Clean and structure segments first
            for i, item in enumerate(transcript_data):
                try:
                    # Extract attributes directly - handle different types of input
                    # YouTube API can return either objects with attributes or dictionaries
                    if hasattr(item, 'start') and hasattr(item, 'duration') and hasattr(item, 'text'):
                        # Object with attributes
                        start = float(item.start) if item.start is not None else 0.0
                        duration = float(item.duration) if item.duration is not None else 0.0
                        text = str(item.text).strip() if item.text is not None else ""
                    elif isinstance(item, dict) and 'start' in item and 'duration' in item and 'text' in item:
                        # Dictionary with keys
                        start = float(item['start']) if item['start'] is not None else 0.0
                        duration = float(item['duration']) if item['duration'] is not None else 0.0
                        text = str(item['text']).strip() if item['text'] is not None else ""
                    else:
                        # Invalid format
                        logger.debug(f"{log_prefix} Skipping segment at index {i}: invalid format")
                        continue

                    # Basic text cleaning within segment (normalize whitespace)
                    text = whitespace_pattern.sub(' ', text)

                    if text:  # Only add segments with actual text
                        cleaned_segments_append({'text': text, 'start': start, 'end': start + duration})
                except (AttributeError, ValueError, TypeError, KeyError) as e_seg:
                    # Skip invalid segments
                    logger.debug(f"{log_prefix} Skipping invalid transcript segment at index {i}: {type(item)}. Error: {type(e_seg).__name__} - {e_seg}")
                    continue

            if not cleaned_segments:
                logger.warning(f"{log_prefix} Formatting: No valid text segments found after cleaning.")
                return None

            # --- Format based on interval ---
            if interval == 0:  # No timestamps, join all text
                # Use a list comprehension for better performance
                texts = [segment['text'] for segment in cleaned_segments]
                full_text = " ".join(texts)

                # Final whitespace cleanup
                full_text = whitespace_pattern.sub(' ', full_text).strip()
                logger.debug(f"{log_prefix} Formatting complete (no timestamps). Length: {len(full_text)}")
                return full_text
            else:  # Group into timed blocks
                # Pre-allocate memory for formatted lines
                formatted_lines = []
                formatted_lines_append = formatted_lines.append  # Local reference for faster access

                # Ensure segments are sorted by start time (usually they are, but be safe)
                cleaned_segments.sort(key=lambda s: s['start'])

                current_block_texts = []
                current_block_start_time = None

                # Cache the timestamp formatting function for better performance
                format_timestamp = _format_timestamp

                for segment in cleaned_segments:
                    start_time = segment['start']
                    text = segment['text']

                    if current_block_start_time is None:
                        # Start the first block
                        current_block_start_time = start_time
                        current_block_texts = [text]
                    elif start_time >= current_block_start_time + interval:
                        # Current segment starts a new block, finalize the previous one
                        if current_block_texts:
                            try:
                                timestamp = format_timestamp(current_block_start_time)
                                block_text = " ".join(current_block_texts)
                                formatted_lines_append(f"[{timestamp}] {block_text}")
                            except Exception as e_format:
                                logger.warning(f"{log_prefix} Error formatting timestamp for block: {e_format}")
                                # Use a default timestamp if formatting fails
                                formatted_lines_append(f"[00:00:00] {' '.join(current_block_texts)}")
                        # Start the new block
                        current_block_start_time = start_time
                        current_block_texts = [text]
                    else:
                        # Add text to the current block
                        current_block_texts.append(text)

                # Add the very last block after the loop finishes
                if current_block_texts and current_block_start_time is not None:
                    try:
                        timestamp = format_timestamp(current_block_start_time)
                        block_text = " ".join(current_block_texts)
                        formatted_lines_append(f"[{timestamp}] {block_text}")
                    except Exception as e_format:
                        logger.warning(f"{log_prefix} Error formatting timestamp for final block: {e_format}")
                        # Use a default timestamp if formatting fails
                        formatted_lines_append(f"[00:00:00] {' '.join(current_block_texts)}")

                logger.debug(f"{log_prefix} Formatting complete ({len(formatted_lines)} timed blocks).")
                # Return empty string instead of None if no formatted lines were created
                return "\n".join(formatted_lines) if formatted_lines else ""

        except Exception as e:
            # Catch unexpected errors during formatting
            logger.error(f"{log_prefix} Critical error during transcript formatting: {e}", exc_info=True)
            # Do not increment stats here, handled in the caller (_fetch_and_format_transcript)
            return None  # Indicate formatting failure


    async def get_stats(self) -> Dict[str, Any]:
        """Returns current transcript processing statistics and cache info.

        Returns:
            dict: Statistics including cache hits/misses, fetch counts, errors, etc.
        """
        # Get stats from underlying caches
        transcript_cache_stats = await self._final_transcript_cache.get_stats()
        error_cache_stats = await self._transcript_fetch_errors.get_stats()

        # Combine with internal stats
        stats_copy = self._stats.copy()
        stats_copy["cache_stats_results"] = transcript_cache_stats
        stats_copy["cache_stats_errors"] = error_cache_stats
        stats_copy["semaphore_limit"] = config.TRANSCRIPT_SEMAPHORE_LIMIT
        # Get current semaphore value (approximate waiters)
        # Note: _waiters is internal, might change. A safer way is needed if critical.
        stats_copy["semaphore_current_waiters"] = len(getattr(self._semaphore, '_waiters', [])) if self._semaphore._waiters else 0
        stats_copy["in_progress_requests"] = len(self._in_progress)

        return stats_copy


    async def clear_cache(self) -> int:
        """Clears the transcript results and error caches.

        Returns:
            int: Total number of entries cleared from both caches.
        """
        try:
            cleared_results = await self._final_transcript_cache.clear()
            cleared_errors = await self._transcript_fetch_errors.clear()
            total_cleared = cleared_results + cleared_errors

            # Reset relevant stats counters
            self._stats["cache_hits_result"] = 0
            self._stats["cache_hits_error"] = 0
            self._stats["cache_misses"] = 0
            # Keep fetch/format stats cumulative unless explicitly reset elsewhere

            logger.info(
                f"Transcript caches cleared. Removed {cleared_results} results and {cleared_errors} errors.",
                cleared_results=cleared_results,
                cleared_errors=cleared_errors,
                total_cleared=total_cleared
            )
            return total_cleared
        except Exception as e:
            logger.error(f"Error clearing transcript caches: {e}", exc_info=True)
            return 0
