#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main FastAPI application setup for Youtubingest.

Initializes the FastAPI application, sets up lifespan management for services,
registers middleware, mounts static files, and includes API routes.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from logging_config import StructuredLogger

# Import version directly from __init__.py
from __init__ import __version__

# Import components from the package
from api import dependencies, routes
from config import config
from exceptions import APIConfigurationError
from logging_config import setup_logging # Import setup function
from middleware import (RateLimiterMiddleware, SecurityAndMetricsMiddleware)
from services.engine import YoutubeScraperEngine
from services.transcript import TranscriptManager
from services.youtube_api import YouTubeAPIClient

# Initialize logger for this module
logger = StructuredLogger(__name__)

# --- Lifespan Management ---

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.

    Handles initialization of services on startup and cleanup on shutdown.
    Populates the global service instances defined in api.dependencies.
    """
    logger.info("Starting Youtubingest FastAPI application lifespan...")

    # --- Startup ---
    # Setup logging as early as possible during startup
    # Log levels can be further configured via environment in server.py
    # setup_logging() # Logging setup moved to server.py to happen *after* config load

    if not config.API_KEY:
        logger.critical("FATAL ERROR: YOUTUBE_API_KEY is not defined. Services will not be initialized.")
        # Set dependencies to None to indicate failure
        dependencies.api_client = None
        dependencies.transcript_manager = None
        dependencies.scraper_engine = None
    else:
        try:
            # Initialize core services
            logger.info("Initializing services...")
            dependencies.api_client = YouTubeAPIClient(config.API_KEY)
            dependencies.transcript_manager = TranscriptManager()



            # Initialize the main engine, passing dependencies
            dependencies.scraper_engine = YoutubeScraperEngine(
                api_client=dependencies.api_client,
                transcript_manager=dependencies.transcript_manager
            )
            logger.info("Youtubingest services initialized successfully.")

            # Perform an initial API key validation check
            if not dependencies.api_client.validate_api_key_format():
                logger.warning("API key format validation failed (heuristic check). Application might not function correctly.")

        except APIConfigurationError as api_err:
            logger.critical(f"API configuration error during startup: {api_err}")
            # Ensure all dependencies are None on critical failure
            dependencies.api_client = None
            dependencies.transcript_manager = None
            dependencies.scraper_engine = None
        except Exception as e:
            logger.critical(f"Critical unexpected error during service initialization: {e}", exc_info=True)
            dependencies.api_client = None
            dependencies.transcript_manager = None
            dependencies.scraper_engine = None

    # Yield control to the running application
    yield

    # --- Shutdown ---
    logger.info("Shutting down Youtubingest FastAPI application lifespan...")
    if dependencies.scraper_engine:
        try:
            await dependencies.scraper_engine.shutdown()
            logger.info("Scraper engine shut down successfully.")
        except Exception as e:
            logger.error(f"Error during scraper engine shutdown: {e}", exc_info=True)
    else:
        logger.info("Scraper engine was not initialized, skipping shutdown.")

    logger.info("Lifespan cleanup finished.")


# --- FastAPI Application Instantiation ---

app = FastAPI(
    lifespan=lifespan,
    title="Youtubingest API",
    description="API to digest YouTube content (videos, playlists, channels, search) into LLM-friendly text.",
    version=__version__
)

# --- Middleware Registration ---
logger.debug("Registering middleware...")

# CORS Middleware (should generally be first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], # Allow necessary methods
    allow_headers=["*"] # Allow all headers
)
logger.debug(f"CORS Middleware added. Allowed origins: {config.ALLOWED_ORIGINS}")

# Custom Middleware (order can matter)
app.add_middleware(RateLimiterMiddleware) # Apply rate limiting first
app.add_middleware(SecurityAndMetricsMiddleware) # Combined security and metrics middleware

logger.debug("All middleware registered.")

# --- Static Files Mounting ---
# Use the 'static' directory in the same directory as this file
static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    try:
        app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info(f"Static files mounted from directory: {static_dir}")
    except Exception as e:
        logger.error(f"Failed to mount static files directory '{static_dir}': {e}", exc_info=True)
else:
    logger.warning(f"Static files directory not found at expected location: {static_dir}. Static files will not be served.")


# --- API Router Inclusion ---
# Include the routes defined in api/routes.py
app.include_router(routes.router)
logger.info("API routes included.")

# --- Root Endpoint (Optional - can be removed if / serves index.html) ---
# Example: Simple confirmation endpoint at root
# @app.get("/")
# async def read_root():
#     return {"message": "Welcome to Youtubingest API"}

logger.info("FastAPI application setup complete.")
