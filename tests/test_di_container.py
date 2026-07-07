"""ServiceContainer: singleton=False must return fresh instances, singleton=True
must cache, and concurrent get() of a singleton factory must build it exactly once
(regression guards for the two DI bugs found in Fase 3 recon)."""
from __future__ import annotations

import threading
import time

import pytest

from app.core.di import ServiceContainer


@pytest.fixture
def container():
    c = ServiceContainer()
    c.clear()
    yield c
    c.clear()


def test_eager_service_is_returned_as_is(container):
    obj = object()
    container.register("svc", service=obj)
    assert container.get("svc") is obj
    assert container.get("svc") is obj


def test_singleton_factory_is_cached(container):
    container.register("s", factory=lambda: object(), singleton=True)
    a = container.get("s")
    b = container.get("s")
    assert a is b  # same instance every time


def test_non_singleton_factory_returns_fresh_instances(container):
    """The core bug: singleton=False used to be a no-op (cached like a singleton)."""
    container.register("f", factory=lambda: object(), singleton=False)
    a = container.get("f")
    b = container.get("f")
    assert a is not b  # fresh instance each get()


def test_non_singleton_factory_runs_every_call(container):
    calls = []
    container.register("f", factory=lambda: calls.append(1) or object(), singleton=False)
    container.get("f")
    container.get("f")
    container.get("f")
    assert len(calls) == 3


def test_unknown_service_raises(container):
    with pytest.raises(ValueError):
        container.get("nope")


def test_has_and_clear(container):
    container.register("a", service=object())
    container.register("b", factory=lambda: object())
    assert container.has("a") and container.has("b")
    container.clear()
    assert not container.has("a") and not container.has("b")


def test_factory_may_resolve_sibling_without_deadlock(container):
    """A factory that calls container.get(...) for another service must not
    self-deadlock (registry lock is reentrant)."""
    container.register("dep", factory=lambda: "DEP", singleton=True)
    container.register("main", factory=lambda: {"dep": container.get("dep")}, singleton=True)
    assert container.get("main") == {"dep": "DEP"}


def test_singleton_factory_built_once_under_concurrency(container):
    """Many threads resolving an uncreated singleton factory concurrently must get
    the SAME instance and run the factory exactly once (TOCTOU guard).

    The barrier synchronizes ENTRY into get() (not the factory body) so all
    threads race the check-then-create window at once; the fix must let only one
    of them run the factory."""
    build_count = []
    entry_barrier = threading.Barrier(20)

    def slow_factory():
        # Widen the race window WITHOUT depending on other threads reaching here
        # (only one thread should, thanks to the double-checked lock).
        time.sleep(0.02)
        build_count.append(1)
        return object()

    container.register("race", factory=slow_factory, singleton=True)

    results: list = []
    results_lock = threading.Lock()

    def worker():
        entry_barrier.wait()  # all threads hit get() at ~the same instant
        inst = container.get("race")
        with results_lock:
            results.append(inst)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(build_count) == 1, f"factory ran {len(build_count)} times, expected 1"
    assert all(r is results[0] for r in results), "threads got different instances"
