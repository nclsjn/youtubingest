#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pydantic models and Dataclasses for Youtubingest API requests, responses,
and internal data structures.
"""

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# Import necessary functions from text_processing
from text_processing import (
    extract_urls,
    clean_title,
    clean_description,
    format_duration
)
# Import config for default values
from config import config
from logging_config import StructuredLogger

logger = StructuredLogger(__name__)


class IngestRequest(BaseModel):
    """Data model for YouTube content ingestion requests.

    Defines the parameters and validation for the /ingest endpoint.
    """

    url: str = Field(
        ...,
        description="YouTube URL (video, playlist, channel) or search term."
    )
    include_transcript: bool = Field(
        True,
        description="Whether to include the video transcript(s)."
    )
    include_description: bool = Field(
        True,
        description="Whether to include the video description(s)."
    )

    transcript_interval: Optional[int] = Field(
        None,
        description="Interval (seconds) for grouping transcript lines (0 = no grouping/timestamps). "
                   f"Defaults to {config.DEFAULT_TRANSCRIPT_INTERVAL_SECONDS} if omitted or invalid.",
        ge=0
    )
    start_date: Optional[datetime] = Field(
        None,
        description="Filter videos published on or after this date (ISO 8601 format, e.g. 2023-01-01)."
    )
    end_date: Optional[datetime] = Field(
        None,
        description="Filter videos published on or before this date (ISO 8601 format, e.g. 2023-12-31)."
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Ensure dates have timezone information (assume UTC if missing).

        Args:
            v: The date value to validate

        Returns:
            datetime: The validated date with timezone info
        """
        if v and v.tzinfo is None:
            logger.debug(f"Adding UTC timezone to date: {v}")
            return v.replace(tzinfo=timezone.utc)
        return v

    @field_validator("url")
    @classmethod
    def url_must_be_valid_or_search(cls, v: str) -> str:
        """Validate the URL or search term.

        Args:
            v: The URL or search term to validate

        Returns:
            str: The cleaned URL or search term

        Raises:
            ValueError: If the URL is invalid or missing
        """
        if not v or not isinstance(v, str) or not v.strip():
            raise ValueError("URL or search term is required")

        cleaned = v.strip()

        if len(cleaned) > 1000:
            raise ValueError("URL or search term too long (max 1000 characters)")

        # Basic check for non-YouTube URLs, but allow them as they might be search terms
        if cleaned.startswith(("http://", "https://")):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(cleaned)
                # Log a warning but don't raise error here, let the API client handle it
                if parsed.netloc and not parsed.netloc.endswith(("youtube.com", "youtu.be")):
                    logger.warning(f"Non-YouTube URL provided: {cleaned[:100]}")
            except Exception as e:
                logger.warning(f"Could not parse URL: {cleaned[:100]}: {e}")

        return cleaned

    @field_validator("transcript_interval")
    @classmethod
    def validate_transcript_interval(cls, v: Optional[int]) -> Optional[int]:
        """Validate the transcript interval value.

        Args:
            v: The transcript interval in seconds

        Returns:
            int: The validated interval, or default if invalid or None
        """
        if v is None:
            # Return None here, the default will be applied later if needed
            return None

        allowed_intervals = {0, 10, 20, 30, 60}
        if v in allowed_intervals:
            return v

        logger.warning(f"Invalid transcript_interval value: {v}. Will use default.")
        # Return None, let the processing logic apply the default
        return None


@dataclass
class Video:
    """Data class for video metadata and content.

    Used internally for processing and as part of the API response.
    """

    id: str
    snippet: dict = field(default_factory=dict)
    contentDetails: dict = field(default_factory=dict)
    transcript: Optional[dict] = field(default=None, repr=False)  # Structure: {'language': 'en', 'transcript': '...'}
    tags: List[str] = field(default_factory=list)
    description_urls: List[str] = field(default_factory=list, repr=False)
    video_transcript_language: Optional[str] = None
    api_quota_cost: int = field(default=0)

    @classmethod
    def from_api_response(cls, item: dict) -> "Video":
        """Create a Video instance from a YouTube API video resource item.

        Args:
            item: YouTube API response item for a video

        Returns:
            Video: New Video instance populated with API data
        """
        snippet = item.get("snippet", {})
        description = snippet.get("description", "")

        return cls(
            id=item.get("id"),
            snippet=snippet,
            contentDetails=item.get("contentDetails", {}),
            tags=snippet.get("tags", []) or [],
            description_urls=extract_urls(description),  # Extract URLs on creation
        )

    # Property getters for convenience
    @property
    def title(self) -> str:
        """Get the video title."""
        return self.snippet.get("title", "")

    @property
    def description(self) -> str:
        """Get the video description."""
        return self.snippet.get("description", "")

    @property
    def channel_id(self) -> str:
        """Get the channel ID."""
        return self.snippet.get("channelId", "")

    @property
    def channel_title(self) -> str:
        """Get the channel title."""
        return self.snippet.get("channelTitle", "")

    @property
    def url(self) -> str:
        """Get the video URL."""
        return f"https://youtu.be/{self.id}" if self.id else "#"

    @property
    def channel_url(self) -> str:
        """Get the channel URL."""
        return f"https://www.youtube.com/channel/{self.channel_id}" if self.channel_id else "#"

    @property
    def duration(self) -> str:
        """Get the video duration (ISO 8601 format)."""
        return self.contentDetails.get("duration", "")

    @property
    def published_at(self) -> str:
        """Get the publication date (ISO 8601 string)."""
        return self.snippet.get("publishedAt", "")

    @property
    def default_language(self) -> Optional[str]:
        """Get the default language code."""
        return self.snippet.get("defaultLanguage")

    @property
    def default_audio_language(self) -> Optional[str]:
        """Get the default audio language code."""
        return self.snippet.get("defaultAudioLanguage")

    def get_published_at_datetime(self) -> Optional[datetime]:
        """Convert the published_at string to a timezone-aware datetime object (UTC).

        Returns:
            datetime: Published date as datetime, or None if not available
        """
        pub_str = self.published_at
        if not pub_str:
            return None

        try:
            # Handle potential variations in format (e.g., with/without Z, milliseconds)
            # Ensure it ends with Z for UTC parsing
            if pub_str.endswith("Z"):
                ts = pub_str[:-1]
            else:
                ts = pub_str

            if "." in ts:
                ts = ts.split(".", 1)[0]  # Remove milliseconds if present

            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid publication date format for video {self.id}: {pub_str} - {e}",
                video_id=self.id,
                date_str=pub_str,
                error=str(e)
            )
            return None

    def to_text(self, include_description: bool = True, include_transcript: bool = True) -> str:
        """Convert video metadata and content to a text digest string.

        Args:
            include_description: Whether to include the video description
            include_transcript: Whether to include the video transcript

        Returns:
            str: Formatted text digest for this video
        """
        # Format publication date
        published_at_dt_utc = self.get_published_at_datetime()
        published_at_str = published_at_dt_utc.strftime("%Y-%m-%d %H:%M:%S (UTC)") if published_at_dt_utc else "Unknown Date"

        # Format duration and tags
        formatted_duration = format_duration(self.duration)
        tags_str = ", ".join(f"'{tag}'" for tag in self.tags[:10]) if self.tags else "None"
        if len(self.tags) > 10:
            tags_str += f" ... and {len(self.tags) - 10} more"

        # Clean text content
        cleaned_title = clean_title(self.title)
        cleaned_description = ""
        if include_description and self.description:
            cleaned_description = clean_description(self.description.strip())

        # Get transcript section if requested
        transcript_section = ""
        if include_transcript:
            transcript_section = self._get_transcript_section()

        # Build metadata section
        metadata_lines = [
            f"- Publication Date: {published_at_str}",
            f"- Duration: {formatted_duration}",
            f"- Tags: {tags_str}",
            f"- Video URL: <{html.escape(self.url)}>",
            f"- Channel Name: {html.escape(self.channel_title)}",
            f"- Channel URL: <{html.escape(self.channel_url)}>",
        ]

        # Combine all sections
        text_parts = [
            f"Video Title: {cleaned_title}",
            "\nMetadata:",
            "\n".join(metadata_lines)
        ]

        # Only add description if include_description is True and there is a description
        if include_description and cleaned_description:
            text_parts.extend(["\nDescription:", cleaned_description])

        # Only add transcript if include_transcript is True and there is a transcript section
        if include_transcript and transcript_section:
            text_parts.extend(["\n" + transcript_section])

        return "\n".join(text_parts).strip()

    def _get_transcript_section(self) -> str:
        """Format the transcript section of the digest.

        Returns:
            str: Formatted transcript section or empty string if no transcript
        """
        if self.transcript and isinstance(self.transcript, dict) and self.transcript.get("transcript"):
            lang = self.transcript.get("language", "unknown")
            text = self.transcript.get("transcript", "")
            return f"Transcript (language {lang}):\n{text}"

        # Return empty string instead of a message when no transcript is available
        # This ensures nothing is added to the digest when include_transcript is True but no transcript exists
        return ""

    def get_language_codes(self) -> List[str]:
        """Get all available language codes associated with this video.

        Returns:
            list: List of language codes found in this video's metadata
        """
        langs = set()

        if self.default_language:
            langs.add(self.default_language.split('-')[0])

        if self.default_audio_language:
            langs.add(self.default_audio_language.split('-')[0])

        if self.video_transcript_language:
            langs.add(self.video_transcript_language.split('-')[0])

        return list(langs)


class IngestResponse(BaseModel):
    """Model for ingestion response.

    Defines the structure of the response returned by the /ingest endpoint.
    """

    source_name: str = Field(
        ...,
        description="Identified source (e.g., Playlist title, Channel name, Search query)."
    )
    digest: str = Field(
        ...,
        description="The combined text digest of the processed content."
    )
    video_count: int = Field(
        ...,
        description="Number of videos included in the digest."
    )


    processing_time_ms: Optional[float] = Field(
        None,
        description="Server processing time in milliseconds."
    )
    api_call_count: Optional[int] = Field(
        None,
        description="Number of YouTube API calls made for this request."
    )
    token_count: Optional[int] = Field(
        None,
        description="Number of tokens in the text digest."
    )
    api_quota_used: Optional[int] = Field(
        None,
        description="Estimated YouTube API quota units used for this request."
    )
    high_quota_cost: bool = Field(
        False,
        description="Indicates if this request used high-cost API operations (e.g., search)."
    )
    videos: Optional[List[Video]] = Field(
        None,
        description="List of processed video details (if available)."
    )


class ErrorResponse(BaseModel):
    """Model for error responses.

    Defines the structure of error responses returned by the API.
    """

    detail: str = Field(
        ...,
        description="Detailed error message."
    )
    error_code: Optional[str] = Field(
        None,
        description="Optional internal error code."
    )
    suggestion: Optional[str] = Field(
        None,
        description="Optional suggestion for the user."
    )
