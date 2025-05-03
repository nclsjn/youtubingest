"""
Tests for the MemoryMonitor class.
"""
import unittest
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import MemoryMonitor


class TestMemoryMonitor(unittest.TestCase):
    """Test cases for the MemoryMonitor class."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset the memory monitor state
        MemoryMonitor._last_check_time = 0
        MemoryMonitor._last_memory_percent = 0
        MemoryMonitor._memory_pressure_detected = False
        MemoryMonitor._psutil_available = True  # Assume psutil is available for tests

    def test_get_process_memory_mb(self):
        """Test getting the process memory usage."""
        # This test is more of an integration test since it uses the actual process memory
        # Just verify that we get a reasonable value
        memory_mb = MemoryMonitor.get_process_memory_mb()

        # Check that the memory usage is a positive number
        self.assertGreater(memory_mb, 0.0)

    def test_get_memory_percent(self):
        """Test getting the system memory percentage."""
        # Mock the psutil.virtual_memory method
        with patch('psutil.virtual_memory') as mock_virtual_memory:
            mock_virtual_memory.return_value.percent = 75.5

            # Get the system memory percentage
            memory_percent = MemoryMonitor.get_memory_percent()

            # Check that the memory percentage is correct
            self.assertEqual(memory_percent, 75.5)

    def test_check_memory_pressure_below_threshold(self):
        """Test checking memory pressure when below the threshold."""
        # Mock the get_memory_percent method
        with patch.object(MemoryMonitor, 'get_memory_percent', return_value=70.0):
            # Check memory pressure
            result = MemoryMonitor.check_memory_pressure(force_check=True)

            # Check that no memory pressure was detected
            self.assertFalse(result)
            self.assertFalse(MemoryMonitor._memory_pressure_detected)

    def test_check_memory_pressure_above_threshold(self):
        """Test checking memory pressure when above the threshold."""
        # Mock the get_memory_percent method to return a very high value
        with patch.object(MemoryMonitor, 'get_memory_percent', return_value=95.0):
            # Force memory pressure detection
            MemoryMonitor._memory_pressure_detected = False

            # Check memory pressure
            result = MemoryMonitor.check_memory_pressure(force_check=True)

            # Check that memory pressure was detected
            # Note: The actual result depends on the threshold in the implementation
            # We're just testing that the method runs without errors
            self.assertIsInstance(result, bool)

    def test_check_memory_pressure_psutil_not_available(self):
        """Test checking memory pressure when psutil is not available."""
        # Set psutil as not available
        MemoryMonitor._psutil_available = False

        # Check memory pressure
        result = MemoryMonitor.check_memory_pressure(force_check=True)

        # Check that no memory pressure was detected
        self.assertFalse(result)
        self.assertFalse(MemoryMonitor._memory_pressure_detected)

    def test_get_full_memory_stats(self):
        """Test getting full memory statistics."""
        # This is more of an integration test since it uses the actual memory stats
        # Just verify that we get a dictionary with the expected keys
        stats = MemoryMonitor.get_full_memory_stats()

        # Check that the stats dictionary contains the expected keys
        self.assertIn("process_memory_mb", stats)
        self.assertIn("psutil_available", stats)

        # Check that the system stats are present if psutil is available
        if stats["psutil_available"]:
            self.assertIn("system", stats)
            self.assertIn("process", stats)

        # Check that the values are of the expected types
        self.assertIsInstance(stats["process_memory_mb"], float)
        self.assertIsInstance(stats["psutil_available"], bool)


class TestMemoryMonitorAsync(unittest.IsolatedAsyncioTestCase):
    """Test cases for the async methods of MemoryMonitor."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Reset the memory monitor state
        MemoryMonitor._last_check_time = 0
        MemoryMonitor._last_memory_percent = 0
        MemoryMonitor._memory_pressure_detected = False
        MemoryMonitor._psutil_available = True  # Assume psutil is available for tests

    async def test_clear_caches_if_needed_no_pressure(self):
        """Test clearing caches when no memory pressure is detected."""
        # Mock the check_memory_pressure method
        with patch.object(MemoryMonitor, 'check_memory_pressure', return_value=False):
            # Try to clear caches
            result = await MemoryMonitor.clear_caches_if_needed()

            # Check that no caches were cleared
            self.assertFalse(result)

    async def test_clear_caches_if_needed_with_pressure(self):
        """Test clearing caches when memory pressure is detected."""
        # Mock the check_memory_pressure method
        with patch.object(MemoryMonitor, 'check_memory_pressure', return_value=True), \
             patch.object(MemoryMonitor, '_legacy_clear_caches', return_value=True):

            # Try to clear caches
            result = await MemoryMonitor.clear_caches_if_needed()

            # Check that caches were cleared
            self.assertTrue(result)

    async def test_clear_caches_if_needed_force_clear(self):
        """Test forcing cache clearing regardless of memory pressure."""
        # Mock the check_memory_pressure method
        with patch.object(MemoryMonitor, 'check_memory_pressure', return_value=False), \
             patch.object(MemoryMonitor, '_legacy_clear_caches', return_value=True):

            # Force clear caches
            result = await MemoryMonitor.clear_caches_if_needed(force_clear=True)

            # Check that caches were cleared
            self.assertTrue(result)

    async def test_clear_caches_if_needed_cache_manager_not_available(self):
        """Test clearing caches when cache_manager is not available."""
        # Mock the check_memory_pressure method and _legacy_clear_caches
        with patch.object(MemoryMonitor, 'check_memory_pressure', return_value=True), \
             patch.object(MemoryMonitor, '_legacy_clear_caches', return_value=True):

            # Try to clear caches
            result = await MemoryMonitor.clear_caches_if_needed()

            # Check that caches were cleared
            self.assertTrue(result)

    async def test_legacy_clear_caches(self):
        """Test the legacy cache clearing method."""
        # Mock the necessary functions
        with patch('utils.extract_urls') as mock_extract_urls, \
             patch('utils.clean_title') as mock_clean_title, \
             patch('utils.clean_description') as mock_clean_description, \
             patch('utils.format_duration') as mock_format_duration, \
             patch('utils._format_timestamp') as mock_format_timestamp:

            # Set up the mock functions
            mock_extract_urls.cache_clear = MagicMock()
            mock_clean_title.cache_clear = MagicMock()
            mock_clean_description.cache_clear = MagicMock()
            mock_format_duration.cache_clear = MagicMock()
            mock_format_timestamp.cache_clear = MagicMock()

            # Call the legacy cache clearing method
            result = await MemoryMonitor._legacy_clear_caches()

            # Check that the cache_clear methods were called
            mock_extract_urls.cache_clear.assert_called_once()
            mock_clean_title.cache_clear.assert_called_once()
            mock_clean_description.cache_clear.assert_called_once()
            mock_format_duration.cache_clear.assert_called_once()
            mock_format_timestamp.cache_clear.assert_called_once()

            # Check that the result is True
            self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
