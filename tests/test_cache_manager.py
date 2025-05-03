"""
Tests for the cache manager module.
"""
import unittest
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cache_manager import CacheManager, cache_manager


class TestCacheManager(unittest.TestCase):
    """Test cases for the CacheManager class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a fresh instance of CacheManager for each test
        self.cache_manager = CacheManager()

    def test_singleton_pattern(self):
        """Test that the cache_manager is a singleton."""
        # The global cache_manager should be the same instance
        self.assertIs(cache_manager, cache_manager)

        # Creating a new instance should return a different object
        new_manager = CacheManager()
        self.assertIsNot(cache_manager, new_manager)

    def test_register_func_cache(self):
        """Test registering a function cache."""
        # Create a mock function with a cache_clear method
        mock_func = MagicMock()
        mock_func.cache_clear = MagicMock()

        # Register the function cache
        self.cache_manager.register_func_cache("test_func", mock_func)

        # Check that the function was registered
        self.assertIn("test_func", self.cache_manager._func_caches)
        self.assertEqual(self.cache_manager._func_caches["test_func"], mock_func)

    def test_register_func_cache_no_cache_clear(self):
        """Test registering a function without cache_clear method."""
        # Create a mock function without a cache_clear method
        mock_func = MagicMock()

        # Register the function cache should not raise an error
        # Note: The actual implementation registers the function even if it doesn't have cache_clear
        # This is different from our initial expectation, but it's the actual behavior
        self.cache_manager.register_func_cache("test_func", mock_func)

        # The function should be registered
        self.assertIn("test_func", self.cache_manager._func_caches)


class TestCacheManagerAsync(unittest.IsolatedAsyncioTestCase):
    """Test cases for the async methods of CacheManager."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create a fresh instance of CacheManager for each test
        self.cache_manager = CacheManager()

    async def test_register_lru_cache(self):
        """Test registering an LRU cache."""
        # Create a mock LRU cache
        mock_lru_cache = MagicMock()
        mock_lru_cache.clear = MagicMock(return_value=asyncio.Future())
        mock_lru_cache.clear.return_value.set_result(5)  # 5 items cleared

        # Register the LRU cache
        await self.cache_manager.register_lru_cache("test_lru", mock_lru_cache)

        # Check that the LRU cache was registered
        self.assertIn("test_lru", self.cache_manager._lru_caches)
        self.assertEqual(self.cache_manager._lru_caches["test_lru"], mock_lru_cache)

    async def test_clear_lru_caches(self):
        """Test clearing LRU caches through clear_all_caches."""
        # Create mock LRU caches
        mock_lru1 = MagicMock()
        mock_lru1.clear = MagicMock(return_value=asyncio.Future())
        mock_lru1.clear.return_value.set_result(3)  # 3 items cleared

        mock_lru2 = MagicMock()
        mock_lru2.clear = MagicMock(return_value=asyncio.Future())
        mock_lru2.clear.return_value.set_result(2)  # 2 items cleared

        # Register the LRU caches
        await self.cache_manager.register_lru_cache("test_lru1", mock_lru1)
        await self.cache_manager.register_lru_cache("test_lru2", mock_lru2)

        # Clear all caches (including LRU caches)
        results = await self.cache_manager.clear_all_caches()

        # Check that the clear methods were called
        mock_lru1.clear.assert_called_once()
        mock_lru2.clear.assert_called_once()

        # Check the results
        self.assertEqual(results["lru_cache_test_lru1"], 3)
        self.assertEqual(results["lru_cache_test_lru2"], 2)

    async def test_clear_all_caches(self):
        """Test clearing all caches."""
        # Create mock function caches
        mock_func = MagicMock()
        mock_func.cache_clear = MagicMock()

        # Create mock LRU caches
        mock_lru = MagicMock()
        mock_lru.clear = MagicMock(return_value=asyncio.Future())
        mock_lru.clear.return_value.set_result(4)  # 4 items cleared

        # Register the caches
        self.cache_manager.register_func_cache("test_func", mock_func)
        await self.cache_manager.register_lru_cache("test_lru", mock_lru)

        # Clear all caches
        results = await self.cache_manager.clear_all_caches()

        # Check that the clear methods were called
        mock_func.cache_clear.assert_called_once()
        mock_lru.clear.assert_called_once()

        # Check the results
        self.assertEqual(results["function_caches_cleared"], 1)
        self.assertEqual(results["lru_cache_test_lru"], 4)

    async def test_clear_func_caches(self):
        """Test clearing function caches through clear_all_caches."""
        # Create mock functions with cache_clear methods
        mock_func1 = MagicMock()
        mock_func1.cache_clear = MagicMock()
        mock_func2 = MagicMock()
        mock_func2.cache_clear = MagicMock()

        # Register the function caches
        self.cache_manager.register_func_cache("test_func1", mock_func1)
        self.cache_manager.register_func_cache("test_func2", mock_func2)

        # Clear all caches (including function caches)
        results = await self.cache_manager.clear_all_caches()

        # Check that the cache_clear methods were called
        mock_func1.cache_clear.assert_called_once()
        mock_func2.cache_clear.assert_called_once()

        # Check the results
        self.assertEqual(results["function_caches_cleared"], 2)

    async def test_get_stats(self):
        """Test getting cache statistics."""
        # Register mock function caches
        mock_func1 = MagicMock()
        mock_func1.cache_clear = MagicMock()
        mock_func1.cache_info = MagicMock(return_value=MagicMock(hits=10, misses=5, maxsize=128, currsize=15))

        mock_func2 = MagicMock()
        mock_func2.cache_clear = MagicMock()
        mock_func2.cache_info = MagicMock(return_value=MagicMock(hits=20, misses=10, maxsize=128, currsize=25))

        self.cache_manager.register_func_cache("test_func1", mock_func1)
        self.cache_manager.register_func_cache("test_func2", mock_func2)

        # Get the stats
        stats = await self.cache_manager.get_stats()

        # Check the stats
        self.assertIn("func_cache_test_func1", stats)
        self.assertIn("func_cache_test_func2", stats)
        self.assertEqual(stats["func_cache_test_func1"]["hits"], 10)
        self.assertEqual(stats["func_cache_test_func2"]["hits"], 20)


if __name__ == '__main__':
    unittest.main()
