"""CacheService: the in-memory tier must be a bounded LRU that evicts old entries
and drops expired ones on access (regression guard for the unbounded dict)."""
from __future__ import annotations

import time

import pytest

import app.services.cache_service as cache_mod
from app.services.cache_service import CacheService


@pytest.fixture
def cache(tmp_path, monkeypatch):
    # Fresh singleton per test, pointed at a temp cache dir.
    monkeypatch.setattr(CacheService, "_instance", None, raising=False)
    monkeypatch.setattr(cache_mod.Config, "CACHE_DIR", tmp_path, raising=False)
    return CacheService()


def test_memory_is_bounded(cache, monkeypatch):
    monkeypatch.setattr(cache_mod, "_MAX_MEMORY_ENTRIES", 10)
    for i in range(50):
        cache.set(f"k{i}", i, persist=False)
    assert len(cache.memory_cache) <= 10


def test_lru_evicts_least_recently_used(cache, monkeypatch):
    monkeypatch.setattr(cache_mod, "_MAX_MEMORY_ENTRIES", 3)
    cache.set("a", 1, persist=False)
    cache.set("b", 2, persist=False)
    cache.set("c", 3, persist=False)
    # Touch 'a' so it becomes most-recent; 'b' is now the LRU victim.
    assert cache.get("a", max_age=300) == 1
    cache.set("d", 4, persist=False)  # evicts 'b'
    assert "b" not in cache.memory_cache
    assert set(cache.memory_cache.keys()) == {"a", "c", "d"}


def test_expired_entry_dropped_from_memory(cache):
    cache.set("temp", "v", persist=False)
    assert "temp" in cache.memory_cache
    # A get() past max_age must both miss AND evict the stale entry.
    time.sleep(0.02)
    assert cache.get("temp", max_age=0) is None
    assert "temp" not in cache.memory_cache


def test_get_or_set_populates_once(cache):
    calls = []

    def factory():
        calls.append(1)
        return "computed"

    assert cache.get_or_set("k", factory, max_age=300) == "computed"
    assert cache.get_or_set("k", factory, max_age=300) == "computed"
    assert len(calls) == 1  # second call served from cache


def test_disk_promote_respects_cap(cache, monkeypatch):
    monkeypatch.setattr(cache_mod, "_MAX_MEMORY_ENTRIES", 2)
    # Persist 3 keys to disk, then clear memory and read them back.
    for k in ("x", "y", "z"):
        cache.set(k, k, persist=True)
    cache.memory_cache.clear()
    for k in ("x", "y", "z"):
        assert cache.get(k, max_age=300) == k
    assert len(cache.memory_cache) <= 2
