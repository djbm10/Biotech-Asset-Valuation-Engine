"""Diagnostic only. Run from repo root; --ontology retains the installed snapshot."""

import gc
import json
import runpy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
shared = runpy.run_path("tests/se/test_ontology_resolver.py")["TestWidelySharedAlias"]._shared
retained = None
if "--ontology" in sys.argv:
    from bve.se.ontology.targets import get_resolver

    retained = get_resolver()
    print("retained ontology", len(retained.entities()), flush=True)
for mode in ["normal", "precollect", "disabled"]:
    for repeat in range(3):
        if mode == "precollect":
            gc.collect()
        enabled = gc.isenabled()
        if mode == "disabled":
            gc.disable()
        measurements = []
        for count in [250, 2000]:
            events = []
            starts = {}

            def observe(phase, info, starts=starts, events=events):
                gen = info["generation"]
                if phase == "start":
                    starts[gen] = time.perf_counter()
                else:
                    events.append(
                        {
                            "generation": gen,
                            "seconds": time.perf_counter() - starts[gen],
                            "collected": info["collected"],
                        }
                    )

            gc.callbacks.append(observe)
            start = time.perf_counter()
            cpu = time.process_time()
            shared(count)
            wall = time.perf_counter() - start
            cpu = time.process_time() - cpu
            gc.callbacks.remove(observe)
            measurements.append({"n": count, "wall": wall, "cpu": cpu, "gc": events})
        if enabled:
            gc.enable()
        print(
            json.dumps({"mode": mode, "repeat": repeat, "measurements": measurements}), flush=True
        )
