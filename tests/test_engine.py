"""
Tests for the YoutubeScraperEngine class.
"""
import unittest
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.engine import YoutubeScraperEngine
from services.youtube_api import YouTubeAPIClient
from services.transcript import TranscriptManager
from models import Video
from exceptions import QuotaExceededError, InvalidInputError, ResourceNotFoundError


class TestYoutubeScraperEngine(unittest.IsolatedAsyncioTestCase):
    """Test cases for the YoutubeScraperEngine class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create mock dependencies
        self.api_client = MagicMock(spec=YouTubeAPIClient)
        self.api_client.quota_reached = False
        self.api_client.api_calls_count = 0
        self.api_client.api_quota_used = 0

        self.transcript_manager = MagicMock(spec=TranscriptManager)

        # Create the engine with mock dependencies
        self.engine = YoutubeScraperEngine(self.api_client, self.transcript_manager)

    async def test_init(self):
        """Test initialization of the engine."""
        self.assertEqual(self.engine.api_client, self.api_client)
        self.assertEqual(self.engine.transcript_manager, self.transcript_manager)
        self.assertEqual(self.engine.quota_reached, False)
        self.assertIsNotNone(self.engine._global_stats)

    async def test_check_quota_no_error(self):
        """Test _check_quota when quota is not reached."""
        # Arrange
        self.api_client.quota_reached = False

        # Act & Assert - Should not raise an exception
        self.engine._check_quota("test-request-id")

    async def test_check_quota_error(self):
        """Test _check_quota when quota is reached."""
        # Arrange
        self.api_client.quota_reached = True

        # Act & Assert - Should raise QuotaExceededError
        with self.assertRaises(QuotaExceededError):
            self.engine._check_quota("test-request-id")

    async def test_identify_and_get_video_ids_invalid_input(self):
        """Test _identify_and_get_video_ids with invalid input."""
        # Arrange
        self.api_client.extract_identifier.return_value = None

        # Act & Assert - Should raise InvalidInputError
        with self.assertRaises(InvalidInputError):
            await self.engine._identify_and_get_video_ids("invalid-url", "test-request-id")

    async def test_identify_and_get_video_ids_valid_input(self):
        """Test _identify_and_get_video_ids with valid input."""
        # Arrange
        self.api_client.extract_identifier.return_value = ("video-id", "video")
        self.api_client.get_videos_from_source.return_value = (["video-id"], "Video Title", False)

        # Act
        source_name, video_ids, content_type, high_quota_cost = await self.engine._identify_and_get_video_ids(
            "https://www.youtube.com/watch?v=video-id",
            "test-request-id"
        )

        # Assert
        self.assertEqual(source_name, "Video Title")
        self.assertEqual(video_ids, ["video-id"])
        self.assertEqual(content_type, "video")
        self.assertEqual(high_quota_cost, False)

    async def test_process_videos_and_transcripts_no_videos(self):
        """Test _process_videos_and_transcripts with no videos."""
        # Arrange
        self.api_client.get_video_details_batch.return_value = []

        # Act
        videos, transcript_found_count = await self.engine._process_videos_and_transcripts(
            ["video-id"],
            True,
            30,
            "test-request-id"
        )

        # Assert
        self.assertEqual(videos, [])
        self.assertEqual(transcript_found_count, 0)

    async def test_process_videos_and_transcripts_with_videos_no_transcript(self):
        """Test _process_videos_and_transcripts with videos but no transcript requested."""
        # Arrange
        mock_video = MagicMock(spec=Video)
        mock_video.id = "video-id"
        mock_video.default_language = "en"
        mock_video.default_audio_language = "en"

        self.api_client.get_video_details_batch.return_value = [mock_video]

        # Act
        videos, transcript_found_count = await self.engine._process_videos_and_transcripts(
            ["video-id"],
            False,  # No transcript requested
            30,
            "test-request-id"
        )

        # Assert
        self.assertEqual(videos, [mock_video])
        self.assertEqual(transcript_found_count, 0)
        self.transcript_manager.get_transcript.assert_not_called()

    async def test_process_transcripts_concurrently_no_videos(self):
        """Test _process_transcripts_concurrently with no videos."""
        # Act
        videos, found_count = await self.engine._process_transcripts_concurrently([], 30, "test-request-id")

        # Assert
        self.assertEqual(videos, [])
        self.assertEqual(found_count, 0)

    async def test_process_transcripts_concurrently_with_videos(self):
        """Test _process_transcripts_concurrently with videos."""
        # Arrange
        mock_video1 = MagicMock(spec=Video)
        mock_video1.id = "video-id-1"
        mock_video1.default_language = "en"
        mock_video1.default_audio_language = "en"

        mock_video2 = MagicMock(spec=Video)
        mock_video2.id = "video-id-2"
        mock_video2.default_language = "fr"
        mock_video2.default_audio_language = "fr"

        videos = [mock_video1, mock_video2]

        # Mock transcript manager to return a transcript for the first video only
        self.transcript_manager.get_transcript.side_effect = [
            {"language": "en", "transcript": "Transcript 1"},
            None
        ]

        # Act
        result_videos, found_count = await self.engine._process_transcripts_concurrently(
            videos,
            30,
            "test-request-id"
        )

        # Assert
        self.assertEqual(result_videos, videos)  # Should return the same list
        self.assertEqual(found_count, 1)  # Only one transcript found
        self.assertEqual(mock_video1.transcript, {"language": "en", "transcript": "Transcript 1"})
        self.assertEqual(mock_video1.video_transcript_language, "en")
        self.assertIsNone(mock_video2.transcript)
        self.assertIsNone(mock_video2.video_transcript_language)

    async def test_finalize_processing(self):
        """Test _finalize_processing."""
        # Arrange
        mock_video = MagicMock(spec=Video)
        videos = [mock_video]
        request_context = {
            "start_time_mono": asyncio.get_event_loop().time(),
            "request_start_api_calls": 5,
            "request_start_quota_used": 10,
            "request_id": "test-request-id"
        }

        # Act
        source_name, result_videos, stats, high_quota_cost = self.engine._finalize_processing(
            "Test Source",
            videos,
            1,  # transcript_found_count
            False,  # high_quota_cost
            request_context
        )

        # Assert
        self.assertEqual(source_name, "Test Source")
        self.assertEqual(result_videos, videos)
        self.assertIn("processing_time_ms", stats)
        self.assertIn("api_calls_request", stats)
        self.assertIn("api_quota_used_request", stats)
        self.assertIn("memory_mb_process", stats)
        self.assertEqual(high_quota_cost, False)

    async def test_get_global_stats(self):
        """Test get_global_stats."""
        # Arrange
        self.api_client.get_api_stats.return_value = {"api_calls": 10}
        self.transcript_manager.get_stats.return_value = {"cache_hits": 5}

        # Act
        stats = await self.engine.get_global_stats()

        # Assert
        self.assertIn("engine_uptime_seconds", stats)
        self.assertIn("total_requests_processed", stats)
        self.assertIn("total_videos_processed", stats)
        self.assertIn("api_client_stats", stats)
        self.assertIn("transcript_manager_stats", stats)
        self.assertIn("memory_stats", stats)

    async def test_clear_caches(self):
        """Test clear_caches."""
        # This is more of an integration test
        # Just verify that the method returns a dictionary

        # Act
        results = await self.engine.clear_caches()

        # Assert
        self.assertIsInstance(results, dict)
        # Check if it's an error result or a successful result
        if "error" in results:
            self.assertIsInstance(results["error"], str)
        else:
            self.assertIn("garbage_collection", results)


if __name__ == '__main__':
    unittest.main()
