#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cache Manager for Youtubingest.

Provides a centralized cache management system for the application.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Callable

from config import config
from logging_config import StructuredLogger
from utils import LRUCache

logger = StructuredLogger(__name__)


class CacheManager:
    """Centralized cache management system.
    
    Provides a unified interface for managing multiple caches across the application.
    Supports registration, clearing, and statistics for all registered caches.
    """
    
    def __init__(self):
        """Initialize the cache manager."""
        self._caches: Dict[str, Any] = {}
        self._lru_caches: Dict[str, LRUCache] = {}
        self._func_caches: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
    
    async def register_lru_cache(self, name: str, cache: LRUCache) -> None:
        """Register an LRU cache with the manager.
        
        Args:
            name: A unique name for the cache
            cache: The LRUCache instance to register
        """
        async with self._lock:
            self._lru_caches[name] = cache
            logger.debug(f"Registered LRU cache: {name}")
    
    def register_func_cache(self, name: str, func: Callable) -> None:
        """Register a function with @lru_cache decorator.
        
        Args:
            name: A unique name for the cache
            func: The function with @lru_cache decorator
        """
        if hasattr(func, 'cache_clear'):
            self._func_caches[name] = func
            logger.debug(f"Registered function cache: {name}")
        else:
            logger.warning(f"Function {name} does not have cache_clear method, not registering")
    
    def register_generic_cache(self, name: str, cache: Any, clear_method: str = 'clear') -> None:
        """Register a generic cache object.
        
        Args:
            name: A unique name for the cache
            cache: The cache object to register
            clear_method: The name of the method to call for clearing the cache
        """
        if hasattr(cache, clear_method):
            self._caches[name] = {
                'cache': cache,
                'clear_method': clear_method
            }
            logger.debug(f"Registered generic cache: {name}")
        else:
            logger.warning(f"Cache {name} does not have {clear_method} method, not registering")
    
    async def clear_all_caches(self) -> Dict[str, Any]:
        """Clear all registered caches.
        
        Returns:
            dict: Results of clearing each cache
        """
        logger.info("Clearing all registered caches...")
        results = {}
        
        # Clear LRU caches
        for name, cache in self._lru_caches.items():
            try:
                count = await cache.clear()
                results[f"lru_cache_{name}"] = count
            except Exception as e:
                logger.error(f"Error clearing LRU cache {name}: {e}")
                results[f"lru_cache_{name}"] = f"Error: {e}"
        
        # Clear function caches
        func_caches_cleared = 0
        for name, func in self._func_caches.items():
            try:
                func.cache_clear()
                func_caches_cleared += 1
            except Exception as e:
                logger.error(f"Error clearing function cache {name}: {e}")
                results[f"func_cache_{name}"] = f"Error: {e}"
        
        results["function_caches_cleared"] = func_caches_cleared
        
        # Clear generic caches
        for name, cache_info in self._caches.items():
            try:
                cache = cache_info['cache']
                clear_method = getattr(cache, cache_info['clear_method'])
                result = clear_method()
                results[f"generic_cache_{name}"] = result
            except Exception as e:
                logger.error(f"Error clearing generic cache {name}: {e}")
                results[f"generic_cache_{name}"] = f"Error: {e}"
        
        logger.info(f"Cache clearing complete. Results: {results}")
        return results
    
    async def clear_cache_by_name(self, name: str) -> Any:
        """Clear a specific cache by name.
        
        Args:
            name: The name of the cache to clear
            
        Returns:
            Any: Result of clearing the cache
            
        Raises:
            ValueError: If the cache name is not found
        """
        if name in self._lru_caches:
            try:
                count = await self._lru_caches[name].clear()
                logger.info(f"Cleared LRU cache {name}: {count} items removed")
                return count
            except Exception as e:
                logger.error(f"Error clearing LRU cache {name}: {e}")
                raise
        
        elif name in self._func_caches:
            try:
                self._func_caches[name].cache_clear()
                logger.info(f"Cleared function cache {name}")
                return "cleared"
            except Exception as e:
                logger.error(f"Error clearing function cache {name}: {e}")
                raise
        
        elif name in self._caches:
            try:
                cache_info = self._caches[name]
                cache = cache_info['cache']
                clear_method = getattr(cache, cache_info['clear_method'])
                result = clear_method()
                logger.info(f"Cleared generic cache {name}")
                return result
            except Exception as e:
                logger.error(f"Error clearing generic cache {name}: {e}")
                raise
        
        else:
            logger.warning(f"Cache {name} not found")
            raise ValueError(f"Cache {name} not found")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all registered caches.
        
        Returns:
            dict: Statistics for all caches
        """
        stats = {}
        
        # Get LRU cache stats
        for name, cache in self._lru_caches.items():
            try:
                cache_stats = await cache.get_stats()
                stats[f"lru_cache_{name}"] = cache_stats
            except Exception as e:
                logger.error(f"Error getting stats for LRU cache {name}: {e}")
                stats[f"lru_cache_{name}"] = f"Error: {e}"
        
        # Get function cache info
        for name, func in self._func_caches.items():
            try:
                if hasattr(func, 'cache_info'):
                    cache_info = func.cache_info()
                    stats[f"func_cache_{name}"] = {
                        "hits": cache_info.hits,
                        "misses": cache_info.misses,
                        "maxsize": cache_info.maxsize,
                        "currsize": cache_info.currsize,
                        "hit_ratio": cache_info.hits / (cache_info.hits + cache_info.misses) if (cache_info.hits + cache_info.misses) > 0 else 0
                    }
                else:
                    stats[f"func_cache_{name}"] = "No cache_info method available"
            except Exception as e:
                logger.error(f"Error getting stats for function cache {name}: {e}")
                stats[f"func_cache_{name}"] = f"Error: {e}"
        
        # Get generic cache stats if they have a stats method
        for name, cache_info in self._caches.items():
            try:
                cache = cache_info['cache']
                if hasattr(cache, 'get_stats'):
                    stats[f"generic_cache_{name}"] = cache.get_stats()
                else:
                    stats[f"generic_cache_{name}"] = "No get_stats method available"
            except Exception as e:
                logger.error(f"Error getting stats for generic cache {name}: {e}")
                stats[f"generic_cache_{name}"] = f"Error: {e}"
        
        return stats


# Create a singleton instance
cache_manager = CacheManager()
