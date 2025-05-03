#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Scraper Engine for Youtubingest.

Orchestrates the process of fetching YouTube content (videos, playlists, channels, search),
retrieving metadata and transcripts, processing text, applying limits, and generating
the final digest.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

# Imports from this package
from config import config
from exceptions import (handle_exception, QuotaExceededError, InvalidInputError,
                        ResourceNotFoundError, APIConfigurationError, CircuitOpenError,
                        RateLimitedError)
from models import Video
# Import text_processing functions when needed in _register_caches
from utils import MemoryMonitor, performance_timer
# Import specific service classes
from services.transcript import TranscriptManager
from services.youtube_api import YouTubeAPIClient
from logging_config import StructuredLogger
from cache_manager import cache_manager

logger = StructuredLogger(__name__)


class YoutubeScraperEngine:
    """Orchestrator for fetching and digesting YouTube content.

    Coordinates the YouTubeAPIClient and TranscriptManager to process user requests,
    handle video fetching, transcript retrieval, text processing, token counting,
    and applying limits to generate a final text digest and structured video data.
    Also manages background tasks like memory monitoring.
    """

    def __init__(self, api_client: YouTubeAPIClient, transcript_manager: TranscriptManager):
        """Initialize the scraper engine.

        Args:
            api_client: An instance of YouTubeAPIClient.
            transcript_manager: An instance of TranscriptManager.
        """
        if not isinstance(api_client, YouTubeAPIClient):
            raise TypeError("api_client must be an instance of YouTubeAPIClient")
        if not isinstance(transcript_manager, TranscriptManager):
             raise TypeError("transcript_manager must be an instance of TranscriptManager")

        self.api_client = api_client
        self.transcript_manager = transcript_manager
        # Reflect the API client's quota status locally for quick checks
        self.quota_reached = self.api_client.quota_reached

        # Global statistics for the engine instance
        self._global_stats = {
            "urls_processed": 0,
            "videos_processed_total": 0,
            "total_processing_time_ms": 0.0,
            "engine_start_time": time.monotonic() # Use monotonic for duration
        }

        self._memory_check_task: Optional[asyncio.Task] = None
        self._shutdown_flag = asyncio.Event() # Event to signal shutdown

        # Register caches with the cache manager
        self._register_caches()

        self._start_memory_monitoring()
        logger.info("YoutubeScraperEngine initialized.")

    def _register_caches(self):
        """Register all caches with the cache manager."""
        # Register API client caches
        if hasattr(self.api_client, '_playlist_item_cache'):
            asyncio.create_task(
                cache_manager.register_lru_cache('playlist_items', self.api_client._playlist_item_cache)
            )

        if hasattr(self.api_client, '_channel_resolve_cache'):
            asyncio.create_task(
                cache_manager.register_lru_cache('channel_resolution', self.api_client._channel_resolve_cache)
            )

        if hasattr(self.api_client, 'extract_identifier_sync') and hasattr(self.api_client.extract_identifier_sync, 'cache_clear'):
            cache_manager.register_func_cache('url_parser', self.api_client.extract_identifier_sync)

        # Register transcript manager cache
        if hasattr(self.transcript_manager, '_transcript_cache'):
            asyncio.create_task(
                cache_manager.register_lru_cache('transcripts', self.transcript_manager._transcript_cache)
            )

        # Register utility function caches
        from text_processing import extract_urls, clean_title, clean_description, format_duration, _format_timestamp

        cache_manager.register_func_cache('extract_urls', extract_urls)
        cache_manager.register_func_cache('clean_title', clean_title)
        cache_manager.register_func_cache('clean_description', clean_description)
        cache_manager.register_func_cache('format_duration', format_duration)
        cache_manager.register_func_cache('_format_timestamp', _format_timestamp)

    def _start_memory_monitoring(self):
        """Start the background memory monitoring task if not already running."""
        if self._memory_check_task and not self._memory_check_task.done():
            logger.debug("Memory monitoring task already running.")
            return

        async def _monitor_memory():
            logger.info("Starting background memory monitoring task.")
            while not self._shutdown_flag.is_set():
                try:
                    # Check memory pressure periodically
                    if MemoryMonitor.check_memory_pressure():
                        # If pressure detected, attempt to clear caches
                        await MemoryMonitor.clear_caches_if_needed()

                    # Wait for the configured interval or until shutdown is signaled
                    await asyncio.wait_for(
                        self._shutdown_flag.wait(),
                        timeout=config.MEMORY_CHECK_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    continue # Timeout means interval passed, continue loop
                except asyncio.CancelledError:
                     logger.info("Memory monitoring task cancelled.")
                     break
                except Exception as e:
                    logger.error(f"Error in memory monitoring task: {e}", exc_info=True)
                    # Avoid tight loop on persistent errors
                    await asyncio.sleep(config.MEMORY_CHECK_INTERVAL_SECONDS * 2)
            logger.info("Memory monitoring task stopped.")

        try:
            # Ensure there's a running event loop
            loop = asyncio.get_running_loop()
            self._memory_check_task = loop.create_task(_monitor_memory())
        except RuntimeError:
            logger.warning("No running event loop found, cannot start memory monitoring task yet.")
            # It might be started later when the loop is running

    async def shutdown(self):
        """Cleanly shutdown the scraper engine and its background tasks."""
        logger.info("Shutting down YoutubeScraperEngine...")
        self._shutdown_flag.set() # Signal background tasks to stop

        # Cancel and await the memory monitoring task
        if self._memory_check_task and not self._memory_check_task.done():
            self._memory_check_task.cancel()
            try:
                await self._memory_check_task
            except asyncio.CancelledError:
                logger.debug("Memory monitoring task successfully cancelled.")
            except Exception as e:
                 logger.error(f"Error during memory monitor task shutdown: {e}")



        logger.info("YoutubeScraperEngine shut down complete.")


    @staticmethod
    def _get_sort_key(video: Video) -> datetime:
        """Provides a sort key (publication date, descending) for videos.

        Uses UTC timezone and handles missing dates by sorting them oldest.

        Args:
            video: The Video object to get the sort key for.

        Returns:
            datetime: The publication date (UTC), or datetime.min (UTC) if unavailable.
        """
        dt = video.get_published_at_datetime()
        # Return the actual datetime or a minimum datetime (with UTC tz) for sorting
        return dt if dt else datetime.min.replace(tzinfo=timezone.utc)


    async def process_url(self, url_or_term: str, include_transcript: bool,
                        include_description: bool,
                        transcript_interval: Optional[int], # Allow None here
                        start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Tuple[str, List[Video],
                                                                   Dict[str, Any], bool]:
        """Main processing pipeline for a given URL or search term.

        Orchestrates fetching IDs, details, transcripts, and generating stats.

        Args:
            url_or_term: The YouTube URL or search term provided by the user.
            include_transcript: Whether to fetch and include transcripts.
            include_description: Whether to include video descriptions in the output.
            transcript_interval: The desired interval for grouping transcript lines (seconds).
                                 0 means no timestamps. None uses default from config.
            start_date: Optional filter for videos published on or after this date (UTC).
            end_date: Optional filter for videos published on or before this date (UTC).

        Returns:
            tuple: (source_name, videos, stats, high_quota_cost)
                   - source_name: Descriptive name of the processed source.
                   - videos: List of processed Video objects included in the digest.
                   - stats: Dictionary containing processing statistics for this request.
                   - high_quota_cost: Boolean indicating if this request used high-cost API operations.

        Raises:
            HTTPException: For various errors like invalid input, API errors, quota exceeded, etc.
                           These are intended to be caught by the FastAPI endpoint handler.
        """
        # Initialize request tracking
        request_context = self._init_request_context(url_or_term, include_transcript,
                                                   include_description, transcript_interval,
                                                   start_date, end_date)

        try:
            # Check quota before starting
            self._check_quota(request_context["request_id"])

            # Identify source type and get video IDs
            source_name, video_ids, _, high_quota_cost = await self._identify_and_get_video_ids(
                url_or_term,
                request_context["request_id"],
                start_date,
                end_date
            )

            # If no videos found, return early
            if not video_ids:
                request_stats = self._get_processing_stats(
                    request_context["start_time_mono"],
                    request_context["request_start_api_calls"],
                    request_context["request_start_quota_used"],
                    request_context["request_id"]
                )
                return source_name, [], request_stats, high_quota_cost

            # Get video details and process transcripts
            videos, transcript_found_count = await self._process_videos_and_transcripts(
                video_ids,
                include_transcript,
                request_context["proc_interval"],
                request_context["request_id"]
            )

            # If no valid videos after filtering, return early
            if not videos:
                request_stats = self._get_processing_stats(
                    request_context["start_time_mono"],
                    request_context["request_start_api_calls"],
                    request_context["request_start_quota_used"],
                    request_context["request_id"]
                )
                return source_name, [], request_stats, high_quota_cost

            # Update stats and finalize
            return self._finalize_processing(
                source_name,
                videos,
                transcript_found_count,
                high_quota_cost,
                request_context
            )

        except Exception as e:
            # Handle all exceptions
            return self._handle_processing_exception(e, request_context)

    def _init_request_context(self, url_or_term: str, include_transcript: bool,
                            include_description: bool, transcript_interval: Optional[int],
                            start_date: Optional[datetime], end_date: Optional[datetime]) -> Dict[str, Any]:
        """Initialize the request context with tracking information.

        Args:
            url_or_term: The YouTube URL or search term.
            include_transcript: Whether to include transcripts.
            include_description: Whether to include descriptions.
            transcript_interval: Interval for transcript timestamps.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            dict: Request context with tracking information.
        """
        start_time_mono = time.monotonic()
        request_id = str(uuid.uuid4())[:8]  # Short unique ID for logging

        # Ensure memory monitoring is running
        if not self._memory_check_task or self._memory_check_task.done():
            logger.warning("Memory monitoring task was not running. Attempting restart.")
            self._start_memory_monitoring()

        # Determine transcript interval
        proc_interval = transcript_interval if transcript_interval is not None else config.DEFAULT_TRANSCRIPT_INTERVAL_SECONDS
        proc_interval = max(0, proc_interval)  # Ensure non-negative

        # Log request start
        date_filter_str = []
        if start_date: date_filter_str.append(f"start={start_date.strftime('%Y-%m-%d')}")
        if end_date: date_filter_str.append(f"end={end_date.strftime('%Y-%m-%d')}")
        date_log = f" (Dates: {', '.join(date_filter_str)})" if date_filter_str else ""

        logger.info(
            f"[REQ-{request_id}] Processing request: '{url_or_term[:100]}...'{date_log}",
            request_id=request_id, url=url_or_term[:100], include_transcript=include_transcript,
            include_description=include_description, interval=proc_interval,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None
        )

        # Update global stats
        self._global_stats["urls_processed"] += 1

        return {
            "start_time_mono": start_time_mono,
            "request_start_api_calls": self.api_client.api_calls_count,
            "request_start_quota_used": self.api_client.api_quota_used,
            "request_id": request_id,
            "proc_interval": proc_interval
        }

    def _check_quota(self, request_id: str) -> None:
        """Check if the API quota has been reached.

        Args:
            request_id: The request ID for logging.

        Raises:
            QuotaExceededError: If the quota has been reached.
        """
        self.quota_reached = self.api_client.quota_reached
        if self.quota_reached:
            logger.warning(f"[REQ-{request_id}] Quota limit likely reached. Aborting request early.")
            raise QuotaExceededError("YouTube API quota likely exceeded based on previous errors.")

    async def _identify_and_get_video_ids(self, url_or_term: str, request_id: str,
                                        start_date: Optional[datetime] = None,
                                        end_date: Optional[datetime] = None) -> Tuple[str, List[str], str, bool]:
        """Identify the source type and get video IDs.

        Args:
            url_or_term: The YouTube URL or search term.
            request_id: The request ID for logging.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            tuple: (source_name, video_ids, content_type, high_quota_cost)

        Raises:
            InvalidInputError: If the URL or term is invalid.
        """
        # Identify source type
        with performance_timer("extract_and_resolve_identifier"):
            identifier_info = await self.api_client.extract_identifier(url_or_term)

        if not identifier_info:
            raise InvalidInputError(f"Invalid or unrecognized URL/term format: '{url_or_term}'")

        identifier, content_type = identifier_info
        logger.info(f"[REQ-{request_id}] Identified type: '{content_type}', ID/Query: '{identifier[:50]}...'")

        # Get video IDs
        date_filters = {"start_date": start_date, "end_date": end_date} if start_date or end_date else None
        with performance_timer("get_videos_from_source"):
            video_ids, source_name, high_quota_cost = await self.api_client.get_videos_from_source(
                content_type,
                identifier,
                date_filters=date_filters
            )

        if not video_ids:
            logger.info(f"[REQ-{request_id}] No video IDs found for {content_type} '{identifier[:50]}...' matching criteria.")

        return source_name, video_ids, content_type, high_quota_cost

    async def _process_videos_and_transcripts(self, video_ids: List[str], include_transcript: bool,
                                           transcript_interval: int, request_id: str) -> Tuple[List[Video], int]:
        """Get video details and process transcripts.

        Args:
            video_ids: List of video IDs to process.
            include_transcript: Whether to include transcripts.
            transcript_interval: Interval for transcript timestamps.
            request_id: The request ID for logging.

        Returns:
            tuple: (videos, transcript_found_count)
        """
        # Get video details
        with performance_timer("get_video_details_batch"):
            videos = await self.api_client.get_video_details_batch(video_ids)

        if not videos:
            logger.info(f"[REQ-{request_id}] No valid video details retrieved (after filtering by duration/live status).")
            return [], 0

        # Sort videos by publication date
        try:
            videos.sort(key=self._get_sort_key, reverse=True)
            logger.debug(f"[REQ-{request_id}] Sorted {len(videos)} videos by publication date (desc).")
        except Exception as sort_e:
            logger.warning(f"[REQ-{request_id}] Error sorting videos: {sort_e}. Proceeding without sorting.")

        # Process transcripts if requested
        transcript_found_count = 0
        if include_transcript:
            logger.debug(f"[REQ-{request_id}] Starting transcript processing for {len(videos)} videos (interval={transcript_interval}s)")
            with performance_timer("process_transcripts_concurrently"):
                videos, transcript_found_count = await self._process_transcripts_concurrently(
                    videos,
                    transcript_interval,
                    request_id
                )
            logger.debug(f"[REQ-{request_id}] Transcript processing complete. Found {transcript_found_count} transcripts.")
        else:
            logger.debug(f"[REQ-{request_id}] Skipping transcript processing as requested.")

        return videos, transcript_found_count

    def _finalize_processing(self, source_name: str, videos: List[Video], transcript_found_count: int,
                           high_quota_cost: bool, request_context: Dict[str, Any]) -> Tuple[str, List[Video], Dict[str, Any], bool]:
        """Finalize processing and return results.

        Args:
            source_name: The source name.
            videos: List of processed videos.
            transcript_found_count: Number of transcripts found.
            high_quota_cost: Whether high-cost API operations were used.
            request_context: The request context.

        Returns:
            tuple: (source_name, videos, stats, high_quota_cost)
        """
        # Update global stats
        self._global_stats["videos_processed_total"] += len(videos)
        logger.info(f"[REQ-{request_context['request_id']}] Final digest includes {len(videos)} video(s) for '{source_name}'.")

        # Calculate stats
        request_stats = self._get_processing_stats(
            request_context["start_time_mono"],
            request_context["request_start_api_calls"],
            request_context["request_start_quota_used"],
            request_context["request_id"]
        )
        request_stats["transcripts_found_request"] = transcript_found_count

        # Trigger memory check/cache clearing
        asyncio.create_task(MemoryMonitor.clear_caches_if_needed())

        logger.debug(f"[REQ-{request_context['request_id']}] Processing complete.")
        return source_name, videos, request_stats, high_quota_cost

    def _handle_processing_exception(self, exception: Exception, request_context: Dict[str, Any]) -> None:
        """Handle exceptions during processing.

        Args:
            exception: The exception that occurred.
            request_context: The request context.

        Raises:
            HTTPException: With appropriate status code and details.
        """
        request_id = request_context["request_id"]

        # Calculate stats up to the point of failure (for logging purposes)
        self._get_processing_stats(
            request_context["start_time_mono"],
            request_context["request_start_api_calls"],
            request_context["request_start_quota_used"],
            request_id
        )

        # Update quota reached flag if needed
        if isinstance(exception, QuotaExceededError):
            self.quota_reached = True
            logger.critical(f"[REQ-{request_id}] QuotaExceededError during processing: {exception}")
        elif isinstance(exception, (InvalidInputError, ValueError)):
            logger.warning(f"[REQ-{request_id}] Invalid input error: {exception}")
        elif isinstance(exception, ResourceNotFoundError):
            logger.warning(f"[REQ-{request_id}] Resource not found: {exception}")
        elif isinstance(exception, APIConfigurationError):
            logger.error(f"[REQ-{request_id}] API configuration error: {exception}")
        elif isinstance(exception, CircuitOpenError):
            logger.error(f"[REQ-{request_id}] CircuitOpenError encountered: {exception}")
        elif isinstance(exception, RateLimitedError):
            logger.error(f"[REQ-{request_id}] RateLimitedError encountered: {exception}")
        elif isinstance(exception, HTTPException):
            logger.error(f"[REQ-{request_id}] HTTPException occurred: Status={exception.status_code}, Detail='{exception.detail}'")
        else:
            # Catch any other unexpected errors
            logger.critical(f"[REQ-{request_id}] Critical unexpected error during process_url: {exception}", exc_info=True)

        # Use the centralized exception handler
        raise handle_exception(exception)


    async def _process_transcripts_concurrently(self, videos: List[Video], transcript_interval: int, request_id: str) -> Tuple[List[Video], int]:
        """Processes transcripts for multiple videos concurrently using TranscriptManager.

        Updates the `transcript` and `video_transcript_language` attributes of the
        Video objects in the input list.

        Args:
            videos: List of Video objects to process.
            transcript_interval: The transcript grouping interval in seconds.
            request_id: The request ID for logging context.

        Returns:
            tuple: (processed_videos_list, found_count)
                   - processed_videos_list: The original list with Video objects updated.
                   - found_count: The number of videos for which a transcript was successfully found and processed.
        """
        if not videos:
            return [], 0

        log_prefix = f"[REQ-{request_id}]"
        logger.info(f"{log_prefix} Starting concurrent transcript processing for {len(videos)} video(s)...")

        # Process videos in batches to avoid creating too many tasks at once
        batch_size = min(10, len(videos))  # Process up to 10 videos at a time
        found_count = 0
        processed_tasks_count = 0

        # Process videos in batches
        for i in range(0, len(videos), batch_size):
            batch = videos[i:i+batch_size]
            logger.debug(f"{log_prefix} Processing transcript batch {i//batch_size + 1}/{(len(videos) + batch_size - 1)//batch_size} ({len(batch)} videos)")

            # Create a list of tasks for fetching transcripts for this batch
            tasks = []
            video_map = {}  # Map task back to video object
            for video in batch:
                task = asyncio.create_task(
                    self.transcript_manager.get_transcript(
                        video_id=video.id,
                        default_language=video.default_language,
                        default_audio_language=video.default_audio_language,
                        transcript_interval=transcript_interval
                    ),
                    name=f"transcript_fetch_{video.id}"  # Name task for easier debugging
                )
                tasks.append(task)
                video_map[task] = video

            # Wait for all tasks in this batch to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results for this batch
            for j, result_or_exc in enumerate(batch_results):
                task = tasks[j]
                video = video_map[task]
                processed_tasks_count += 1

                if isinstance(result_or_exc, Exception):
                    # Log the error but don't stop processing others
                    logger.warning(f"{log_prefix} Failed to process transcript task for video {video.id}: {type(result_or_exc).__name__} - {result_or_exc}")
                    video.transcript = None
                    video.video_transcript_language = None
                elif result_or_exc and isinstance(result_or_exc, dict) and result_or_exc.get("transcript"):
                    # Transcript found and processed successfully
                    video.transcript = result_or_exc
                    video.video_transcript_language = result_or_exc.get("language")
                    found_count += 1
                    logger.debug(f"{log_prefix} Successfully processed transcript for video {video.id} ({video.video_transcript_language})")
                else:
                    # Task completed but returned None (e.g., no transcript found, formatting failed)
                    logger.debug(f"{log_prefix} No transcript data returned for video {video.id}.")
                    video.transcript = None
                    video.video_transcript_language = None

        logger.info(f"{log_prefix} Transcript processing finished. Found/processed {found_count}/{processed_tasks_count} transcripts.")
        # Return the original list, which has been modified in place
        return videos, found_count





    def _get_processing_stats(self, start_time_mono: float, start_api_calls: int,
                           start_quota_used: int, request_id: str = "") -> Dict[str, Any]:
        """Calculate and return processing statistics for a single request.

        Args:
            start_time_mono: The monotonic start time of the request processing.
            start_api_calls: API call count at the start of the request.
            start_quota_used: Estimated quota used at the start of the request.
            request_id: The unique ID for this request (for logging).

        Returns:
            dict: A dictionary containing processing time, API calls/quota used for the request, and memory usage.
        """
        end_time_mono = time.monotonic()
        processing_time_ms = (end_time_mono - start_time_mono) * 1000
        # Update global processing time stat
        self._global_stats["total_processing_time_ms"] += processing_time_ms

        # Calculate usage for this specific request
        request_api_calls = self.api_client.api_calls_count - start_api_calls
        request_quota_used = self.api_client.api_quota_used - start_quota_used

        stats = {
            "processing_time_ms": round(processing_time_ms, 2),
            "api_calls_request": request_api_calls,
            "api_quota_used_request": request_quota_used,
            # Get current memory usage at the end of the request
            "memory_mb_process": round(MemoryMonitor.get_process_memory_mb(), 2),
            "memory_percent_system": round(MemoryMonitor.get_memory_percent(), 1) if MemoryMonitor._psutil_available else None,
            "request_id": request_id # Include request ID in stats
        }

        log_prefix = f"[REQ-{request_id}] " if request_id else ""
        logger.debug(
            f"{log_prefix}Request stats calculated: Time={stats['processing_time_ms']:.2f}ms, "
            f"API Calls={stats['api_calls_request']}, Quota Used={stats['api_quota_used_request']}, "
            f"Mem(Proc)={stats['memory_mb_process']}MB",
            extra={"data": stats} # Add stats to structured log
        )
        return stats


    async def get_global_stats(self) -> Dict[str, Any]:
        """Get global operational statistics for the scraper engine instance.

        Returns:
            dict: A dictionary containing global stats like total requests, uptime, cache info, etc.
        """
        uptime = time.monotonic() - self._global_stats["engine_start_time"]
        total_urls = self._global_stats["urls_processed"]

        # Gather stats from components
        api_stats = await self.api_client.get_api_stats()
        tm_stats = await self.transcript_manager.get_stats()
        memory_stats = MemoryMonitor.get_full_memory_stats() # Get detailed memory stats

        stats = {
            "engine_uptime_seconds": round(uptime, 1),
            "total_requests_processed": total_urls,
            "total_videos_processed": self._global_stats["videos_processed_total"],
            "avg_processing_time_ms": round(self._global_stats["total_processing_time_ms"] / max(1, total_urls), 2) if total_urls > 0 else 0.0,
            "requests_per_minute": round(total_urls * 60 / max(1, uptime), 2),
            "quota_reached_flag": self.quota_reached or self.api_client.quota_reached,
            "api_client_stats": api_stats,
            "transcript_manager_stats": tm_stats,
            "memory_stats": memory_stats,
        }

        # Trigger a memory check when stats are requested
        if MemoryMonitor.check_memory_pressure(force_check=True):
            await MemoryMonitor.clear_caches_if_needed()

        return stats


    async def clear_caches(self) -> Dict[str, Any]:
        """Force clear all known caches within the engine and its components.

        Returns:
            dict: Results indicating which caches were cleared and how many items (if applicable).
        """
        logger.warning("Force clearing all caches...")

        # Use the centralized cache manager to clear all caches
        try:
            results = await cache_manager.clear_all_caches()

            # Run garbage collection
            try:
                import gc
                gc.collect()
                results["garbage_collection"] = "triggered"
            except Exception as e:
                logger.warning(f"Garbage collection trigger failed: {e}")
                results["garbage_collection"] = "failed"

            logger.info(f"Cache clearing process completed. Results: {results}")
            return results

        except Exception as e:
            logger.error(f"Error clearing caches: {e}", exc_info=True)
            return {"error": str(e)}
