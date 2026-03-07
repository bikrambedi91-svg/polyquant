"""In-memory TTL cache to avoid spamming external APIs."""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL expiry."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if it exists and hasn't expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store a value with a TTL in seconds."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        """Remove a specific key."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def cleanup(self) -> int:
        """Remove all expired entries. Returns count of removed items."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired_keys = [
                k for k, (_, expires_at) in self._store.items() if now > expires_at
            ]
            for k in expired_keys:
                del self._store[k]
                removed += 1
        return removed

    @property
    def size(self) -> int:
        """Number of entries (including possibly expired ones)."""
        return len(self._store)


# Module-level singleton
cache = TTLCache()
