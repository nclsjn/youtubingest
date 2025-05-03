# Development Guide

This document provides information for developers who want to contribute to the Youtubingest project.

## Development Environment Setup

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- YouTube API key (obtained from the [Google Cloud Console](https://console.cloud.google.com/))

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/youtubingest.git
   cd youtubingest
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Windows:
     ```bash
     venv\Scripts\activate
     ```
   - Linux/macOS:
     ```bash
     source venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create a `.env` file at the root of the project with your YouTube API key:
   ```
   YOUTUBE_API_KEY=your_youtube_api_key
   ```

### Running in Development Mode

To run the application in development mode:

```bash
python server.py
```

The application will be accessible at `http://localhost:8000`.

## Project Structure

```
youtubingest/
├── api/                  # API route definitions
│   ├── dependencies.py   # Injectable dependencies
│   └── routes.py         # API endpoints
├── docs/                 # Documentation
├── services/             # Business services
│   ├── engine.py         # Main engine
│   ├── transcript.py     # Transcript management
│   └── youtube_api.py    # YouTube API client
├── static/               # Static files
├── tests/                # Unit and integration tests
├── cache_manager.py      # Cache manager
├── config.py             # Configuration
├── exceptions.py         # Exception handling
├── logging_config.py     # Logging configuration
├── main.py               # FastAPI application
├── models.py             # Data models
├── server.py             # Server entry point
├── text_processing.py    # Text processing
└── utils.py              # Utilities
```

## Coding Conventions

### Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code style
- Use descriptive variable and function names
- Limit line length to 100 characters
- Use docstrings to document classes and functions

### Docstrings

Use the Google format for docstrings:

```python
def example_function(param1, param2):
    """Function description.

    Args:
        param1: Description of the first parameter.
        param2: Description of the second parameter.

    Returns:
        Description of the return value.

    Raises:
        ExceptionType: Description of when the exception is raised.
    """
    # Function body
```

### Comments

- Code comments should be in English
- Use comments to explain the "why", not the "what"
- Avoid redundant comments that simply repeat the code

## Testing

### Running Tests

To run all tests:

```bash
python -m unittest discover
```

To run a specific test:

```bash
python -m unittest tests.test_module
```

### Writing Tests

- Write unit tests for each new feature
- Use `unittest.IsolatedAsyncioTestCase` for asynchronous tests
- Use mocks to isolate external components
- Aim for at least 80% code coverage

## Dependency Management

- Add new dependencies to `requirements.txt`
- Use specific versions for dependencies (e.g., `fastapi==0.68.0`)
- Minimize the number of external dependencies

## Contribution Process

1. Create a branch for your feature or bug fix
2. Write tests for your code
3. Ensure all tests pass
4. Submit a pull request with a detailed description of the changes

## Best Practices

### Performance

- Use caching for expensive operations
- Limit YouTube API calls to save quota
- Use asynchronous operations for I/O operations
- Monitor memory usage

### Security

- Never store API keys or secrets in the code
- Validate all user input
- Use rate limits to prevent abuse
- Follow OWASP best practices

### Logging

- Use the logger configured in `logging_config.py`
- Include contextual information in logs
- Use the appropriate log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Avoid logging sensitive information

## Deployment

### Production Preparation

1. Set appropriate environment variables
2. Use a WSGI/ASGI server like Gunicorn or Uvicorn
3. Configure a reverse proxy like Nginx
4. Use HTTPS for all communications

### Environment Variables

- `YOUTUBE_API_KEY`: YouTube API key
- `HOST`: Server host (default: 127.0.0.1)
- `PORT`: Server port (default: 8000)
- `LOG_LEVEL_CONSOLE`: Console log level (default: INFO)
- `LOG_LEVEL_FILE`: File log level (default: DEBUG)
- `DEBUG`: Debug mode (default: false)

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [YouTube API Documentation](https://developers.google.com/youtube/v3/docs)
- [asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
