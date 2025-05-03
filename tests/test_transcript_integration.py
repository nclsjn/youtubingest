#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Integration tests for the TranscriptManager.

Tests the complete transcript fetching and formatting process.
"""

import unittest
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Optional

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.transcript import TranscriptManager
from youtube_transcript_api import (YouTubeTranscriptApi, Transcript,
                                   CouldNotRetrieveTranscript, NoTranscriptFound,
                                   TranscriptsDisabled)


class MockTranscript:
    """Mock Transcript class for testing."""

    def __init__(self, language_code: str, is_generated: bool = True, is_translatable: bool = True):
        """Initialize a mock transcript."""
        self.language_code = language_code
        self.language = f"Test Language ({language_code})"
        self.is_generated = is_generated
        self.is_translatable = is_translatable
        self.translation_languages = [
            {"language_code": "en", "language": "English"},
            {"language_code": "fr", "language": "French"},
            {"language_code": "es", "language": "Spanish"},
        ] if is_translatable else []

    def fetch(self):
        """Mock fetch method that returns transcript data."""
        if self.language_code == "error":
            raise CouldNotRetrieveTranscript("Test error")

        # Return mock transcript data
        return [
            {"text": "Hello world", "start": 0.0, "duration": 5.0},
            {"text": "This is a test", "start": 5.0, "duration": 5.0},
            {"text": "Of the transcript API", "start": 10.0, "duration": 5.0},
        ]


class MockTranscriptList:
    """Mock TranscriptList class for testing."""

    def __init__(self, available_transcripts: List[str]):
        """Initialize with a list of available language codes."""
        self.available_transcripts = {
            lang: MockTranscript(lang) for lang in available_transcripts
        }

    def __iter__(self):
        """Make the class iterable to match the real TranscriptList behavior."""
        return iter(self.available_transcripts.values())

    def find_transcript(self, language_codes: List[str]) -> Optional[MockTranscript]:
        """Find a transcript by language code."""
        for lang in language_codes:
            if lang in self.available_transcripts:
                return self.available_transcripts[lang]
        return None

    def find_generated_transcript(self, language_codes: List[str]) -> Optional[MockTranscript]:
        """Find a generated transcript by language code."""
        for lang in language_codes:
            if lang in self.available_transcripts and self.available_transcripts[lang].is_generated:
                return self.available_transcripts[lang]
        return None

    def find_manually_created_transcript(self, language_codes: List[str]) -> Optional[MockTranscript]:
        """Find a manually created transcript by language code."""
        for lang in language_codes:
            if lang in self.available_transcripts and not self.available_transcripts[lang].is_generated:
                return self.available_transcripts[lang]
        return None


class TestTranscriptManagerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for the TranscriptManager."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.transcript_manager = TranscriptManager()

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_success(self, mock_list_transcripts):
        """Test successful transcript retrieval and formatting."""
        # Mock the list_transcripts method
        mock_list_transcripts.return_value = MockTranscriptList(["en", "fr", "es"])

        # Call get_transcript with a valid video ID format (11 characters)
        result = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=30
        )

        # Check the result
        self.assertIsNotNone(result)
        self.assertIn("language", result)
        self.assertEqual(result["language"], "en")
        self.assertIn("transcript", result)
        self.assertIn("[00:00:00]", result["transcript"])
        self.assertIn("Hello world", result["transcript"])

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_no_transcript(self, mock_list_transcripts):
        """Test behavior when no transcript is available."""
        # Mock the list_transcripts method to raise NoTranscriptFound
        # NoTranscriptFound requires video_id, requested_language_codes, and transcript_data
        mock_list_transcripts.side_effect = NoTranscriptFound("test_video_id", ["en"], {})

        # Call get_transcript with a valid video ID format
        result = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=30
        )

        # Check the result
        self.assertIsNone(result)

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_transcripts_disabled(self, mock_list_transcripts):
        """Test behavior when transcripts are disabled."""
        # Mock the list_transcripts method to raise TranscriptsDisabled
        mock_list_transcripts.side_effect = TranscriptsDisabled("test_video_id")

        # Call get_transcript with a valid video ID format
        result = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=30
        )

        # Check the result
        self.assertIsNone(result)

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_language_fallback(self, mock_list_transcripts):
        """Test language fallback when preferred language is not available."""
        # Mock the list_transcripts method
        mock_list_transcripts.return_value = MockTranscriptList(["fr", "es"])  # No English

        # Call get_transcript with English as preferred language
        result = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",  # Not available
            default_audio_language="en",  # Not available
            transcript_interval=30
        )

        # Check the result - should fall back to French
        self.assertIsNotNone(result)
        self.assertIn("language", result)
        self.assertEqual(result["language"], "fr")

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_formatting_error(self, mock_list_transcripts):
        """Test behavior when formatting fails."""
        # Mock the list_transcripts method
        mock_list_transcripts.return_value = MockTranscriptList(["en"])

        # Mock _format_transcript_by_blocks_sync to return None (formatting failure)
        with patch.object(self.transcript_manager, '_format_transcript_by_blocks_sync', return_value=None):
            # Call get_transcript with a valid video ID format
            result = await self.transcript_manager.get_transcript(
                video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
                default_language="en",
                default_audio_language="en",
                transcript_interval=30
            )

            # Check the result
            self.assertIsNone(result)

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_fetch_error(self, mock_list_transcripts):
        """Test behavior when transcript fetch fails."""
        # Create a mock transcript list with an "error" language that will raise an exception
        mock_transcript_list = MockTranscriptList(["error"])
        mock_list_transcripts.return_value = mock_transcript_list

        # Call get_transcript with a valid video ID format
        result = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="error",
            default_audio_language="error",
            transcript_interval=30
        )

        # Check the result
        self.assertIsNone(result)

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_different_intervals(self, mock_list_transcripts):
        """Test transcript formatting with different intervals."""
        # Mock the list_transcripts method
        mock_list_transcripts.return_value = MockTranscriptList(["en"])

        # Test with interval=0 (no timestamps)
        result_no_timestamps = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=0
        )

        # Test with interval=10 (timestamps every 10 seconds)
        result_with_timestamps = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=10
        )

        # Check the results
        self.assertIsNotNone(result_no_timestamps)
        self.assertIsNotNone(result_with_timestamps)

        # No timestamps should not contain "[00:00:00]"
        self.assertNotIn("[00:00:00]", result_no_timestamps["transcript"])

        # With timestamps should contain "[00:00:00]"
        self.assertIn("[00:00:00]", result_with_timestamps["transcript"])

        # With timestamps should have multiple lines
        self.assertIn("\n", result_with_timestamps["transcript"])

    @patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
    async def test_get_transcript_caching(self, mock_list_transcripts):
        """Test that transcripts are cached and reused."""
        # Mock the list_transcripts method
        mock_list_transcripts.return_value = MockTranscriptList(["en"])

        # Call get_transcript twice with the same parameters
        result1 = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=30
        )

        # Second call should use the cache
        result2 = await self.transcript_manager.get_transcript(
            video_id="dQw4w9WgXcQ",  # Valid YouTube video ID format
            default_language="en",
            default_audio_language="en",
            transcript_interval=30
        )

        # Check that both results are the same
        self.assertEqual(result1, result2)

        # Check that list_transcripts was only called once
        mock_list_transcripts.assert_called_once()


if __name__ == '__main__':
    unittest.main()
