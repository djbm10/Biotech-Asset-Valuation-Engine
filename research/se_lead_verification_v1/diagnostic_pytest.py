"""Opt-in pytest GC timing probe; never enabled by the regular test suite."""

import gc
import json
import os
import time
from pathlib import Path

import pytest

TARGET = "test_flagging_does_not_scale_quadratically"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("BVE_GC_STOP_AFTER") != "1":
        return
    position = next(i for i, item in enumerate(items) if item.name == TARGET)
    deselected = items[position + 1 :]
    del items[position + 1 :]
    config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.name != TARGET:
        yield
        return
    cls = item.cls
    original = cls._shared
    rows = []

    def measured(count):
        events = []
        starts = {}

        def cb(phase, info):
            generation = info["generation"]
            if phase == "start":
                starts[generation] = time.perf_counter()
            else:
                events.append(
                    {
                        "generation": generation,
                        "seconds": time.perf_counter() - starts[generation],
                        "collected": info["collected"],
                    }
                )

        gc.callbacks.append(cb)
        start = time.perf_counter()
        cpu = time.process_time()
        try:
            return original(count)
        finally:
            wall = time.perf_counter() - start
            cpu = time.process_time() - cpu
            gc.callbacks.remove(cb)
            rows.append({"n": count, "wall": wall, "cpu": cpu, "gc": events})
            Path(os.environ["BVE_GC_DIAGNOSTIC_OUTPUT"]).write_text(json.dumps(rows, indent=2))

    cls._shared = staticmethod(measured)
    try:
        yield
    finally:
        cls._shared = staticmethod(original)
