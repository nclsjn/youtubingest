#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Uvicorn server entry point for the Youtubingest application.

Handles environment loading (.env), final logging configuration based on environment,
and starts the Uvicorn server process.
"""

import logging
import os
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

# Import the FastAPI app instance from main
from main import app
# Import config components and logging setup
from config import config
from logging_config import setup_logging

# Function to open browser after a short delay
def open_browser(host, port, delay=1.5):
    """
    Opens a web browser pointing to the application after a short delay.

    Args:
        host: The hostname where the server is running
        port: The port number where the server is running
        delay: Delay in seconds before opening the browser
    """
    def _open_browser():
        time.sleep(delay)  # Give the server a moment to start
        url = f"http://{host}:{port}"
        logging.info(f"Opening browser at {url}")
        webbrowser.open(url)

    browser_thread = threading.Thread(target=_open_browser)
    browser_thread.daemon = True  # Thread will exit when main thread exits
    browser_thread.start()

# --- Main Execution Block ---

if __name__ == "__main__":

    # 1. Load Environment Variables from .env file (if it exists)
    try:
        from dotenv import load_dotenv
        # Look for .env in the current directory or parent directories
        env_path = Path(".") / ".env"
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path, override=True) # override=True allows env vars to take precedence
            print(f"Loaded environment variables from: {env_path.resolve()}")
        else:
            print(".env file not found, using system environment variables.")
    except ImportError:
        print("python-dotenv not installed, skipping .env file loading.")
    except Exception as e:
        print(f"Error loading .env file: {e}")


    # 2. Re-initialize Configuration AFTER loading .env
    # This ensures environment variables override defaults defined in Config
    try:
        # Reload configuration from environment variables
        config.load_from_env()
        print("Configuration loaded from environment variables.")
    except Exception as e:
        print(f"Error loading configuration from environment: {e}. Using default config.")


    # 3. Setup Logging based on final configuration
    # Determine log levels from environment or config defaults
    log_level_console_str = os.environ.get("LOG_LEVEL_CONSOLE", "INFO").upper()
    log_level_file_str = os.environ.get("LOG_LEVEL_FILE", "DEBUG").upper()
    log_structured_str = os.environ.get("LOG_STRUCTURED", "true").lower()

    log_level_console = getattr(logging, log_level_console_str, logging.INFO)
    log_level_file = getattr(logging, log_level_file_str, logging.DEBUG)
    log_structured = log_structured_str in ("true", "1", "yes")

    # Call the setup function with potentially overridden levels
    setup_logging(
        log_level_console=log_level_console,
        log_level_file=log_level_file,
        structured=log_structured
    )
    # Logger is now configured


    # 4. Check for Essential Configuration (e.g., API Key)
    # Access the potentially re-initialized config object
    final_config = config # Use the (potentially re-initialized) config instance
    if not final_config.API_KEY:
        # Use logging now that it's configured
        logging.warning("=" * 80)
        logging.warning(" WARNING: YOUTUBE_API_KEY is not defined.")
        logging.warning(" Please define it in a .env file or as an environment variable.")
        logging.warning(" The application will start, but API calls will likely fail.")
        logging.warning("=" * 80)


    # 5. Get Uvicorn Server Parameters from Environment/Defaults
    run_host = os.environ.get("HOST", "127.0.0.1")
    try:
        run_port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        logging.warning(f"Invalid PORT environment variable '{os.environ.get('PORT')}', using default 8000.")
        run_port = 8000
    try:
        # Default to 1 worker unless specified, as multiple workers might complicate
        # global state management if not designed carefully (e.g., shared caches).
        run_workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
        if run_workers > 1:
             logging.warning(f"Running with {run_workers} workers. Ensure application state management is compatible.")
    except ValueError:
        logging.warning(f"Invalid WEB_CONCURRENCY environment variable '{os.environ.get('WEB_CONCURRENCY')}', using default 1.")
        run_workers = 1

    # Reload should only be enabled for development
    debug_mode = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
    run_reload = debug_mode
    # Set Uvicorn's log level based on debug mode or specific env var
    uvicorn_log_level = os.environ.get("UVICORN_LOG_LEVEL", "debug" if debug_mode else "info").lower()


    # 6. Check if auto-open browser is enabled (default to True)
    auto_open_browser = os.environ.get("AUTO_OPEN_BROWSER", "true").lower() in ("true", "1", "yes")

    # 7. Start the Uvicorn Server
    logging.info(f"Starting Uvicorn server on http://{run_host}:{run_port}")
    logging.info(f"Debug mode: {debug_mode}, Workers: {run_workers}, Reload: {run_reload}, Uvicorn Log Level: {uvicorn_log_level}")
    logging.info(f"Auto-open browser: {auto_open_browser}")

    # Launch browser in a separate thread if enabled
    if auto_open_browser:
        open_browser(run_host, run_port)

    uvicorn.run(
        # Use the string format "module:app_instance" for Uvicorn
        "main:app",
        host=run_host,
        port=run_port,
        reload=run_reload, # Enable auto-reload if debug_mode is True
        workers=run_workers if not run_reload else 1, # Uvicorn reload mode works best with 1 worker
        log_level=uvicorn_log_level,
        # access_log=debug_mode # Enable/disable Uvicorn access logs based on debug mode
        # Consider using uvicorn.config.LOGGING_CONFIG for more control if needed
    )
