#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FastAPI dependency injection functions for Youtubingest services.

These functions provide instances of the core service classes (API client,
transcript manager, scraper engine) to the API route handlers. They also
handle basic checks like service initialization and quota status.
"""

from typing import Optional

from fastapi import HTTPException, status

# Import service classes
from services.engine import YoutubeScraperEngine
from services.transcript import TranscriptManager
from services.youtube_api import YouTubeAPIClient
# Import exceptions for checks
from logging_config import StructuredLogger

logger = StructuredLogger(__name__)

# --- Global Service Instances ---
# These variables will be populated during the application lifespan startup.
# They act as singletons for the duration of the application run.
api_client: Optional[YouTubeAPIClient] = None
transcript_manager: Optional[TranscriptManager] = None
scraper_engine: Optional[YoutubeScraperEngine] = None


# --- Dependency Injection Functions ---

def get_api_client() -> YouTubeAPIClient:
    """Dependency function to get the initialized YouTubeAPIClient instance.

    Raises:
        HTTPException: 503 Service Unavailable if the client is not initialized.

    Returns:
        The singleton YouTubeAPIClient instance.
    """
    if not api_client:
        logger.critical("Dependency Error: YouTube API Client not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service Initialization Error: YouTube API Client is not available.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE_API_CLIENT"}
        )
    return api_client

def get_transcript_manager() -> TranscriptManager:
    """Dependency function to get the initialized TranscriptManager instance.

    Raises:
        HTTPException: 503 Service Unavailable if the manager is not initialized.

    Returns:
        The singleton TranscriptManager instance.
    """
    if not transcript_manager:
        logger.critical("Dependency Error: Transcript Manager not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service Initialization Error: Transcript Manager is not available.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE_TRANSCRIPT_MANAGER"}
        )
    return transcript_manager

def get_scraper_engine() -> YoutubeScraperEngine:
    """Dependency function to get the initialized YoutubeScraperEngine instance.

    Checks for initialization and also checks the quota status before returning.

    Raises:
        HTTPException: 503 Service Unavailable if the engine is not initialized.
        HTTPException: 403 Forbidden if the engine's quota_reached flag is set.

    Returns:
        The singleton YoutubeScraperEngine instance.
    """
    if not scraper_engine:
        logger.critical("Dependency Error: YouTube Scraper Engine not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service Initialization Error: Scraper Engine is not available.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE_SCRAPER_ENGINE"}
        )
    # Check the engine's quota flag before allowing processing
    # This flag should be updated by the engine itself when a QuotaExceededError occurs.
    if scraper_engine.quota_reached:
        logger.warning("Dependency Check: YouTube API quota likely exceeded. Blocking request.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, # Use 403 to indicate access denied due to quota
            detail="YouTube API quota likely exceeded. Please try again later.",
            headers={"Retry-After": "3600", "X-Error-Code": "QUOTA_EXCEEDED"} # Suggest retrying after 1 hour
        )
    return scraper_engine


