# Youtubingest API Documentation

This document describes the Youtubingest API endpoints, their parameters, and responses.

## Endpoints

### 1. Ingest YouTube Content

Extracts and processes YouTube content (videos, playlists, channels).

**Endpoint**: `/api/v1/ingest`

**Method**: `POST`

**Request Parameters**:

| Parameter | Type | Description | Required | Default |
|-----------|------|-------------|----------|---------|
| url | string | YouTube URL to process | Yes | - |
| include_transcripts | boolean | Include transcriptions | No | true |
| transcript_interval | integer | Transcript grouping interval (seconds) | No | 10 |

**Request Example**:

```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "include_transcripts": true,
  "transcript_interval": 30
}
```

**Response Example**:

```json
{
  "source_name": "Never Gonna Give You Up",
  "content_type": "video",
  "videos": [
    {
      "id": "dQw4w9WgXcQ",
      "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
      "description": "...",
      "channel_title": "Rick Astley",
      "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "duration_seconds": 213,
      "duration_formatted": "3:33",
      "published_at": "2009-10-25T06:57:33Z",
      "view_count": 1234567890,
      "like_count": 12345678,
      "comment_count": 1234567,
      "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
      "transcript": {
        "language": "en",
        "transcript": "[00:00] We're no strangers to love\n[00:10] You know the rules and so do I..."
      }
    }
  ],
  "stats": {
    "processing_time_ms": 1234,
    "api_calls_request": 2,
    "api_quota_used_request": 3,
    "transcript_found_count": 1,
    "memory_mb_process": 123.45
  }
}
```

**Response Codes**:

- `200 OK`: Request processed successfully
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: YouTube resource not found
- `429 Too Many Requests`: Rate limit reached
- `500 Internal Server Error`: Internal server error

### 2. Get Global Stats

Retrieves global application statistics.

**Endpoint**: `/api/v1/stats`

**Method**: `GET`

**Response Example**:

```json
{
  "engine_uptime_seconds": 3600,
  "total_requests_processed": 100,
  "total_videos_processed": 500,
  "api_client_stats": {
    "api_calls": 200,
    "quota_used": 300,
    "quota_reached": false,
    "cache_hits": 50
  },
  "transcript_manager_stats": {
    "cache_hits_result": 80,
    "cache_hits_error": 10,
    "cache_misses": 20,
    "fetch_attempts": 30,
    "fetch_errors": 5
  },
  "memory_stats": {
    "process_memory_mb": 256.78,
    "system": {
      "memory_percent": 45.6,
      "memory_total_gb": 16.0,
      "memory_available_gb": 8.7
    }
  }
}
```

**Response Codes**:

- `200 OK`: Request processed successfully
- `500 Internal Server Error`: Internal server error

### 3. Clear Caches

Clears application caches.

**Endpoint**: `/api/v1/clear-caches`

**Method**: `POST`

**Response Example**:

```json
{
  "function_caches_cleared": 5,
  "lru_cache_youtube_api": 10,
  "lru_cache_transcript": 15,
  "garbage_collection": {
    "objects_collected": 1000,
    "memory_freed_mb": 50.25
  }
}
```

**Response Codes**:

- `200 OK`: Request processed successfully
- `500 Internal Server Error`: Internal server error

### 4. Health Check

Checks the health status of the application.

**Endpoint**: `/api/v1/health`

**Method**: `GET`

**Response Example**:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "api_client_available": true,
  "transcript_manager_available": true,
  "memory_pressure": false,
  "uptime_seconds": 3600
}
```

**Response Codes**:

- `200 OK`: Application is healthy
- `503 Service Unavailable`: Application is unhealthy

## Error Handling

All errors are returned in a consistent JSON format:

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "YouTube API quota exceeded",
    "details": "Daily quota limit reached. Try again tomorrow.",
    "retry_after": 86400
  }
}
```

## API Limits

- **Request Limit**: 30 requests per minute per IP address
- **Video Limit**: 200 videos maximum per request
- **Maximum Request Body Size**: 15 MB

## Authentication

The API does not require authentication at the moment, but it may be limited by IP address.

## Versioning

The API is versioned in the URL (`/api/v1/...`). Incompatible changes will be introduced in a new version.
