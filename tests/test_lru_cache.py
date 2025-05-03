"""
Tests for the LRUCache class.
"""
import unittest
import sys
import os
import asyncio
import time
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import LRUCache


class TestLRUCache(unittest.IsolatedAsyncioTestCase):
    """Test cases for the LRUCache class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create a fresh instance of LRUCache for each test
        self.cache = LRUCache(maxsize=3, ttl_seconds=10)

    async def test_put_and_get(self):
        """Test putting and getting items from the cache."""
        # Put an item in the cache
        await self.cache.put("key1", "value1")

        # Get the item from the cache
        value = await self.cache.get("key1")

        # Check that the item was retrieved correctly
        self.assertEqual(value, "value1")

        # Check that a non-existent key returns None
        value = await self.cache.get("non-existent-key")
        self.assertIsNone(value)

    async def test_maxsize(self):
        """Test that the cache respects the maxsize limit."""
        # Put more items than the maxsize
        await self.cache.put("key1", "value1")
        await self.cache.put("key2", "value2")
        await self.cache.put("key3", "value3")
        await self.cache.put("key4", "value4")  # This should evict key1

        # Check that the oldest item was evicted
        value = await self.cache.get("key1")
        self.assertIsNone(value)

        # Check that the other items are still in the cache
        self.assertEqual(await self.cache.get("key2"), "value2")
        self.assertEqual(await self.cache.get("key3"), "value3")
        self.assertEqual(await self.cache.get("key4"), "value4")

    async def test_lru_policy(self):
        """Test that the cache follows the Least Recently Used policy."""
        # Put items in the cache
        await self.cache.put("key1", "value1")
        await self.cache.put("key2", "value2")
        await self.cache.put("key3", "value3")

        # Access key1 to make it the most recently used
        await self.cache.get("key1")

        # Put a new item, which should evict key2 (the least recently used)
        await self.cache.put("key4", "value4")

        # Check that key2 was evicted
        value = await self.cache.get("key2")
        self.assertIsNone(value)

        # Check that the other items are still in the cache
        self.assertEqual(await self.cache.get("key1"), "value1")
        self.assertEqual(await self.cache.get("key3"), "value3")
        self.assertEqual(await self.cache.get("key4"), "value4")

    async def test_ttl(self):
        """Test that items expire after the TTL."""
        # Create a cache with a short TTL
        cache = LRUCache(maxsize=3, ttl_seconds=0.1)

        # Put an item in the cache
        await cache.put("key1", "value1")

        # Check that the item is in the cache
        value = await cache.get("key1")
        self.assertEqual(value, "value1")

        # Wait for the TTL to expire
        await asyncio.sleep(0.2)

        # Check that the item has expired
        value = await cache.get("key1")
        self.assertIsNone(value)

    async def test_clear(self):
        """Test clearing the cache."""
        # Put items in the cache
        await self.cache.put("key1", "value1")
        await self.cache.put("key2", "value2")

        # Clear the cache
        cleared_count = await self.cache.clear()

        # Check that the correct number of items were cleared
        self.assertEqual(cleared_count, 2)

        # Check that the items are no longer in the cache
        self.assertIsNone(await self.cache.get("key1"))
        self.assertIsNone(await self.cache.get("key2"))

    async def test_get_stats(self):
        """Test getting cache statistics."""
        # Put items in the cache
        await self.cache.put("key1", "value1")
        await self.cache.put("key2", "value2")

        # Get an item to increment the hit count
        await self.cache.get("key1")

        # Try to get a non-existent item to increment the miss count
        await self.cache.get("non-existent-key")

        # Get the stats
        stats = await self.cache.get_stats()

        # Check the stats
        self.assertEqual(stats["size"], 2)
        self.assertEqual(stats["maxsize"], 3)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertTrue(stats["ttl_enabled"])
        self.assertEqual(stats["hit_ratio"], 0.5)

    async def test_update_existing_item(self):
        """Test updating an existing item in the cache."""
        # Put an item in the cache
        await self.cache.put("key1", "value1")

        # Update the item
        await self.cache.put("key1", "updated-value")

        # Check that the item was updated
        value = await self.cache.get("key1")
        self.assertEqual(value, "updated-value")

    async def test_contains(self):
        """Test checking if an item is in the cache."""
        # Put an item in the cache
        await self.cache.put("key1", "value1")

        # Check that the item is in the cache by getting it
        value = await self.cache.get("key1")
        self.assertIsNotNone(value)

        # Check that a non-existent key returns None
        value = await self.cache.get("non-existent-key")
        self.assertIsNone(value)


if __name__ == '__main__':
    unittest.main()
