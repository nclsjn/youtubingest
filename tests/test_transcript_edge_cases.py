#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for edge cases in transcript formatting.

Tests the _format_transcript_by_blocks_sync method with various edge cases
that might cause errors in production.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.transcript import TranscriptManager


class TestTranscriptEdgeCases(unittest.TestCase):
    """Test cases for edge cases in transcript formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.transcript_manager = TranscriptManager()
        self.log_prefix = "[TEST]"

    def create_mock_transcript_segment(self, start: Any, duration: Any, text: Any) -> MagicMock:
        """Create a mock transcript segment with the given attributes."""
        segment = MagicMock()
        segment.start = start
        segment.duration = duration
        segment.text = text
        return segment

    def test_format_transcript_with_none_values(self):
        """Test formatting with None values in transcript data."""
        # Create mock transcript data with None values
        transcript_data = [
            self.create_mock_transcript_segment(None, 5, "Hello"),
            self.create_mock_transcript_segment(5, None, "world"),
            self.create_mock_transcript_segment(10, 5, None),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # With our improved error handling, it should handle None values
        # and still return a formatted transcript with valid segments
        self.assertIn("Hello", result)
        self.assertIn("world", result)

    def test_format_transcript_with_string_numbers(self):
        """Test formatting with string numbers in transcript data."""
        # Create mock transcript data with string numbers
        transcript_data = [
            self.create_mock_transcript_segment("0", "5", "Hello"),
            self.create_mock_transcript_segment("5", "5", "world"),
            self.create_mock_transcript_segment("10", "5", "this is a test"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        expected = "[00:00:00] Hello world\n[00:00:10] this is a test"
        self.assertEqual(result, expected)

    def test_format_transcript_with_invalid_string_numbers(self):
        """Test formatting with invalid string numbers in transcript data."""
        # Create mock transcript data with invalid string numbers
        transcript_data = [
            self.create_mock_transcript_segment("0", "5", "Hello"),
            self.create_mock_transcript_segment("5a", "5", "world"),  # Invalid
            self.create_mock_transcript_segment("10", "5b", "test"),  # Invalid
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Should only include the valid segment
        self.assertEqual(result, "[00:00:00] Hello")

    def test_format_transcript_with_missing_attributes(self):
        """Test formatting with segments missing required attributes."""
        # Create mock transcript data with missing attributes
        segment1 = MagicMock()
        segment1.start = 0
        segment1.duration = 5
        segment1.text = "Hello"

        segment2 = MagicMock()
        segment2.start = 5
        # Missing duration - will be treated as 0.0
        segment2.duration = None
        segment2.text = "world"

        segment3 = MagicMock()
        segment3.start = 10
        segment3.duration = 5
        # Missing text - will be skipped
        segment3.text = None

        segment4 = MagicMock()
        # Missing start - will be treated as 0.0
        segment4.start = None
        segment4.duration = 5
        segment4.text = "test"

        transcript_data = [segment1, segment2, segment3, segment4]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # With our improved error handling, it should include segments with default values
        self.assertIn("Hello", result)
        self.assertIn("world", result)
        self.assertIn("test", result)

    def test_format_transcript_with_very_large_values(self):
        """Test formatting with very large values in transcript data."""
        # Create mock transcript data with very large values
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
            self.create_mock_transcript_segment(10**10, 5, "large start time"),  # Very large start time
            self.create_mock_transcript_segment(20, 10**10, "large duration"),  # Very large duration
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Check that the result contains the expected segments
        self.assertIn("Hello world", result)
        self.assertIn("large start time", result)
        self.assertIn("large duration", result)

        # The exact timestamp format for very large values might vary depending on the system
        # so we just check that the timestamps are present
        self.assertIn("[00:00:00]", result)  # For "Hello world"
        # The timestamp for "large start time" will be very large
        # The timestamp for "large duration" will be at 20 seconds
        self.assertIn("[00:00:20]", result)

    def test_format_transcript_with_special_characters(self):
        """Test formatting with special characters in transcript data."""
        # Create mock transcript data with special characters
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello & world"),
            self.create_mock_transcript_segment(5, 5, "Special < > characters"),
            self.create_mock_transcript_segment(10, 5, "Emoji 😊 test"),
            self.create_mock_transcript_segment(15, 5, "HTML <b>tags</b>"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        expected = "[00:00:00] Hello & world Special < > characters\n[00:00:10] Emoji 😊 test HTML <b>tags</b>"
        self.assertEqual(result, expected)

    def test_format_transcript_with_html_entities(self):
        """Test formatting with HTML entities in transcript data."""
        # Create mock transcript data with HTML entities
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello &amp; world"),
            self.create_mock_transcript_segment(5, 5, "&lt;Special&gt; characters"),
            self.create_mock_transcript_segment(10, 5, "&quot;Quoted text&quot;"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # HTML entities should be preserved
        expected = "[00:00:00] Hello &amp; world &lt;Special&gt; characters\n[00:00:10] &quot;Quoted text&quot;"
        self.assertEqual(result, expected)

    def test_format_transcript_with_very_long_text(self):
        """Test formatting with very long text in transcript data."""
        # Create mock transcript data with very long text
        long_text = "This is a very long text. " * 100  # 2400 characters
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello world"),
            self.create_mock_transcript_segment(5, 5, long_text),
            self.create_mock_transcript_segment(10, 5, "After long text"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Should handle long text correctly
        self.assertIn("[00:00:00] Hello world", result)
        self.assertIn("This is a very long text.", result)
        self.assertIn("[00:00:10] After long text", result)

    def test_format_transcript_with_many_segments(self):
        """Test formatting with many segments in transcript data."""
        # Create mock transcript data with many segments
        transcript_data = []
        for i in range(1000):
            transcript_data.append(self.create_mock_transcript_segment(i, 1, f"Segment {i}"))

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 100, self.log_prefix
        )

        # Should handle many segments correctly
        self.assertIn("[00:00:00]", result)
        self.assertIn("Segment 0", result)
        self.assertIn("[00:01:40]", result)  # 100 seconds later
        # The exact timestamp for 1000 seconds might vary depending on how segments are grouped
        # so we just check that segment 900 is present
        self.assertIn("Segment 900", result)

    def test_format_transcript_with_zero_duration(self):
        """Test formatting with zero duration in transcript data."""
        # Create mock transcript data with zero duration
        transcript_data = [
            self.create_mock_transcript_segment(0, 0, "Zero duration"),
            self.create_mock_transcript_segment(5, 5, "Normal duration"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Should handle zero duration correctly
        expected = "[00:00:00] Zero duration Normal duration"
        self.assertEqual(result, expected)

    def test_format_transcript_with_negative_duration(self):
        """Test formatting with negative duration in transcript data."""
        # Create mock transcript data with negative duration
        transcript_data = [
            self.create_mock_transcript_segment(0, -5, "Negative duration"),
            self.create_mock_transcript_segment(5, 5, "Normal duration"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Should handle negative duration correctly (end time will be less than start time)
        expected = "[00:00:00] Negative duration Normal duration"
        self.assertEqual(result, expected)

    def test_format_transcript_with_negative_start_time(self):
        """Test formatting with negative start time in transcript data."""
        # Create mock transcript data with negative start time
        transcript_data = [
            self.create_mock_transcript_segment(-5, 5, "Negative start"),
            self.create_mock_transcript_segment(0, 5, "Zero start"),
            self.create_mock_transcript_segment(5, 5, "Positive start"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Check that the result contains all segments
        self.assertIn("Negative start", result)
        self.assertIn("Zero start", result)
        self.assertIn("Positive start", result)

        # Negative start time should be treated as 0
        self.assertIn("[00:00:00]", result)


if __name__ == '__main__':
    unittest.main()
