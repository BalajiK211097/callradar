"""
In-memory LRU cache for recently retrieved analyses.

Avoids repeated JSON deserialisation of large analysis blobs for
the same call within a short window.  The cache is process-local
and does not survive restarts — that is intentional for a hackathon.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

_MAX_ENTRIES = 200


class _LRUCache:
    """Thread-unsafe LRU dict cache.  Sufficient for a single-worker server."""

    def __init__(self, max_size: int = _MAX_ENTRIES) -> None:
        """Initialise an LRU cache with a fixed capacity.

        Args:
            max_size: Maximum number of entries to retain.
        """
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        """Return cached value or None if the key is absent.

        Args:
            key: Cache key.

        Returns:
            Cached value or None.
        """
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def set(self, key: str, value: Any) -> None:
        """Store a value, evicting the oldest entry if at capacity.

        Args:
            key: Cache key.
            value: Value to store (any serialisable type).
        """
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        """Remove a single entry if it exists.

        Args:
            key: Cache key to remove.
        """
        self._store.pop(key, None)

    def clear(self) -> None:
        """Evict all cached entries."""
        self._store.clear()

    def __len__(self) -> int:
        """Return the number of entries currently held."""
        return len(self._store)


# Module-level singleton — import and use directly
analysis_cache = _LRUCache()
