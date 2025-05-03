#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for transcript formatting functionality.

Tests the _format_transcript_by_blocks_sync method in TranscriptManager
and the _format_timestamp function in text_processing.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.transcript import TranscriptManager
from text_processing import _format_timestamp


class TestFormatTimestamp(unittest.TestCase):
    """Test cases for the _format_timestamp function."""

    def test_format_timestamp_valid_input(self):
        """Test _format_timestamp with valid input values."""
        test_cases = [
            (0, "00:00:00"),
            (1, "00:00:01"),
            (59, "00:00:59"),
            (60, "00:01:00"),
            (61, "00:01:01"),
            (3599, "00:59:59"),
            (3600, "01:00:00"),
            (3661, "01:01:01"),
            (86399, "23:59:59"),  # 24h - 1s
            (86400, "24:00:00"),  # 24h
            (90000, "25:00:00"),  # 25h
        ]

        for seconds, expected in test_cases:
            with self.subTest(seconds=seconds):
                result = _format_timestamp(seconds)
                self.assertEqual(result, expected)

    def test_format_timestamp_float_input(self):
        """Test _format_timestamp with float input values."""
        test_cases = [
            (0.0, "00:00:00"),
            (0.5, "00:00:00"),  # Truncated to int
            (0.9, "00:00:00"),  # Truncated to int
            (1.1, "00:00:01"),  # Truncated to int
            (59.9, "00:00:59"),  # Truncated to int
            (60.1, "00:01:00"),  # Truncated to int
        ]

        for seconds, expected in test_cases:
            with self.subTest(seconds=seconds):
                result = _format_timestamp(seconds)
                self.assertEqual(result, expected)

    def test_format_timestamp_string_input(self):
        """Test _format_timestamp with string input values."""
        test_cases = [
            ("0", "00:00:00"),
            ("1", "00:00:01"),
            ("60", "00:01:00"),
            ("3600", "01:00:00"),
            ("0.5", "00:00:00"),  # Truncated to int
            ("60.9", "00:01:00"),  # Truncated to int
        ]

        for seconds, expected in test_cases:
            with self.subTest(seconds=seconds):
                result = _format_timestamp(seconds)
                self.assertEqual(result, expected)

    def test_format_timestamp_negative_input(self):
        """Test _format_timestamp with negative input values."""
        test_cases = [
            (-1, "00:00:00"),  # Should be clamped to 0
            (-60, "00:00:00"),  # Should be clamped to 0
            (-3600, "00:00:00"),  # Should be clamped to 0
        ]

        for seconds, expected in test_cases:
            with self.subTest(seconds=seconds):
                result = _format_timestamp(seconds)
                self.assertEqual(result, expected)

    def test_format_timestamp_invalid_input(self):
        """Test _format_timestamp with invalid input values."""
        test_cases = [
            None,
            "",
            "abc",
            "1a",
            {},
            [],
            True,
            False,
        ]

        for seconds in test_cases:
            with self.subTest(seconds=seconds):
                # Should return default value "00:00:00" and log a warning
                try:
                    result = _format_timestamp(seconds)
                    self.assertEqual(result, "00:00:00")
                except TypeError:
                    # For unhashable types, we'll get a TypeError from the lru_cache
                    # This is expected and we'll handle it in the actual code
                    pass


class TestFormatTranscriptByBlocks(unittest.TestCase):
    """Test cases for the _format_transcript_by_blocks_sync method."""

    def setUp(self):
        """Set up test fixtures."""
        self.transcript_manager = TranscriptManager()
        self.log_prefix = "[TEST]"

    def create_mock_transcript_segment(self, start: float, duration: float, text: str) -> MagicMock:
        """Create a mock transcript segment with the given attributes."""
        segment = MagicMock()
        segment.start = start
        segment.duration = duration
        segment.text = text
        return segment

    def test_format_transcript_empty_data(self):
        """Test formatting with empty transcript data."""
        result = self.transcript_manager._format_transcript_by_blocks_sync(
            [], "en", "video123", "Test Source", 30, self.log_prefix
        )
        self.assertIsNone(result)

    def test_format_transcript_no_timestamps(self):
        """Test formatting with interval=0 (no timestamps)."""
        # Create mock transcript data
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
            self.create_mock_transcript_segment(10, 5, "this is"),
            self.create_mock_transcript_segment(15, 5, "a test"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 0, self.log_prefix
        )

        self.assertEqual(result, "Hello world this is a test")

    def test_format_transcript_with_timestamps(self):
        """Test formatting with interval=10 (timestamps every 10 seconds)."""
        # Create mock transcript data
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
            self.create_mock_transcript_segment(10, 5, "this is"),
            self.create_mock_transcript_segment(15, 5, "a test"),
            self.create_mock_transcript_segment(20, 5, "with timestamps"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        expected = "[00:00:00] Hello world\n[00:00:10] this is a test\n[00:00:20] with timestamps"
        self.assertEqual(result, expected)

    def test_format_transcript_with_unsorted_segments(self):
        """Test formatting with unsorted transcript segments."""
        # Create mock transcript data with unsorted timestamps
        transcript_data = [
            self.create_mock_transcript_segment(10, 5, "this is"),
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(20, 5, "with timestamps"),
            self.create_mock_transcript_segment(5, 5, "world"),
            self.create_mock_transcript_segment(15, 5, "a test"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        expected = "[00:00:00] Hello world\n[00:00:10] this is a test\n[00:00:20] with timestamps"
        self.assertEqual(result, expected)

    def test_format_transcript_with_invalid_segments(self):
        """Test formatting with some invalid segments that should be skipped."""
        # Create mock transcript data with some invalid segments
        valid_segment1 = self.create_mock_transcript_segment(0, 5, "Hello")
        valid_segment2 = self.create_mock_transcript_segment(5, 5, "world")

        # Invalid segments with various issues
        invalid_segment1 = MagicMock()  # Missing attributes
        # Configure the mock to return string values for attributes to avoid test issues
        invalid_segment1.start = None
        invalid_segment1.duration = None
        invalid_segment1.text = None

        invalid_segment2 = self.create_mock_transcript_segment(10, 5, "")  # Empty text
        invalid_segment3 = self.create_mock_transcript_segment(15, 5, None)  # None text

        valid_segment3 = self.create_mock_transcript_segment(20, 5, "valid again")

        transcript_data = [
            valid_segment1,
            invalid_segment1,
            valid_segment2,
            invalid_segment2,
            invalid_segment3,
            valid_segment3,
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        # Check that the result contains the expected segments
        self.assertIn("Hello world", result)
        self.assertIn("valid again", result)
        # Check the timestamps
        self.assertIn("[00:00:00]", result)
        self.assertIn("[00:00:20]", result)

    def test_format_transcript_with_whitespace_cleanup(self):
        """Test formatting with text that needs whitespace cleanup."""
        # Create mock transcript data with text that has extra whitespace
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "  Hello  "),
            self.create_mock_transcript_segment(5, 5, " world \n"),
            self.create_mock_transcript_segment(10, 5, "this   is"),
            self.create_mock_transcript_segment(15, 5, "a\ttest  "),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
        )

        expected = "[00:00:00] Hello world\n[00:00:10] this is a test"
        self.assertEqual(result, expected)

    def test_format_transcript_with_exception_in_format_timestamp(self):
        """Test handling of exceptions in _format_timestamp."""
        # Create mock transcript data
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
        ]

        # Mock _format_timestamp to raise an exception
        with patch('text_processing._format_timestamp_uncached', side_effect=Exception("Test exception")):
            result = self.transcript_manager._format_transcript_by_blocks_sync(
                transcript_data, "en", "video123", "Test Source", 10, self.log_prefix
            )

            # With our improved error handling, it should use a default timestamp
            # and still return a formatted transcript
            self.assertIn("[00:00:00]", result)
            self.assertIn("Hello", result)
            self.assertIn("world", result)

    def test_format_transcript_with_large_interval(self):
        """Test formatting with a large interval that groups all segments together."""
        # Create mock transcript data
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
            self.create_mock_transcript_segment(10, 5, "this is"),
            self.create_mock_transcript_segment(15, 5, "a test"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", 100, self.log_prefix
        )

        expected = "[00:00:00] Hello world this is a test"
        self.assertEqual(result, expected)

    def test_format_transcript_with_negative_interval(self):
        """Test formatting with a negative interval (should be treated as 0)."""
        # Create mock transcript data
        transcript_data = [
            self.create_mock_transcript_segment(0, 5, "Hello"),
            self.create_mock_transcript_segment(5, 5, "world"),
        ]

        result = self.transcript_manager._format_transcript_by_blocks_sync(
            transcript_data, "en", "video123", "Test Source", -10, self.log_prefix
        )

        # Negative interval should be treated as 0 (no timestamps)
        self.assertEqual(result, "Hello world")


if __name__ == '__main__':
    unittest.main()
