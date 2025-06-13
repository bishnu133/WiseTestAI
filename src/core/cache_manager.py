"""
Element cache management for AITestRunner
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class CacheManager:
    """Manages element selector caching"""

    def __init__(self, cache_dir: str = "config/mapping", ttl: int = 86400):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl  # Time to live in seconds
        self.cache = {}
        self.project_name = None

    def set_project(self, project_name: str):
        """Set project name for cache file"""
        self.project_name = project_name.lower().replace(' ', '_')
        self._load_cache()

    def _load_cache(self):
        """Load cache from file"""
        if not self.project_name:
            return

        cache_file = self.cache_dir / f"{self.project_name}_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self.cache = json.load(f)
                    self._clean_expired()
            except Exception as e:
                print(f"Error loading cache: {e}")
                self.cache = {}

    def _save_cache(self):
        """Save cache to file"""
        if not self.project_name:
            return

        cache_file = self.cache_dir / f"{self.project_name}_cache.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def _clean_expired(self):
        """Remove expired cache entries"""
        current_time = datetime.now().timestamp()
        expired_keys = []

        for key, data in self.cache.items():
            if current_time - data.get('timestamp', 0) > self.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            self._save_cache()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached element info"""
        if key in self.cache:
            data = self.cache[key]
            if datetime.now().timestamp() - data.get('timestamp', 0) <= self.ttl:
                return data.get('value')
        return None

    def save_cache(self, key: str, value: Dict[str, Any]):
        """Save element info to cache"""
        self.cache[key] = {
            'value': value,
            'timestamp': datetime.now().timestamp()
        }
        self._save_cache()

    def clear_cache(self):
        """Clear all cache"""
        self.cache = {}
        self._save_cache()