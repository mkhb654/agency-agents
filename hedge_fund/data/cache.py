"""Thread-safe, TTL-based in-memory cache with singleton access.

Usage::

    cache = Cache.get_instance()
    cache.set("my_key", expensive_result, ttl=600)
    value = cache.get("my_key")  # returns None after 600 s

Key generation helper::

    key = Cache.make_key("get_prices", "AAPL", start_date="2024-01-01")
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheStats:
    """Immutable snapshot of cache performance counters."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """Return the cache hit-rate as a fraction in [0, 1]."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class _CacheEntry:
    """Internal wrapper pairing a cached value with an expiry timestamp."""

    value: Any
    expires_at: float  # ``time.monotonic()`` deadline


class Cache:
    """Singleton in-memory cache with per-key TTL and thread safety.

    Parameters
    ----------
    default_ttl:
        Default time-to-live in seconds for entries that do not specify one.
        A value of ``0`` disables expiry.
    max_size:
        Upper bound on the number of cached entries.  When exceeded the oldest
        entries are evicted on the next write.
    """

    _instance: Optional[Cache] = None
    _init_lock: threading.Lock = threading.Lock()

    def __init__(self, default_ttl: int = 3600, max_size: int = 10_000) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, default_ttl: int = 3600, max_size: int = 10_000) -> Cache:
        """Return the global ``Cache`` singleton, creating it on first call.

        Args:
            default_ttl: Default TTL in seconds (only used on first creation).
            max_size: Maximum entries (only used on first creation).

        Returns:
            The singleton ``Cache`` instance.
        """
        if cls._instance is None:
            with cls._init_lock:
                # Double-checked locking pattern.
                if cls._instance is None:
                    cls._instance = cls(default_ttl=default_ttl, max_size=max_size)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Destroy the singleton.  Primarily useful in tests."""
        with cls._init_lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(func_name: str, *args: Any, **kwargs: Any) -> str:
        """Deterministically generate a cache key from a function name and its arguments.

        The key is a SHA-256 hex digest derived from a JSON-serialised
        representation of the inputs.

        Args:
            func_name: Qualified function name used as namespace.
            *args: Positional arguments passed to the function.
            **kwargs: Keyword arguments passed to the function.

        Returns:
            A 64-character hex-digest string suitable as a dictionary key.
        """

        def _serialise(obj: Any) -> Any:
            """Best-effort JSON-safe conversion of arbitrary objects."""
            if isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            if isinstance(obj, (list, tuple)):
                return [_serialise(i) for i in obj]
            if isinstance(obj, dict):
                return {str(k): _serialise(v) for k, v in sorted(obj.items())}
            # Fallback to repr for non-JSON-native types.
            return repr(obj)

        raw = json.dumps(
            {"fn": func_name, "a": _serialise(args), "kw": _serialise(kwargs)},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key, returning ``None`` if missing or expired.

        Args:
            key: Cache key string.

        Returns:
            The cached value, or ``None``.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if self._default_ttl > 0 and time.monotonic() > entry.expires_at:
                # Lazy expiration.
                del self._store[key]
                self._misses += 1
                self._evictions += 1
                logger.debug("Cache EXPIRED key=%s", key[:16])
                return None
            self._hits += 1
            logger.debug("Cache HIT key=%s", key[:16])
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value under *key* with an optional per-entry TTL.

        Args:
            key: Cache key string.
            value: The value to cache.
            ttl: Time-to-live in seconds.  ``None`` uses the default TTL.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        if effective_ttl > 0:
            expires_at = time.monotonic() + effective_ttl
        else:
            expires_at = float("inf")
        with self._lock:
            self._store[key] = _CacheEntry(value=value, expires_at=expires_at)
            logger.debug("Cache SET key=%s ttl=%s", key[:16], effective_ttl)
            # Enforce max_size by evicting oldest entries.
            if len(self._store) > self._max_size:
                self._evict_oldest_locked()

    def delete(self, key: str) -> bool:
        """Remove a single entry.  Returns ``True`` if the key existed.

        Args:
            key: Cache key string.
        """
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
            return existed

    def clear(self) -> int:
        """Remove **all** entries and return how many were cleared."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.debug("Cache CLEARED (%d entries)", count)
            return count

    def has(self, key: str) -> bool:
        """Check whether a non-expired entry exists for *key*."""
        return self.get(key) is not None

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> CacheStats:
        """Return a snapshot of cache performance statistics."""
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                size=len(self._store),
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evict_oldest_locked(self) -> None:
        """Evict entries until we are at or below ``_max_size``.

        Must be called while already holding ``self._lock``.
        """
        target = int(self._max_size * 0.9)
        keys = list(self._store.keys())
        to_remove = len(keys) - target
        for key in keys[:to_remove]:
            del self._store[key]
            self._evictions += 1
        logger.debug("Cache EVICTED %d entries", to_remove)
