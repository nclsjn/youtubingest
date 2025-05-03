#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API Routes for the Youtubingest application using FastAPI.

Defines endpoints for ingesting content, health checks, cache clearing,
and serving the frontend interface.
"""

import json
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse

# Import models, exceptions, dependencies, services, config from the package
from config import config
from models import ErrorResponse, IngestRequest, IngestResponse
from services.engine import YoutubeScraperEngine
from services.transcript import TranscriptManager
from services.youtube_api import YouTubeAPIClient
from api.dependencies import (get_api_client, get_scraper_engine,
                           get_transcript_manager)
from logging_config import StructuredLogger
from text_processing import count_tokens

# Import version directly from root __init__.py
from __init__ import __version__ as app_version


logger = StructuredLogger(__name__)

# Create an API router
router = APIRouter()

# Define common error responses for OpenAPI documentation
ERROR_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Invalid input parameters"},
    403: {"model": ErrorResponse, "description": "Forbidden (e.g., Quota Exceeded, API Key Issue)"},
    404: {"model": ErrorResponse, "description": "Resource not found"},
    413: {"model": ErrorResponse, "description": "Request entity too large"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
    503: {"model": ErrorResponse, "description": "Service unavailable (e.g., initialization failed, circuit open)"}
}

# --- Static File Routes ---

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Handles browser requests for the favicon."""
    # Look for favicon in the static directory
    favicon_path = Path(__file__).parent.parent / "static" / "favicon.ico"

    if favicon_path.is_file():
        return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")
    else:
        # Return No Content if favicon doesn't exist
        return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/style.css", include_in_schema=False)
async def get_css():
    """Serves the CSS file."""
    css_path = Path(__file__).parent.parent / "static" / "style.css"

    if css_path.is_file():
        return FileResponse(css_path, media_type="text/css")
    else:
        logger.error(f"CSS file not found at expected location: {css_path}")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

@router.get("/script.js", include_in_schema=False)
async def get_js():
    """Serves the JavaScript file."""
    js_path = Path(__file__).parent.parent / "static" / "script.js"

    if js_path.is_file():
        return FileResponse(js_path, media_type="application/javascript")
    else:
        logger.error(f"JavaScript file not found at expected location: {js_path}")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def get_index_html():
    """Serves the main HTML interface file.

    Returns:
        FileResponse: The index.html file.

    Raises:
        HTTPException: 500 if the index.html file cannot be found.
    """
    # Determine potential paths relative to this file's location
    # Look for index.html file in the static directory
    html_file_path_1 = Path(__file__).parent.parent / "static" / "index.html"

    html_file_path = html_file_path_1

    if not html_file_path.is_file():
        logger.error(f"Interface file 'index.html' not found at expected location: {html_file_path}")
        raise HTTPException(status_code=500, detail="Web interface file not found.")

    logger.debug(f"Serving index.html from: {html_file_path}")
    # Use FileResponse for efficient serving
    response = FileResponse(html_file_path)
    # Set cache control for static assets
    response.headers["Cache-Control"] = f"public, max-age={config.STATIC_CACHE_MAX_AGE}"
    return response

# --- API Endpoints ---

@router.post(
    "/ingest",
    response_model=IngestResponse,
    responses=ERROR_RESPONSES,
    summary="Ingest YouTube URL/Search",
    description="Processes a YouTube URL (video, playlist, channel), handle (@username), or search term to generate a text digest suitable for LLMs. Returns the digest and structured video data."
)
async def ingest_youtube_content(
    request: IngestRequest,
    scraper: YoutubeScraperEngine = Depends(get_scraper_engine) # Inject the main engine
):
    """API endpoint to process a YouTube URL or search query.

    Orchestrates fetching, processing, and digesting content via the Scraper Engine.

    Args:
        request: The validated IngestRequest model containing user input.
        scraper: The injected YoutubeScraperEngine instance.

    Returns:
        IngestResponse: Contains the source name, digest, video count, token count,
                        limit status, processing stats, and detailed video list.

    Raises:
        HTTPException: Propagated from the scraper engine for various error conditions.
    """
    # Sanitize URL for logging
    safe_url = html.escape(request.url[:100]) + ("..." if len(request.url) > 100 else "")
    date_info = []
    if request.start_date: date_info.append(f"start={request.start_date.strftime('%Y-%m-%d')}")
    if request.end_date: date_info.append(f"end={request.end_date.strftime('%Y-%m-%d')}")
    date_str = f" with dates ({', '.join(date_info)})" if date_info else ""

    logger.info(f"Received /ingest request for: {safe_url}{date_str}")

    try:
        # Call the main processing method of the scraper engine
        source_name, videos, stats, high_quota_cost = await scraper.process_url(
            url_or_term=request.url,
            include_transcript=request.include_transcript,
            include_description=request.include_description,
            transcript_interval=request.transcript_interval, # Pass interval, engine uses default if None
            start_date=request.start_date,
            end_date=request.end_date,
        )

        # Handle case where no valid videos were found or processed
        if not videos:
            logger.info(f"No valid videos found or processed for '{safe_url}' (Source: {source_name})")
            date_filter_msg = " or that match your date filters" if request.start_date or request.end_date else ""
            no_videos_message = f"No videos found or processed for '{source_name}'. Check the URL/term{date_filter_msg}, ensure videos meet duration criteria (>{config.MIN_DURATION.total_seconds()}s), and are not live/upcoming."

            # Count tokens in the message
            token_count = count_tokens(no_videos_message)

            return IngestResponse(
                source_name=source_name,
                digest=no_videos_message,
                video_count=0,
                processing_time_ms=stats.get("processing_time_ms"),
                api_call_count=stats.get("api_calls_request"),
                api_quota_used=stats.get("api_quota_used_request"),
                token_count=token_count,  # Add the token count to the response
                videos=[] # Return empty list
            )

        # --- Generate Final Digest ---
        # Combine text from all processed videos with a clear separator
        separator = "\n\n" + "=" * 80 + "\n\n"
        # Use the to_text method which includes metadata, description and transcript (if requested)
        full_digest = separator.join([v.to_text(
            include_description=request.include_description,
            include_transcript=request.include_transcript
        ) for v in videos])

        # Count tokens in the digest
        token_count = count_tokens(full_digest)

        # Log success summary
        logger.info(
            f"Ingestion successful for '{source_name}'. Processed {len(videos)} video(s). Token count: {token_count or 'N/A'}"
        )

        # --- Return Successful Response ---
        # high_quota_cost is now directly provided by the engine

        return IngestResponse(
            source_name=source_name,
            digest=full_digest,
            video_count=len(videos),
            processing_time_ms=stats.get("processing_time_ms"),
            api_call_count=stats.get("api_calls_request"),
            api_quota_used=stats.get("api_quota_used_request"),
            high_quota_cost=high_quota_cost,  # Indicates if this request used high-cost API operations
            token_count=token_count,  # Add the token count to the response
            videos=videos # Include the list of processed Video objects
        )

    # --- Exception Handling for /ingest ---
    # Use the centralized exception handler
    except Exception as e:
        # Log the exception first
        if isinstance(e, HTTPException):
            logger.error(f"HTTPException caught processing /ingest for '{safe_url}': Status={e.status_code}, Detail='{e.detail}'")
        elif hasattr(e, 'error_code'):
            logger.error(f"{type(e).__name__} processing /ingest for '{safe_url}': {e}", exc_info=True)
        else:
            logger.critical(f"Unexpected error processing /ingest for '{safe_url}': {e}", exc_info=True)

        # Use the centralized exception handler
        from exceptions import handle_exception
        raise handle_exception(e)


@router.get(
    "/health",
    summary="Health Check",
    description="Provides the operational status of the Youtubingest service and its components, including basic statistics.",
    response_description="JSON object containing the health status and component readiness."
    # No explicit response_model needed, returns JSON directly
)
async def health_check(
    # Inject dependencies to check their status implicitly
    # These parameters are intentionally not used directly in the function body
    # Their presence ensures the services are running correctly
    # pylint: disable=unused-argument
    api_client: YouTubeAPIClient = Depends(get_api_client),
    transcript_manager: TranscriptManager = Depends(get_transcript_manager),
    scraper: YoutubeScraperEngine = Depends(get_scraper_engine)
):
    """Endpoint to check system health and retrieve operational statistics."""
    logger.debug("Health check endpoint requested.")
    # If dependencies were injected successfully, the core services are considered ready
    status_str = "healthy"
    status_code = status.HTTP_200_OK

    health_data = {
        "status": status_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service_version": app_version,
        "components": {
            "api_client": "ready",
            "transcript_manager": "ready",
            "scraper_engine": "ready"
        }
    }

    # Attempt to get detailed stats if services are ready
    try:
        global_stats = await scraper.get_global_stats()
        health_data["statistics"] = global_stats # Embed the detailed stats
    except Exception as e:
        logger.error(f"Error collecting statistics for /health endpoint: {e}", exc_info=True)
        health_data["statistics"] = {"error": f"Failed to collect detailed stats: {str(e)}"}
        # Optionally degrade status if stats collection fails critically
        # health_data["status"] = "degraded"
        # status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Return JSON response manually for flexibility
    return Response(
        content=json.dumps(health_data, default=str), # Use default=str for non-serializable types like datetime
        status_code=status_code,
        media_type="application/json"
    )


@router.post(
    "/clear-caches",
    summary="Clear All Caches",
    description="Forces the clearing of all internal caches (API responses, transcripts, tokens, etc.). Use with caution.",
    status_code=status.HTTP_200_OK,
    response_description="JSON object confirming cache clearing results."
)
async def clear_all_caches(
    scraper: YoutubeScraperEngine = Depends(get_scraper_engine) # Need engine to trigger clear
):
    """Endpoint to manually trigger the clearing of all application caches."""
    logger.warning("Received request to clear all caches via /clear-caches endpoint.")
    try:
        results = await scraper.clear_caches()
        return {
            "status": "success",
            "message": "All caches cleared successfully.",
            "details": results # Include details returned by the engine's clear method
        }
    except Exception as e:
        logger.error(f"Error occurred during manual cache clearing via endpoint: {e}", exc_info=True)
        # Use the centralized exception handler
        from exceptions import handle_exception
        raise handle_exception(e)


@router.post("/check-input-type", response_model=Dict[str, Any])
async def check_input_type(request: Dict[str, str], api_client: YouTubeAPIClient = Depends(get_api_client)):
    """
    Check if the input is likely to be a search query (high API cost) or another type.

    Args:
        request: Dictionary containing the 'url' field with the input to check
        api_client: YouTubeAPIClient instance

    Returns:
        Dictionary with input type information and cost warning
    """
    if not api_client:
        from exceptions import APIConfigurationError
        raise APIConfigurationError("YouTube API client is not available. Service may be initializing or misconfigured.")

    url_or_term = request.get("url", "").strip()
    if not url_or_term:
        return {
            "is_search": False,
            "input_type": "empty",
            "high_cost_warning": False,
            "message": "Empty input"
        }

    try:
        # Use the extract_identifier method to determine the input type
        identifier_info = await api_client.extract_identifier(url_or_term)

        if not identifier_info:
            return {
                "is_search": False,
                "input_type": "invalid",
                "high_cost_warning": False,
                "message": "Invalid or unrecognized input format"
            }

        _, content_type = identifier_info

        # Check if it's a search query
        is_search = content_type == "search"

        return {
            "is_search": is_search,
            "input_type": content_type,
            "high_cost_warning": is_search,
            "message": "This appears to be a search query, which uses a lot of API quota (100 units per page)" if is_search else f"Input recognized as {content_type}"
        }

    except Exception as e:
        logger.error(f"Error checking input type: {e}", exc_info=True)
        return {
            "is_search": False,
            "input_type": "error",
            "high_cost_warning": False,
            "message": f"Error checking input type: {str(e)}"
        }
