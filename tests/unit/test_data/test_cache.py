"""Tests for data/cache.py — TTL cache functionality."""

import time

import pytest

from data.cache import TTLCache


@pytest.fixture
def ttl_cache():
    """Fresh cache instance for each test."""
    c = TTLCache()
    yield c
    c.clear()


class TestTTLCache:
    def test_set_and_get(self, ttl_cache):
        ttl_cache.set("key1", "value1", ttl=60)
        assert ttl_cache.get("key1") == "value1"

    def test_get_nonexistent_returns_none(self, ttl_cache):
        assert ttl_cache.get("nonexistent") is None

    def test_has_returns_true_for_valid(self, ttl_cache):
        ttl_cache.set("key1", 42, ttl=60)
        assert ttl_cache.has("key1") is True

    def test_has_returns_false_for_missing(self, ttl_cache):
        assert ttl_cache.has("missing") is False

    def test_ttl_expiry(self, ttl_cache):
        ttl_cache.set("expire_me", "data", ttl=1)
        assert ttl_cache.get("expire_me") == "data"
        time.sleep(1.1)
        assert ttl_cache.get("expire_me") is None

    def test_has_returns_false_after_expiry(self, ttl_cache):
        ttl_cache.set("expire_me", "data", ttl=1)
        time.sleep(1.1)
        assert ttl_cache.has("expire_me") is False

    def test_overwrite_key(self, ttl_cache):
        ttl_cache.set("key1", "old", ttl=60)
        ttl_cache.set("key1", "new", ttl=60)
        assert ttl_cache.get("key1") == "new"

    def test_different_types(self, ttl_cache):
        ttl_cache.set("int_key", 42, ttl=60)
        ttl_cache.set("list_key", [1, 2, 3], ttl=60)
        ttl_cache.set("dict_key", {"a": 1}, ttl=60)
        assert ttl_cache.get("int_key") == 42
        assert ttl_cache.get("list_key") == [1, 2, 3]
        assert ttl_cache.get("dict_key") == {"a": 1}

    def test_clear(self, ttl_cache):
        ttl_cache.set("a", 1, ttl=60)
        ttl_cache.set("b", 2, ttl=60)
        ttl_cache.clear()
        assert ttl_cache.get("a") is None
        assert ttl_cache.get("b") is None

    def test_delete(self, ttl_cache):
        ttl_cache.set("key1", "val", ttl=60)
        ttl_cache.delete("key1")
        assert ttl_cache.get("key1") is None

    def test_delete_nonexistent_no_error(self, ttl_cache):
        ttl_cache.delete("nonexistent")  # should not raise

    def test_cleanup_removes_expired(self, ttl_cache):
        ttl_cache.set("fresh", "data", ttl=60)
        ttl_cache.set("stale", "data", ttl=1)
        time.sleep(1.1)
        removed = ttl_cache.cleanup()
        assert removed == 1
        assert ttl_cache.get("fresh") == "data"
        assert ttl_cache.get("stale") is None

    def test_size(self, ttl_cache):
        assert ttl_cache.size == 0
        ttl_cache.set("a", 1, ttl=60)
        ttl_cache.set("b", 2, ttl=60)
        assert ttl_cache.size == 2

    def test_independent_ttls(self, ttl_cache):
        ttl_cache.set("short", "data", ttl=1)
        ttl_cache.set("long", "data", ttl=60)
        time.sleep(1.1)
        assert ttl_cache.get("short") is None
        assert ttl_cache.get("long") == "data"
