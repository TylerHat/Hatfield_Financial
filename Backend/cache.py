"""
Simple thread-safe in-memory cache with TTL support.
"""

import threading
import time


class SimpleCache:
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key, ttl_seconds):
        """Return cached data if it exists and hasn't expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry and (time.time() - entry['ts']) < ttl_seconds:
                return entry['data']
            return None

    def set(self, key, data):
        """Store data with current timestamp."""
        with self._lock:
            self._store[key] = {'data': data, 'ts': time.time()}

    def clear(self, key=None):
        """Clear a specific key or the entire cache."""
        with self._lock:
            if key:
                self._store.pop(key, None)
            else:
                self._store.clear()
