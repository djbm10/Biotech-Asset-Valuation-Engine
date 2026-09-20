"""Draw the company-pipeline tranche mechanically, from a universe that already existed.

The selection rule is frozen before acquisition and is deliberately blind to the science.
A manifest assembled by picking companies whose programs look relevant to the benchmark it
is about to be measured against would answer that benchmark by construction, and the source
would never have been tested at all.

So the population is the engine's own tracked company universe -- built for the weekly BD
loop long before this source existed, and for entirely different reasons -- and the draw is a
hash ordering, which depends on the ticker and on nothing else. Re-running this script
reproduces the same tranche on any machine and in any Python.
"""

from __future__ import annotations

import hashlib

from bve.ops.weekly_runner import UNIVERSE

#: Fixed so the draw is reproducible and cannot be re-rolled until it looks better.
DRAW_SALT = "bve-company-pipeline-tranche-1"
TRANCHE_SIZE = 20


def tranche(size: int = TRANCHE_SIZE) -> list[str]:
    tickers = sorted({asset["ticker"] for asset in UNIVERSE} - {"NONE"})
    ranked = sorted(tickers, key=lambda t: hashlib.sha256(f"{DRAW_SALT}:{t}".encode()).hexdigest())
    return ranked[:size]


if __name__ == "__main__":
    for ticker in tranche():
        print(ticker)
