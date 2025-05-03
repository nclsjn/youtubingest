#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Data API v3 Client for Youtubingest.

Handles interaction with the YouTube API for fetching video, playlist,
channel data, and search results. Includes caching, rate limiting awareness,
and identifier resolution.
"""

import asyncio
import functools
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote_plus

from fastapi import HTTPException
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
import isodate

# Imports from this package
from config import config
from exceptions import (APIConfigurationError, InvalidInputError,
                          QuotaExceededError, RateLimitedError,
                          ResourceNotFoundError, CircuitOpenError)
from models import Video
from utils import (CircuitBreaker, LRUCache, RetryableRequest,
                   SecureApiKeyManager, performance_timer)
from logging_config import StructuredLogger

logger = StructuredLogger(__name__)


class YouTubeAPIClient:
    """Client for interacting with the YouTube Data API v3.

    Provides methods to extract information from URLs, resolve channel identifiers,
    and fetch video details while handling API quotas, errors, and rate limits.
    Uses caching for frequently accessed data like channel ID resolution and
    playlist items.
    """

    # Regular expression patterns for URL matching (more specific)
    URL_PATTERNS = {
        "video": re.compile(r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)(?P<identifier>[a-zA-Z0-9_-]{11})"),
        "playlist": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/(?:playlist|watch)\?.*?list=(?P<identifier>[a-zA-Z0-9_-]+)"),
        "channel_id": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/channel/(?P<identifier>UC[a-zA-Z0-9_-]+)"),
        "channel_handle": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/@(?P<identifier>[a-zA-Z0-9_.-]+)"),
        # Legacy URL types (less common now)
        "channel_custom": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/c/(?P<identifier>[a-zA-Z0-9_.-]+)"),
        "channel_user": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/user/(?P<identifier>[a-zA-Z0-9_.-]+)"),
        "search_query_param": re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/results\?search_query=(?P<query>[^&]+)"),
    }

    # Set of channel types that need resolution to channel IDs
    RESOLVABLE_CHANNEL_TYPES: Set[str] = {"channel_handle", "channel_custom", "channel_user"}

    # API quota costs for different endpoint calls (estimates)
    API_COST = {
        "videos.list": 1,
        "search.list": 100,
        "channels.list": 1,
        "playlists.list": 1,
        "playlistItems.list": 1
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the YouTube API client.

        Args:
            api_key: YouTube Data API key. If None, attempts to load from config/env.

        Raises:
            APIConfigurationError: If the API key is missing or client cannot be built.
        """
        logger.info("Initializing YouTube API Client...")
        self.key_manager = SecureApiKeyManager()
        # Use provided key first, then fallback to manager's retrieval
        self.api_key = api_key if api_key is not None else self.key_manager.get_key()
        self.quota_reached = False # Flag to indicate if quota exceeded error was hit

        if not self.api_key:
            logger.critical("YouTube API key is missing.")
            raise APIConfigurationError("YouTube API Key is not configured.")

        if not self.key_manager.validate_key(self.api_key):
            # Log warning but proceed, validation is heuristic
            logger.warning("API key format validation failed (heuristic check).")

        try:
            # Build the YouTube API service object
            # cache_discovery=False prevents issues with stale discovery documents
            self.youtube: Resource = build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)
            # Initialize circuit breaker for API calls
            self.circuit_breaker = CircuitBreaker(name="youtube_api")
            logger.debug("YouTube API Resource created successfully.")
        except Exception as e:
            logger.critical(f"Error initializing YouTube API client build: {e}", error=str(e), exc_info=True)
            raise APIConfigurationError(f"Could not initialize YouTube API service: {e}") from e

        # Statistics tracking
        self.api_calls_count = 0
        self.api_quota_used = 0
        self.last_request_time_ms = 0.0 # For basic rate limiting delay

        # Initialize caches
        self._playlist_item_cache = LRUCache(
            maxsize=config.PLAYLIST_ITEM_CACHE_SIZE,
            ttl_seconds=config.PLAYLIST_ITEM_CACHE_TTL_SECONDS
        )
        self._channel_resolve_cache = LRUCache(
            maxsize=config.RESOLVE_CACHE_SIZE,
            ttl_seconds=config.RESOLVE_CACHE_TTL_SECONDS
        )

        # Set up cached URL parsing function using instance method
        # Note: Caching instance methods directly can sometimes be tricky if the instance state matters.
        # Here, the parsing logic itself is stateless, so it should be safe.
        self.extract_identifier_sync = functools.lru_cache(maxsize=config.URL_PARSE_CACHE_SIZE)(
            self._extract_identifier_sync_impl
        )
        logger.info("YouTube API Client initialized.")


    async def _wait_for_rate_limit(self) -> float:
        """Introduces a small, random delay between requests if needed.

        Helps prevent hitting API rate limits by ensuring a minimum delay
        with jitter between consecutive calls made by this client instance.

        Returns:
            float: The actual delay applied in milliseconds (0.0 if no delay needed).
        """
        now_ms = time.monotonic() * 1000
        elapsed_ms = now_ms - self.last_request_time_ms

        # Calculate required delay with jitter
        base_delay = random.uniform(config.MIN_DELAY_MS, config.MAX_DELAY_MS)
        jitter_factor = 0.5 # Example jitter factor
        required_delay_ms = base_delay * (1 - jitter_factor + random.random() * jitter_factor * 2)

        actual_delay_ms = 0.0
        if elapsed_ms < required_delay_ms:
            actual_delay_ms = required_delay_ms - elapsed_ms
            await asyncio.sleep(actual_delay_ms / 1000.0)
            self.last_request_time_ms = now_ms + actual_delay_ms
            logger.debug(f"Applied API delay: {actual_delay_ms:.2f}ms")
        else:
            self.last_request_time_ms = now_ms # Update last request time even if no delay applied

        return actual_delay_ms

    async def _execute_api_call(self, api_request: Any, cost: int = 1,
                              timeout: float = config.API_TIMEOUT_SECONDS,
                              retry_policy: Optional[Dict[str, Any]] = None) -> dict:
        """Executes the API call with circuit breaker, retry logic, and timeout.

        Args:
            api_request: The Google API Client Library request object (e.g., youtube.videos().list(...)).
            cost: Estimated API quota cost for this request type.
            timeout: Timeout in seconds for each attempt.
            retry_policy: Optional dictionary overriding default retry settings.

        Returns:
            dict: The parsed JSON response from the API.

        Raises:
            QuotaExceededError: If API quota is exceeded.
            ResourceNotFoundError: If the requested resource is not found (404).
            RateLimitedError: If rate limited by API (429) or circuit breaker.
            APIConfigurationError: For configuration-related issues.
            HTTPException: For other unrecoverable HTTP errors.
            Exception: For unexpected errors during execution.
        """
        await self._wait_for_rate_limit() # Apply basic delay first

        if retry_policy is None:
            retry_policy = RetryableRequest.create_retry_policy("youtube_api")

        if self.quota_reached:
            # If we know quota is reached, fail fast or make one last attempt based on policy
            logger.warning("Quota previously reached, attempting API call with limited/no retries.")
            retry_policy["max_retries"] = min(retry_policy.get("max_retries", config.API_RETRY_ATTEMPTS), 0) # Allow 0 retries if quota hit

        try:
            # Wrap the API execution logic in the circuit breaker and retry mechanism
            response = await self.circuit_breaker(
                RetryableRequest.execute_with_retry,
                # Lambda to execute the request object
                lambda: api_request.execute(),
                # Pass retry parameters
                max_retries=retry_policy.get("max_retries", config.API_RETRY_ATTEMPTS),
                base_delay_ms=retry_policy.get("base_delay_ms", config.API_RETRY_BASE_DELAY_MS),
                timeout_seconds=timeout,
                # Specify exceptions to retry on (defined in RetryableRequest or passed via policy)
                # operation_name can be inferred or passed explicitly
                operation_name=getattr(api_request, '_methodName', 'unknown_api_call')
            )

            # If successful, update stats
            self.api_calls_count += 1
            self.api_quota_used += cost
            # If call succeeded after quota was thought reached, maybe reset flag? Risky.
            # if self.quota_reached: logger.info("API call succeeded after quota flag was set.")
            return response

        except CircuitOpenError as e:
            logger.error(f"Circuit breaker open, preventing API call: {e}", breaker_name="youtube_api", state="open")
            # Map to RateLimitedError or a specific ServiceUnavailable error
            raise RateLimitedError(f"YouTube API temporarily unavailable (Circuit Breaker Open): {e}") from e

        except QuotaExceededError as qe:
            self.quota_reached = True # Set the flag
            logger.critical(f"YouTube API quota exceeded: {qe}", error=str(qe))
            raise qe # Re-raise to be handled by caller

        except ResourceNotFoundError as rnfe:
             logger.warning(f"YouTube resource not found: {rnfe}")
             raise rnfe # Re-raise to be handled by caller

        except HttpError as http_err:
             # Handle other HTTP errors that weren't caught by retry logic (e.g., 400, 401)
             status_code = getattr(http_err, 'resp', {}).get('status', 500)
             logger.error(f"Unhandled HTTP error during API call: {status_code} - {http_err}", status=status_code, error=str(http_err), exc_info=True)
             # Raise as HTTPException for FastAPI to handle
             raise HTTPException(status_code=status_code, detail=f"YouTube API Error: {http_err}") from http_err

        except Exception as e:
            # Catch any other unexpected errors during the process
            logger.error(f"Unexpected error during API call execution: {e}", error=str(e), exc_info=True)
            raise # Re-raise unexpected exceptions


    def _extract_identifier_sync_impl(self, url_or_term: str) -> Optional[Tuple[str, str]]:
        """Synchronously extracts identifier and type from URL/term using regex.

        This is the core implementation wrapped by the LRU cache `extract_identifier_sync`.

        Args:
            url_or_term: The input URL or potential search term.

        Returns:
            tuple: (identifier, type_key) if a known pattern is matched,
                   ("search_term", "search") if it looks like a search term,
                   or None if input is invalid or cannot be classified.
        """
        if not url_or_term or not isinstance(url_or_term, str):
            logger.debug("Invalid input to _extract_identifier_sync_impl: empty or not a string.")
            return None

        cleaned_input = url_or_term.strip()
        if not cleaned_input:
            return None

        # Try matching known URL patterns first
        for pattern_name, pattern in self.URL_PATTERNS.items():
            match = pattern.match(cleaned_input)
            if match:
                identifier_or_query = match.groupdict().get("identifier") or match.groupdict().get("query")
                if identifier_or_query:
                    # Use the pattern name directly as the type key
                    type_key = pattern_name.replace("_query_param", "") # Simplify search type key
                    identifier = unquote_plus(identifier_or_query) # Decode URL encoding
                    logger.debug(f"Matched pattern '{type_key}' with identifier '{identifier[:50]}...'")
                    return identifier, type_key

        # If no pattern matched, determine if it's likely a search term or an unknown URL format
        is_likely_url = cleaned_input.startswith(("http://", "https://", "www.")) or "/" in cleaned_input or "." in cleaned_input
        # Avoid classifying existing file paths as search terms
        looks_like_file_path = False
        try:
            # Basic check, might not cover all edge cases
            looks_like_file_path = Path(cleaned_input).exists() or Path(cleaned_input).is_file()
        except Exception:
             pass # Ignore errors during path check

        if not is_likely_url and not looks_like_file_path:
            # Doesn't look like a URL or file path, treat as search term
            logger.debug(f"Input treated as search term: '{cleaned_input[:50]}...'")
            return cleaned_input, "search"
        elif is_likely_url:
            # Looks like a URL but didn't match known patterns
            logger.warning(f"Unmatched URL-like input treated as search: '{cleaned_input[:100]}...'")
            # Could potentially try more complex parsing here, but for now, treat as search
            return cleaned_input, "search"
        else:
            # Looks like a file path or other unclassifiable input
            logger.warning(f"Input could not be classified (might be file path?): '{cleaned_input[:100]}...'")
            return None


    async def extract_identifier(self, url_or_term: str) -> Optional[Tuple[str, str]]:
        """Asynchronously extracts identifier and type, resolving channel handles/users/custom URLs to channel IDs.

        Uses the cached synchronous extraction first, then performs API calls if needed for resolution.

        Args:
            url_or_term: The input URL or search term.

        Returns:
            tuple: (final_identifier, final_type) where type might be resolved (e.g., "channel"),
                   or None if input is invalid or resolution fails critically.

        Raises:
            QuotaExceededError: If quota is hit during resolution.
            APIConfigurationError: If API is misconfigured.
            RateLimitedError: If rate limited during resolution.
        """
        # Use the cached synchronous extraction
        sync_result = self.extract_identifier_sync(url_or_term)

        if not sync_result:
            logger.warning(f"Could not extract initial identifier for: '{url_or_term[:100]}...'")
            # Decide if unidentifiable input should be treated as search or error
            # Treating as search might be more user-friendly
            # return url_or_term, "search"
            return None # Or return None to indicate failure

        identifier, original_type = sync_result
        logger.debug(f"Initial extraction: id='{identifier[:50]}...', type='{original_type}'")

        # If the type requires resolution (handle, user, custom), resolve it to a channel ID
        if original_type in self.RESOLVABLE_CHANNEL_TYPES:
            logger.info(f"Resolution needed for type '{original_type}': {identifier[:50]}...")
            try:
                # Use performance timer for the resolution part
                with performance_timer(f"resolve_channel_{original_type}"):
                    channel_id = await self._resolve_channel_identifier(identifier, original_type)

                if channel_id:
                    logger.info(f"Resolved '{identifier[:50]}...' ({original_type}) to Channel ID: {channel_id}")
                    return channel_id, "channel" # Return the resolved ID and unified "channel" type
                else:
                    # Resolution failed, but wasn't a critical API error (e.g., not found)
                    logger.warning(f"Failed to resolve '{identifier[:50]}...' ({original_type}) to a channel ID. Treating input as search term.")
                    # Fallback: treat the original input as a search query
                    return url_or_term, "search"

            except (QuotaExceededError, APIConfigurationError, RateLimitedError) as resolve_critical_e:
                # Propagate critical errors that prevent resolution
                logger.error(f"Critical API error during resolution of '{identifier[:50]}...': {resolve_critical_e}")
                raise resolve_critical_e
            except Exception as e:
                # Catch unexpected errors during resolution
                logger.error(f"Unexpected error resolving {identifier[:50]}... ({original_type}): {e}. Treating as search.", exc_info=True)
                return url_or_term, "search"
        else:
            # Type does not require resolution (e.g., video, playlist, channel_id, search)
            return identifier, original_type


    async def _resolve_channel_identifier(self, identifier: str, original_type: str) -> Optional[str]:
        """Resolves a channel handle, username, or custom URL to a channel ID using the API.

        Uses caching (`_channel_resolve_cache`) to avoid repeated API calls.

        Args:
            identifier: The channel identifier (handle, username, or custom URL part).
            original_type: The type of identifier ('channel_handle', 'channel_user', 'channel_custom').

        Returns:
            str: The resolved YouTube Channel ID (UC...), or None if not found or resolution fails.

        Raises:
            QuotaExceededError: If API quota is hit during the call.
            RateLimitedError: If rate limited.
            APIConfigurationError: If API is misconfigured.
        """
        cache_key = (identifier, original_type)
        # Check cache first
        cached_result = await self._channel_resolve_cache.get(cache_key)
        if cached_result is not None: # Cache stores None on failure, so check explicitly
            logger.debug(f"Channel resolution cache hit for {original_type} '{identifier[:50]}...': {'Found' if cached_result else 'Not Found'}")
            return cached_result

        logger.debug(f"Channel resolution cache miss for {original_type} '{identifier[:50]}...'. Querying API.")

        api_param = {}
        resolved_id: Optional[str] = None
        needs_api_call = True

        # Determine API parameter based on the original identifier type
        if original_type == "channel_handle":
            # Ensure handle starts with '@' for the API parameter if it exists
            handle = identifier if identifier.startswith("@") else f"@{identifier}"
            api_param = {"forHandle": handle}
        elif original_type == "channel_user":
            api_param = {"forUsername": identifier}
        elif original_type == "channel_custom":
            # Custom URLs are deprecated. Try resolving as handle first, then username as fallback.
            logger.debug(f"Attempting to resolve deprecated custom URL '/c/{identifier}'...")
            needs_api_call = False # Prevent direct API call for 'channel_custom' type
            try:
                # Try resolving as handle
                resolved_id = await self._resolve_channel_identifier(identifier, "channel_handle")
                if not resolved_id:
                    # If handle fails, try resolving as username
                    logger.debug(f"Custom URL '/c/{identifier}' not resolved as handle, trying as username.")
                    resolved_id = await self._resolve_channel_identifier(identifier, "channel_user")

                if not resolved_id:
                     logger.warning(f"Could not resolve custom URL '/c/{identifier}' as handle or username.")

            except Exception as e_resolve:
                 # Catch errors during this recursive resolution attempt
                 logger.error(f"Error during recursive resolution of custom URL '/c/{identifier}': {e_resolve}", exc_info=True)
                 resolved_id = None # Ensure it's None on error
        else:
            # Should not happen if called correctly, but handle defensively
            logger.error(f"Unsupported resolution type requested: {original_type}")
            needs_api_call = False
            resolved_id = None


        # Perform the API call if parameters were set
        if needs_api_call and api_param:
            try:
                logger.debug(f"Calling channels.list API with params: {api_param}")
                # Request only the ID field
                req = self.youtube.channels().list(part="id", fields="items(id)", **api_param)
                # Execute the call using the wrapped method
                resp = await self._execute_api_call(req, cost=self.API_COST["channels.list"])

                items = resp.get("items")
                if items and isinstance(items, list) and len(items) > 0:
                    resolved_id = items[0].get("id")
                    logger.debug(f"API resolution successful for {api_param}: Found Channel ID {resolved_id}")
                else:
                    logger.debug(f"API resolution for {api_param}: No channel found.")
                    resolved_id = None

            except ResourceNotFoundError:
                # API call succeeded but returned 404
                logger.debug(f"API resolution for {api_param} returned 404 (Not Found).")
                resolved_id = None
            # Let other critical exceptions (Quota, RateLimit, Config) propagate up
            except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
                logger.error(f"API error during channel resolution {api_param}: {e_api}")
                raise e_api
            except Exception as e_unexpected:
                # Catch any other unexpected errors during the API call
                logger.error(f"Unexpected error during API resolution {api_param}: {e_unexpected}", exc_info=True)
                resolved_id = None

        # Cache the result (even if None) before returning
        await self._channel_resolve_cache.put(cache_key, resolved_id)
        logger.debug(f"Cached resolution result for {original_type} '{identifier[:50]}...': {'Found' if resolved_id else 'Not Found'}")

        return resolved_id


    async def get_videos_from_source(self, source_type: str, source_id_or_query: str,
                                   date_filters: Optional[Dict[str, datetime]] = None) -> Tuple[List[str], str, bool]:
        """Fetches a list of video IDs based on the source type (channel, playlist, video, search).

        Args:
            source_type: The type of content source ('channel', 'playlist', 'video', 'search').
            source_id_or_query: The identifier (ID or handle/user) or search query string.
            date_filters: Optional dictionary with 'start_date' and/or 'end_date' (datetime objects).

        Returns:
            tuple: (list_of_video_ids, source_name, high_quota_cost) where:
                   - list_of_video_ids: List of YouTube video IDs
                   - source_name: A descriptive name for the source (e.g., channel title, playlist title, search query)
                   - high_quota_cost: Boolean indicating if this operation used high-cost API calls

        Raises:
            ValueError: If the source type is unsupported or input is invalid.
            QuotaExceededError, RateLimitedError, APIConfigurationError, ResourceNotFoundError: Propagated from API calls.
            HTTPException: For unrecoverable errors during processing.
        """
        logger.info(
            f"Fetching video IDs for type '{source_type}': {source_id_or_query[:100]}...",
            source_type=source_type,
            source_id_or_query=source_id_or_query[:100],
            date_filters=date_filters
        )

        if not source_id_or_query:
            raise InvalidInputError("Source identifier or query cannot be empty.")

        video_ids: List[str] = []
        # Default source name, will be updated if possible
        source_name = f"{source_type.capitalize()}: {source_id_or_query[:50]}"

        try:
            # Use performance timer for the specific fetch operation
            timer_name = f"get_videos_from_{source_type}"
            with performance_timer(timer_name):
                high_quota_cost = False
                if source_type == "channel":
                    video_ids, source_name, high_quota_cost = await self._get_channel_videos(source_id_or_query, date_filters)
                elif source_type == "playlist":
                    video_ids, source_name, high_quota_cost = await self._get_playlist_videos(source_id_or_query, date_filters)
                elif source_type == "video":
                    # For a single video, we just validate it and get its title
                    video_ids, source_name, high_quota_cost = await self._get_single_video(source_id_or_query)
                elif source_type == "search":
                    video_ids, source_name, high_quota_cost = await self._get_search_videos(source_id_or_query, date_filters)
                else:
                    raise ValueError(f"Unsupported source type: {source_type}")

            logger.info(
                f"{len(video_ids)} potential video ID(s) found for source '{source_name}'.",
                video_count=len(video_ids),
                source_name=source_name,
                source_type=source_type
            )

            # Apply global limit on the number of videos processed per request
            if len(video_ids) > config.MAX_VIDEOS_PER_REQUEST:
                logger.warning(
                    f"Limiting to {config.MAX_VIDEOS_PER_REQUEST} video IDs from {len(video_ids)} found for '{source_name}'.",
                    original_count=len(video_ids),
                    limit=config.MAX_VIDEOS_PER_REQUEST,
                    source_name=source_name
                )
                video_ids = video_ids[:config.MAX_VIDEOS_PER_REQUEST]

            return video_ids, source_name, high_quota_cost

        # Catch specific, expected errors and re-raise them
        except (ValueError, InvalidInputError, QuotaExceededError, RateLimitedError, APIConfigurationError, ResourceNotFoundError) as e:
            logger.error(f"Error fetching video IDs for {source_type} '{source_id_or_query[:50]}...': {e}")
            raise e
        # Catch unexpected errors and wrap them in HTTPException
        except Exception as e:
            logger.critical(f"Unexpected error fetching video IDs for {source_type} '{source_id_or_query[:50]}...': {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Server error while fetching video IDs: {type(e).__name__}"
            ) from e


    async def _get_channel_videos(self, channel_id: str, date_filters: Optional[Dict[str, datetime]]) -> Tuple[List[str], str]:
        """Gets video IDs from a channel's uploads playlist.

        Args:
            channel_id: The YouTube Channel ID (must be UC...).
            date_filters: Optional date range filters.

        Returns:
            tuple: (list_of_video_ids, channel_title or channel_id)
        """
        uploads_playlist_id, channel_title = await self._get_channel_uploads_playlist_id(channel_id)
        source_name = channel_title if channel_title else f"Channel ID: {channel_id}"

        if not uploads_playlist_id:
            logger.warning(f"Could not find 'uploads' playlist for channel: {channel_id}. Returning empty list.")
            return [], source_name

        # Use the playlist fetching logic now that we have the uploads playlist ID
        video_ids = [vid_id async for vid_id in self._yield_video_ids_from_playlist(uploads_playlist_id, date_filters)]
        return video_ids, source_name, False  # False indicates not a high-cost operation


    async def _get_playlist_videos(self, playlist_id: str, date_filters: Optional[Dict[str, datetime]]) -> Tuple[List[str], str]:
        """Gets video IDs from a specific playlist.

        Args:
            playlist_id: The YouTube Playlist ID.
            date_filters: Optional date range filters.

        Returns:
            tuple: (list_of_video_ids, playlist_title or playlist_id)
        """
        playlist_title = await self._get_playlist_title(playlist_id)
        source_name = playlist_title if playlist_title else f"Playlist ID: {playlist_id}"

        video_ids = [vid_id async for vid_id in self._yield_video_ids_from_playlist(playlist_id, date_filters)]
        return video_ids, source_name, False  # False indicates not a high-cost operation


    async def _get_single_video(self, video_id: str) -> Tuple[List[str], str, bool]:
        """Validates a single video ID and gets its title.

        Checks if the video exists and meets basic criteria (like duration, not live).

        Args:
            video_id: The YouTube Video ID.

        Returns:
            tuple: ([video_id] if valid, else [], video_title or video_id, high_quota_cost flag)
        """
        is_valid, video_title = await self._check_single_video_validity(video_id)
        source_name = video_title if video_title else f"Video ID: {video_id}"

        if not is_valid:
            logger.info(f"Single video check: Video {video_id} is invalid or does not meet criteria.", video_id=video_id)
            return [], source_name, False # Return empty list if invalid
        else:
            return [video_id], source_name, False  # False indicates not a high-cost operation


    async def _get_search_videos(self, query: str, date_filters: Optional[Dict[str, datetime]],
                               max_results: Optional[int] = None) -> Tuple[List[str], str]:
        """Performs a video search using the YouTube API and retrieves video IDs.

        Args:
            query: The search query string (can include operators like 'before:', 'channel:').
            date_filters: Optional date range filters (applied if not specified in query).
            max_results: Maximum number of video IDs to return. Defaults to config.

        Returns:
            tuple: (list_of_video_ids, descriptive_source_name)

        Raises:
            ValueError: If the search query is invalid after parsing.
            QuotaExceededError, RateLimitedError, etc.: Propagated from API calls.
        """
        max_r = max_results if max_results is not None else config.MAX_SEARCH_RESULTS
        if max_r <= 0:
            return [], f"Search: {query} (0 max results)"

        # Parse the query for operators and get API parameters
        parsed_query, api_params = self._parse_search_query(query)

        # Apply date filters from request if not already present from query operators
        if date_filters:
            if 'publishedAfter' not in api_params and date_filters.get('start_date'):
                api_params['publishedAfter'] = date_filters['start_date'].strftime("%Y-%m-%dT00:00:00Z")
            if 'publishedBefore' not in api_params and date_filters.get('end_date'):
                # Ensure end date includes the whole day
                api_params['publishedBefore'] = date_filters['end_date'].strftime("%Y-%m-%dT23:59:59Z")

        # Ensure there's something to search for
        if not parsed_query and not api_params.get("channelId"): # Allow search within channel without query term
            raise ValueError(f"Invalid or empty search query after parsing: '{query}'")

        video_ids: List[str] = []
        next_page_token: Optional[str] = None
        retrieved_count = 0

        # Create a descriptive name for the search source
        filter_desc = f" ({len(api_params)} filter(s))" if api_params else ""
        # Create clean source name without high cost indicator
        source_name = f"Search '{parsed_query[:40]}...'{filter_desc}" if parsed_query else f"Channel Search{filter_desc}"
        
        # Set high_quota_cost flag to True for search.list operations
        high_quota_cost = True

        logger.info(f"Performing high-cost API search (100 units/page) for: '{parsed_query}' with params: {api_params}", query=parsed_query, params=api_params, quota_cost=self.API_COST["search.list"])

        # Paginate through search results
        while retrieved_count < max_r:
            try:
                # Determine how many results to request in this batch
                batch_size = min(config.BATCH_SIZE, max_r - retrieved_count)
                if batch_size <= 0: break # Should not happen if loop condition is correct

                current_params = {
                    "part": "id", # Only need video IDs
                    "type": "video", # Search only for videos
                    "maxResults": batch_size,
                    "pageToken": next_page_token,
                    "fields": "items(id/videoId),nextPageToken", # Request only necessary fields
                    **api_params, # Include parsed filters
                }
                # Add query term if it exists
                if parsed_query:
                    current_params["q"] = parsed_query

                req = self.youtube.search().list(**current_params)
                resp = await self._execute_api_call(req, cost=self.API_COST["search.list"])

                items = resp.get("items", [])
                new_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

                video_ids.extend(new_ids)
                retrieved_count += len(new_ids)

                logger.debug(f"Search page fetched {len(new_ids)} IDs. Total retrieved: {retrieved_count}/{max_r}.")

                next_page_token = resp.get("nextPageToken")
                if not next_page_token:
                    logger.debug("No more search result pages.")
                    break # Exit loop if no more pages

            except HTTPException as e:
                 # Handle specific errors like invalid search filters
                if e.status_code == 400 and "invalid" in str(e.detail).lower():
                    logger.error(f"Invalid search filter used for query '{query[:50]}...'. Error: {e.detail}")
                    raise ValueError(f"Invalid search filter used in query: '{query}'. Check operator syntax/values.") from e
                else:
                    logger.error(f"HTTP error during search pagination for '{query[:50]}...': {e}")
                    raise # Re-raise other HTTP exceptions
            # Let critical API errors propagate
            except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
                logger.error(f"API error during search pagination for '{query[:50]}...': {e_api}")
                raise e_api
            except Exception as e:
                logger.error(f"Unexpected error during search pagination for '{query[:50]}...' (page token: {next_page_token}): {e}", exc_info=True)
                break # Stop pagination on unexpected errors

        logger.info(f"Search completed for '{query[:50]}...'. Found {len(video_ids)} total video IDs.", query=query[:50], video_count=len(video_ids))
        return video_ids, source_name, high_quota_cost


    async def _get_channel_uploads_playlist_id(self, channel_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Gets the uploads playlist ID and title for a given channel ID.

        Args:
            channel_id: The YouTube Channel ID (must start with UC).

        Returns:
            tuple: (uploads_playlist_id, channel_title) or (None, None) if not found.
        """
        if not channel_id or not channel_id.startswith("UC"):
             logger.error(f"Invalid channel ID format provided for getting uploads playlist: {channel_id}")
             return None, None

        try:
            # Request snippet for title and contentDetails for uploads playlist ID
            fields = "items(snippet/title,contentDetails/relatedPlaylists/uploads)"
            req = self.youtube.channels().list(part="snippet,contentDetails", id=channel_id, fields=fields)
            resp = await self._execute_api_call(req, cost=self.API_COST["channels.list"])

            if not resp.get("items"):
                logger.warning(f"Channel not found via API (ID: {channel_id}) when fetching uploads playlist.")
                # Treat as ResourceNotFoundError semantically
                raise ResourceNotFoundError(f"Channel with ID {channel_id} not found.")

            item = resp["items"][0]
            channel_title = item.get("snippet", {}).get("title")
            playlist_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

            if not playlist_id:
                # This can happen for some channel types or if uploads are hidden
                logger.warning(f"Could not find 'uploads' playlist ID for channel {channel_id} ('{channel_title}'). Channel might have no public videos or uploads disabled.")
                return None, channel_title # Return title even if playlist ID is missing

            logger.debug(f"Found uploads playlist ID '{playlist_id}' for channel '{channel_title}' ({channel_id})")
            return playlist_id, channel_title

        except ResourceNotFoundError:
            # Catch 404 specifically for channels
            logger.warning(f"Channel ID not found via API (404): {channel_id}")
            return None, None # Return None, None if channel itself doesn't exist
        # Let other critical API errors propagate
        except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
             logger.error(f"API error getting uploads playlist ID for channel {channel_id}: {e_api}")
             raise e_api
        except Exception as e:
            logger.error(f"Unexpected error getting uploads playlist ID for channel {channel_id}: {e}", exc_info=True)
            # Return None, None on unexpected errors
            return None, None


    async def _get_playlist_title(self, playlist_id: str) -> Optional[str]:
        """Gets the title of a specific playlist.

        Args:
            playlist_id: The YouTube Playlist ID.

        Returns:
            str: The playlist title, or None if not found or error occurs.
        """
        try:
            # Request only the snippet part for the title
            req = self.youtube.playlists().list(part="snippet", id=playlist_id, fields="items(snippet/title)")
            resp = await self._execute_api_call(req, cost=self.API_COST["playlists.list"])

            items = resp.get("items")
            if items and isinstance(items, list) and len(items) > 0:
                title = items[0].get("snippet", {}).get("title")
                logger.debug(f"Found title for playlist {playlist_id}: '{title}'")
                return title
            else:
                # Playlist exists but has no items or title? Unlikely but possible.
                logger.warning(f"Playlist {playlist_id} found but has no items/title in API response.")
                return None # Treat as not found semantically

        except ResourceNotFoundError:
            logger.warning(f"Playlist ID not found via API (404): {playlist_id}")
            return None
        # Let other critical API errors propagate
        except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
             logger.error(f"API error retrieving playlist title for {playlist_id}: {e_api}")
             raise e_api
        except Exception as e:
            logger.error(f"Unexpected error retrieving playlist title for {playlist_id}: {e}", exc_info=True)
            return None


    async def _check_single_video_validity(self, video_id: str) -> Tuple[bool, Optional[str]]:
        """Checks if a single video exists and meets duration/live criteria using the API.

        Args:
            video_id: The YouTube Video ID.

        Returns:
            tuple: (is_valid, video_title) where is_valid is True if the video exists
                   and meets criteria, False otherwise. video_title is returned if found.
        """
        if not video_id or not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            logger.warning(f"Invalid video ID format provided for validity check: {video_id}")
            return False, None

        try:
            # Request snippet (for title, live status) and contentDetails (for duration)
            fields = "items(id,snippet(title,liveBroadcastContent),contentDetails/duration)"
            req = self.youtube.videos().list(part="snippet,contentDetails", id=video_id, fields=fields)
            resp = await self._execute_api_call(req, cost=self.API_COST["videos.list"])

            if not resp.get("items"):
                logger.warning(f"Video not found via API (ID: {video_id}) during validity check.")
                # Treat as ResourceNotFoundError semantically
                raise ResourceNotFoundError(f"Video with ID {video_id} not found.")

            item = resp["items"][0]
            video_title = item.get("snippet", {}).get("title")
            duration_iso = item.get("contentDetails", {}).get("duration")
            live_status = item.get("snippet", {}).get("liveBroadcastContent", "none") # Default to 'none' if missing

            # Check if duration and live status meet configured criteria
            is_valid_meta = self._is_valid_video_meta(duration_iso, live_status)

            if not is_valid_meta:
                logger.debug(f"Video {video_id} ('{video_title[:30]}...') ignored due to metadata (Duration/Live Status).")
                return False, video_title # Return False but still provide title if found
            else:
                 logger.debug(f"Video {video_id} ('{video_title[:30]}...') passed validity check.")
                 return True, video_title

        except ResourceNotFoundError:
            logger.warning(f"Video ID not found via API (404): {video_id}")
            return False, None
        # Let other critical API errors propagate
        except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
             logger.error(f"API error checking single video validity for {video_id}: {e_api}")
             raise e_api
        except Exception as e:
            logger.error(f"Unexpected error checking single video validity for {video_id}: {e}", exc_info=True)
            return False, None # Treat unexpected errors as invalid


    def _parse_search_query(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """Parses a search query string for YouTube operators (e.g., before:, channel:).

        Separates the query into the main search term and API parameters based on operators.

        Args:
            query: The raw search query string from the user.

        Returns:
            tuple: (parsed_query_term, api_params_dict)
                   - parsed_query_term: The remaining query string after operators are extracted.
                   - api_params_dict: Dictionary of API parameters derived from operators.
        """
        api_params: Dict[str, Any] = {}
        remaining_query_parts: List[str] = []

        # Define supported operators and their mapping to API parameters and formatters
        # None formatter means use the value directly. None API key means handle in query string.
        operator_map: Dict[str, Optional[Tuple[Optional[str], Optional[Callable[[str], Optional[Any]]]]]] = {
            "intitle:": (None, None), # Handled in query string
            "description:": (None, None), # Handled in query string
            "before:": ("publishedBefore", self._format_date_for_api),
            "after:": ("publishedAfter", self._format_date_for_api),
            "channel:": ("channelId", None), # Expects UC... ID
            "duration:": ("videoDuration", lambda v: v.lower() if v.lower() in ["short", "medium", "long", "any"] else None),
            "dimension:": ("videoDimension", lambda v: v.lower() if v.lower() in ["2d", "3d", "any"] else None),
            "definition:": ("videoDefinition", lambda v: v.lower() if v.lower() in ["high", "standard", "any"] else None),
            "caption:": ("videoCaption", lambda v: {"true": "closedCaption", "closedcaption": "closedCaption", "false": "none", "none": "none"}.get(v.lower(), "any")),
            "license:": ("videoLicense", lambda v: {"creativecommon": "creativeCommon", "youtube": "youtube"}.get(v.lower(), "any")),
            "embeddable:": ("videoEmbeddable", lambda v: "true" if v.lower() == "true" else "any"), # API only supports 'true' or 'any'
            "syndicated:": ("videoSyndicated", lambda v: "true" if v.lower() == "true" else "any"), # API only supports 'true' or 'any'
            "type:": ("type", lambda v: v.lower() if v.lower() in ["video", "playlist", "channel", "any"] else None), # Usually forced to 'video' later
            "order:": ("order", lambda v: v.lower() if v.lower() in ["date", "rating", "relevance", "title", "videoCount", "viewCount"] else None)
        }

        # Regex to find operators (word:value or word:"quoted value") and quoted phrases
        # Order matters: Match quoted operator first, then unquoted, then quoted phrase, then word
        pattern = re.compile(
            r'(\w+):"([^"]+)"'  # operator:"quoted value" (Group 1: op, Group 2: val)
            r'|(\w+):(\S+)'      # operator:value (Group 3: op, Group 4: val)
            r'|"([^"]+)"'        # "quoted phrase" (Group 5: val)
            r'|(\S+)'            # regular word (Group 6: val)
        )

        processed_indices = set()
        query_len = len(query)

        for match in pattern.finditer(query):
            start, end = match.span()
            # Skip if this part of the string was already processed as part of a previous match
            if any(i in processed_indices for i in range(start, end)):
                continue

            op_key, value = None, None

            # Check which group matched
            if match.group(1) and match.group(2): # operator:"quoted value"
                op_key = match.group(1).lower() + ":"
                value = match.group(2)
            elif match.group(3) and match.group(4): # operator:value
                op_key = match.group(3).lower() + ":"
                value = match.group(4)
            elif match.group(5): # "quoted phrase"
                remaining_query_parts.append(f'"{match.group(5)}"')
            elif match.group(6): # regular word
                remaining_query_parts.append(match.group(6))

            # Process if it was an operator match
            if op_key and op_key in operator_map:
                mapping = operator_map[op_key]
                if mapping is None: # Handle in query string
                    # Re-add the operator and value (quoted if needed) to the query parts
                    quote = '"' if ' ' in value else ''
                    remaining_query_parts.append(f'{op_key}{quote}{value}{quote}')
                    logger.debug(f"Adding search modifier to query: {op_key}{value}")
                else:
                    api_param_key, formatter = mapping
                    if api_param_key: # Ensure it maps to an API parameter
                        formatted_value = formatter(value) if formatter else value
                        if formatted_value is not None:
                            if api_param_key in api_params:
                                logger.warning(f"Search operator '{op_key}' specified multiple times. Using last value: '{value}'.")
                            api_params[api_param_key] = formatted_value
                            logger.debug(f"Setting search API parameter: {api_param_key}={formatted_value}")
                        else:
                            logger.warning(f"Invalid value '{value}' for search operator '{op_key}' ignored.")
                    else:
                         logger.warning(f"Operator '{op_key}' is defined but has no API parameter mapping.")

            elif op_key:
                # If it looked like an operator but wasn't in our map, treat it as part of the query
                logger.debug(f"Unknown operator '{op_key}', treating as search term: {match.group(0)}")
                remaining_query_parts.append(match.group(0))

            # Mark the matched span as processed
            for i in range(start, end):
                processed_indices.add(i)

        # Combine remaining parts into the final query string
        final_q = " ".join(remaining_query_parts).strip()

        # Default search type to video if not specified by operator
        if "type" not in api_params:
            api_params["type"] = "video"

        logger.debug(f"Parsed search query: q='{final_q}', params={api_params}")
        return final_q, api_params


    def _format_date_for_api(self, date_str: str) -> Optional[str]:
        """Formats various user-friendly date strings into RFC 3339 format (YYYY-MM-DDTHH:MM:SSZ) for the API.

        Handles formats like YYYY-MM-DD, YYYYMMDD, MM/DD/YYYY, DD-MM-YYYY.
        Assumes UTC and sets time to start of day (00:00:00Z) for 'after'
        and end of day (23:59:59Z) for 'before' might be better, but API uses inclusive start/exclusive end?
        Sticking to 00:00:00Z for simplicity as API handles ranges.

        Args:
            date_str: The date string input by the user.

        Returns:
            str: The formatted date string for the API (RFC 3339), or None if parsing fails.
        """
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()
        dt: Optional[datetime] = None

        try:
            # Try common formats directly
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            elif re.match(r'^\d{8}$', date_str): # YYYYMMDD
                dt = datetime.strptime(date_str, "%Y%m%d")
            elif re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str): # MM/DD/YYYY
                dt = datetime.strptime(date_str, "%m/%d/%Y")
            elif re.match(r'^\d{1,2}[-.]\d{1,2}[-.]\d{4}$', date_str): # DD-MM-YYYY or DD.MM.YYYY
                 # Need to handle both separators
                 separator = "-" if "-" in date_str else "."
                 dt = datetime.strptime(date_str, f"%d{separator}%m{separator}%Y")
            # Add more formats if needed (e.g., YYYY/MM/DD)

            if dt:
                # Format as RFC 3339 UTC timestamp (start of the day)
                return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
            else:
                logger.warning(f"Unrecognized date format for API conversion: '{date_str}'")
                return None

        except (ValueError, TypeError) as e:
            logger.warning(f"Error formatting date '{date_str}' for API: {e}")
            return None


    async def _fetch_playlist_page(self, playlist_id: str, page_token: Optional[str]) -> dict:
        """Fetches a single page of playlist items using the API, utilizing caching.

        Args:
            playlist_id: The YouTube Playlist ID.
            page_token: The token for the next page, or None for the first page.

        Returns:
            dict: The API response dictionary for the playlist items list call.

        Raises:
            ResourceNotFoundError: If the playlist is not found (404).
            QuotaExceededError, RateLimitedError, etc.: Propagated from _execute_api_call.
            ValueError: If playlist ID is invalid (though API usually returns 404).
        """
        cache_key = (playlist_id, page_token)
        # Check cache first
        cached_result = await self._playlist_item_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Playlist items cache hit for {playlist_id}, page token: {page_token}")
            return cached_result

        logger.debug(f"Playlist items cache miss for {playlist_id}, page token: {page_token}. Querying API.")

        # Request necessary fields: video ID and publication date
        fields = "items(snippet(publishedAt,resourceId/videoId)),nextPageToken"
        try:
            req = self.youtube.playlistItems().list(
                part="snippet", # Snippet contains publishedAt and resourceId
                playlistId=playlist_id,
                maxResults=config.BATCH_SIZE, # Use configured batch size
                pageToken=page_token,
                fields=fields
            )
            resp = await self._execute_api_call(req, cost=self.API_COST["playlistItems.list"])

            # Cache the successful response before returning
            await self._playlist_item_cache.put(cache_key, resp)
            return resp

        except ResourceNotFoundError:
            # Playlist itself not found
            logger.warning(f"Playlist {playlist_id} not found or inaccessible (404).")
            # Cache the failure? Maybe not for 404s as it might become available later.
            raise # Re-raise the specific error
        # Let other critical errors propagate
        except (QuotaExceededError, RateLimitedError, APIConfigurationError) as e_api:
            logger.error(f"API error fetching playlist page {playlist_id}, token {page_token}: {e_api}")
            raise e_api
        except Exception as e:
            logger.error(f"Unexpected error fetching playlist page {playlist_id}, token {page_token}: {e}", exc_info=True)
            # Wrap unexpected errors
            raise HTTPException(status_code=500, detail="Server error fetching playlist items") from e


    async def _yield_video_ids_from_playlist(self, playlist_id: str,
                                           date_filters: Optional[Dict[str, datetime]] = None) -> AsyncGenerator[str, None]:
        """Yields video IDs from a playlist page by page, applying date filtering.

        Handles pagination automatically.

        Args:
            playlist_id: The YouTube Playlist ID.
            date_filters: Optional dictionary with 'start_date' and/or 'end_date'.

        Yields:
            str: Video IDs from the playlist that match the date criteria.
        """
        next_page_token: Optional[str] = None
        has_more_pages = True
        videos_yielded = 0
        page_count = 0

        start_date = date_filters.get("start_date") if date_filters else None
        end_date = date_filters.get("end_date") if date_filters else None

        # Build filter description for logging
        date_filter_parts = []
        if start_date: date_filter_parts.append(f"after {start_date.date()}")
        if end_date: date_filter_parts.append(f"before {end_date.date()}")
        filter_desc = f" (filtering: {' and '.join(date_filter_parts)})" if date_filter_parts else ""

        logger.debug(f"Starting to yield video IDs from playlist {playlist_id}{filter_desc}", playlist_id=playlist_id)

        # Optimization: Track consecutive pages with no date matches
        consecutive_date_misses = 0
        max_consecutive_misses_to_stop = 3 # Stop if 3 pages in a row have 0 matches

        while has_more_pages and videos_yielded < config.MAX_VIDEOS_PER_REQUEST:
            page_count += 1
            logger.debug(f"Fetching playlist page {page_count} for {playlist_id}, token: {next_page_token}")
            try:
                resp = await self._fetch_playlist_page(playlist_id, next_page_token)
                items = resp.get("items", [])

                if not items:
                    logger.debug(f"No items found on page {page_count} for playlist {playlist_id}.")
                    break # Stop if a page is empty

                ids_yielded_this_page = 0
                for item in items:
                    snippet = item.get("snippet", {})
                    video_id = snippet.get("resourceId", {}).get("videoId")
                    published_at_str = snippet.get("publishedAt")

                    if not video_id or not published_at_str:
                        logger.debug(f"Skipping playlist item with missing ID or date: {item}")
                        continue

                    try:
                        # Parse published date (assuming UTC from API)
                        # Reuse logic from Video model's method for consistency
                        if published_at_str.endswith("Z"):
                            ts = published_at_str[:-1]
                        else:
                            ts = published_at_str
                        if "." in ts: ts = ts.split(".", 1)[0]
                        published_dt_utc = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

                        # Apply date filtering
                        date_ok = (not start_date or published_dt_utc >= start_date) and \
                                  (not end_date or published_dt_utc <= end_date)

                        if date_ok:
                            yield video_id
                            videos_yielded += 1
                            ids_yielded_this_page += 1
                            # Check global limit after each yield
                            if videos_yielded >= config.MAX_VIDEOS_PER_REQUEST:
                                logger.info(f"Reached MAX_VIDEOS_PER_REQUEST ({config.MAX_VIDEOS_PER_REQUEST}) while processing playlist {playlist_id}.")
                                has_more_pages = False
                                break # Stop processing this page and exit outer loop
                        # else: logger.debug(f"Video {video_id} filtered out by date: {published_dt_utc.date()}")

                    except (ValueError, TypeError) as e_date:
                        logger.warning(f"Invalid date format for playlist item {video_id} in {playlist_id}: '{published_at_str}'. Skipping. Error: {e_date}")
                        continue

                # Check optimization condition after processing the page
                if ids_yielded_this_page == 0 and (start_date or end_date):
                    consecutive_date_misses += 1
                    logger.debug(f"Page {page_count} yielded 0 videos matching date filters ({consecutive_date_misses}/{max_consecutive_misses_to_stop} misses).")
                    if consecutive_date_misses >= max_consecutive_misses_to_stop:
                        logger.info(f"Stopping playlist iteration early for {playlist_id} after {consecutive_date_misses} consecutive pages with no date matches.")
                        has_more_pages = False
                else:
                    consecutive_date_misses = 0 # Reset counter if matches found

                if not has_more_pages: break # Exit outer loop if limit reached or optimization triggered

                next_page_token = resp.get("nextPageToken")
                if not next_page_token:
                    has_more_pages = False # Reached the end of the playlist

            # Handle errors during pagination
            except (QuotaExceededError, RateLimitedError, APIConfigurationError, ResourceNotFoundError) as e_api:
                logger.error(f"API error while iterating playlist {playlist_id} on page {page_count}: {e_api}")
                raise e_api # Propagate critical errors
            except Exception as e:
                logger.error(f"Unexpected error iterating playlist {playlist_id} on page {page_count}: {e}", exc_info=True)
                break # Stop iteration on unexpected errors

        logger.debug(f"Finished yielding from playlist {playlist_id}. Total yielded: {videos_yielded}")


    def _is_valid_video_meta(self, duration_iso: Optional[str], live_status: Optional[str]) -> bool:
        """Checks if video duration and live broadcast status meet the configured criteria.

        Args:
            duration_iso: ISO 8601 duration string (e.g., 'PT1M30S').
            live_status: Live broadcast content status ('none', 'live', 'upcoming', 'completed').

        Returns:
            bool: True if the video meets the criteria (not live/upcoming, duration >= min), False otherwise.
        """
        # 1. Check live status: Ignore live or upcoming videos
        # Allow 'none', 'completed', or if the field is missing (None)
        if live_status not in ("none", "completed", None):
            logger.debug(f"Video filtered out: Live status is '{live_status}'.")
            return False

        # 2. Check duration: Must be parseable and meet minimum length
        if not duration_iso:
            logger.debug("Video filtered out: Missing duration information.")
            return False

        try:
            duration_td = isodate.parse_duration(duration_iso)
            # Compare with configured minimum duration
            if duration_td < config.MIN_DURATION:
                logger.debug(f"Video filtered out: Duration {duration_td} is less than minimum {config.MIN_DURATION}.")
                return False
            # Duration is valid
            return True
        except (isodate.ISO8601Error, TypeError, ValueError) as e:
            # Log error but treat as invalid if duration cannot be parsed
            logger.warning(f"Could not parse video duration '{duration_iso}': {e}. Filtering out video.")
            return False


    async def get_video_details_batch(self, video_ids: List[str],
                                    include_content_details: bool = True) -> List[Video]:
        """Fetches detailed information for a list of video IDs in batches using the videos.list endpoint.

        Filters the results based on duration and live broadcast status according to config.

        Args:
            video_ids: A list of YouTube video IDs.
            include_content_details: Whether to fetch contentDetails (contains duration). Default True.

        Returns:
            list: A list of valid Video objects containing the fetched details.
                  Videos that don't meet criteria (duration, live status) are excluded.
        """
        if not video_ids:
            return []

        # Clean and deduplicate IDs first
        cleaned_ids = {vid for vid in video_ids if vid and isinstance(vid, str) and len(vid) == 11}
        unique_ids = list(cleaned_ids)
        if not unique_ids:
            return []

        logger.info(f"Fetching details for {len(unique_ids)} unique video ID(s)...", video_count=len(unique_ids))

        valid_videos_details: List[Video] = []
        processed_ids = set() # Track IDs processed across batches

        # Process IDs in batches
        for i in range(0, len(unique_ids), config.BATCH_SIZE):
            batch_ids = unique_ids[i : i + config.BATCH_SIZE]
            logger.debug(f"Processing video details batch {i // config.BATCH_SIZE + 1} ({len(batch_ids)} IDs starting with {batch_ids[0]})")

            try:
                # Fetch details for the current batch
                batch_results = await self._fetch_video_details_batch(batch_ids, include_content_details)

                # Process items in the successful batch result
                for item in batch_results:
                    video_id = item.get("id")
                    if not video_id or video_id in processed_ids:
                        continue # Skip duplicates or items without ID

                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    duration_iso = content_details.get("duration")
                    live_status = snippet.get("liveBroadcastContent", "none")

                    # Validate metadata (duration, live status)
                    if self._is_valid_video_meta(duration_iso, live_status):
                        # Create Video object if valid
                        video_obj = Video.from_api_response(item)
                        # Estimate quota cost per video in the batch
                        video_obj.api_quota_cost = max(1, self.API_COST["videos.list"] // len(batch_results) if batch_results else 1)
                        valid_videos_details.append(video_obj)
                    else:
                        logger.debug(f"Video {video_id} ('{snippet.get('title', 'N/A')[:30]}...') filtered out after detail fetch due to metadata.")

                    processed_ids.add(video_id)

            # Handle errors for the batch fetch itself
            except (QuotaExceededError, RateLimitedError, APIConfigurationError, ResourceNotFoundError) as e_api:
                 logger.error(f"API error fetching video details batch starting with {batch_ids[0]}: {e_api}")
                 # Decide whether to continue with next batch or stop
                 # For Quota error, definitely stop
                 if isinstance(e_api, QuotaExceededError): raise e_api
                 # For others, maybe continue? For now, re-raise.
                 raise e_api
            except Exception as e:
                 logger.error(f"Unexpected error fetching video details batch starting with {batch_ids[0]}: {e}", exc_info=True)
                 # Continue to next batch on unexpected errors? Or stop? Stop for safety.
                 raise HTTPException(status_code=500, detail="Server error fetching video details") from e


        logger.info(
            f"Retrieved and validated details for {len(valid_videos_details)}/{len(unique_ids)} unique video ID(s).",
            valid_count=len(valid_videos_details),
            total_unique_count=len(unique_ids)
        )
        return valid_videos_details


    async def _fetch_video_details_batch(self, batch_ids: List[str],
                                       include_content_details: bool = True) -> List[dict]:
        """Fetches details for a single batch of video IDs (max 50).

        Internal helper for get_video_details_batch.

        Args:
            batch_ids: List of video IDs (up to BATCH_SIZE).
            include_content_details: Whether to fetch contentDetails part.

        Returns:
            list: List of video item dictionaries from the API response.

        Raises:
            Propagates exceptions from _execute_api_call.
        """
        if not batch_ids:
            return []
        if len(batch_ids) > config.BATCH_SIZE:
             logger.warning(f"Batch size {len(batch_ids)} exceeds max {config.BATCH_SIZE}. Truncating.")
             batch_ids = batch_ids[:config.BATCH_SIZE]

        ids_string = ",".join(batch_ids)
        logger.debug(f"Calling videos.list API for {len(batch_ids)} IDs: {batch_ids[0]}...")

        # Determine parts and fields to request
        parts = ["snippet"]
        fields_list = [
            "items(id",
            "snippet(title,description,channelId,channelTitle,publishedAt,defaultLanguage,defaultAudioLanguage,tags,liveBroadcastContent)"
        ]
        if include_content_details:
            parts.append("contentDetails")
            fields_list.append("contentDetails(duration)")
        fields_list.append(")") # Close items()

        parts_str = ",".join(parts)
        fields_str = ",".join(fields_list)

        try:
            req = self.youtube.videos().list(
                part=parts_str,
                id=ids_string,
                fields=fields_str,
                maxResults=len(batch_ids) # Ensure API doesn't return more than requested
            )
            resp = await self._execute_api_call(req, cost=self.API_COST["videos.list"])
            return resp.get("items", []) # Return the list of video items

        except Exception as e:
            # Log and re-raise errors from the API call execution
            logger.error(f"Failed API call in _fetch_video_details_batch for IDs starting with {batch_ids[0]}: {e}")
            raise e


    async def get_api_stats(self) -> Dict[str, Any]:
        """Returns current API usage statistics and cache states.

        Returns:
            dict: Statistics including API calls, quota used, cache info, circuit breaker state.
        """
        playlist_cache_stats = await self._playlist_item_cache.get_stats()
        channel_cache_stats = await self._channel_resolve_cache.get_stats()
        circuit_breaker_state = self.circuit_breaker.get_stats() # Assuming sync method

        return {
            "api_calls_count": self.api_calls_count,
            "api_quota_used_estimated": self.api_quota_used,
            "quota_reached_flag": self.quota_reached,
            "circuit_breaker": circuit_breaker_state,
            "caches": {
                "playlist_items": playlist_cache_stats,
                "channel_resolution": channel_cache_stats,
                "url_parsing": self.extract_identifier_sync.cache_info()._asdict() if hasattr(self.extract_identifier_sync, 'cache_info') else "N/A",
            },
            "api_key_info": {
                "available": bool(self.api_key),
                "obfuscated": self.key_manager.obfuscate_key(self.api_key)
            }
        }

    def validate_api_key_format(self) -> bool:
        """Performs a basic heuristic check on the API key format.

        Returns:
            bool: True if the key format seems plausible, False otherwise.
        """
        return self.key_manager.validate_key(self.api_key)
