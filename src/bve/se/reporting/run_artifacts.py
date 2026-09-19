"""One run, one directory: the artifacts a search leaves behind and how it reports itself.

Every piece of this already existed as a separate flag -- ``--output``, ``--emit-problem``,
``--acquisition-ledger``, ``--snapshot-dir``, ``--custody-root``, ``--format shortlist`` --
and a user had to know all of them, and know which internal stage each belonged to, to end up
with a run they could read, audit and reproduce. This module is the wiring that turns that
knowledge into one flag. It invents nothing: the paths are conventions over the existing
writers, and the summary is composed from records the run already produces.

Two properties matter more than the layout:

- **A failed run still leaves its evidence.** The compiled problem and the exact reproduce
  command are written before acquisition starts, and the result, ledger and summary are
  written before the fail-closed exits. A run that ends UNSCOREABLE is then something you can
  read rather than something you have to re-run to understand.
- **Nothing here claims a stronger run status than the engine did.** ``CONVERGED`` from this
  pipeline means the seed queries were re-issued to the live source and produced no growth;
  the summary labels that ``LIVE`` so a future fast/local mode can never quietly inherit the
  word.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from bve.se.reporting.shortlist import Shortlist

#: What ``CONVERGED`` attests on this path. A cache-served convergence proof would be a
#: different claim and must be labelled differently rather than sharing this one.
CONVERGENCE_MODE_LIVE = "LIVE"
LIVE_CONVERGENCE_MEANING = (
    "LIVE: the seed queries were re-issued to the live sources and produced no new "
    "candidates. No local-fixpoint or cache-served mode exists; if one is added it must "
    "report its own mode and must not be scored as live convergence."
)


@dataclass(frozen=True)
class RunDirectory:
    """The deterministic layout of one run's artifacts."""

    root: Path

    @property
    def problem(self) -> Path:
        return self.root / "problem.yaml"

    @property
    def result(self) -> Path:
        return self.root / "result.json"

    @property
    def shortlist_text(self) -> Path:
        return self.root / "shortlist.txt"

    @property
    def shortlist_json(self) -> Path:
        return self.root / "shortlist.json"

    @property
    def memo(self) -> Path:
        return self.root / "memo.md"

    @property
    def run_manifest(self) -> Path:
        return self.root / "run_manifest.json"

    @property
    def acquisition_ledger(self) -> Path:
        return self.root / "acquisition_ledger.jsonl"

    @property
    def summary_text(self) -> Path:
        return self.root / "summary.txt"

    @property
    def summary_json(self) -> Path:
        return self.root / "summary.json"

    @property
    def command(self) -> Path:
        return self.root / "reproduce.sh"

    @property
    def invocation(self) -> Path:
        return self.root / "invocation.json"

    @property
    def log(self) -> Path:
        return self.root / "logs" / "run.log"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def custody(self) -> Path:
        return self.root / "custody"

    def prepare(self) -> None:
        """Create the directories the run writes into, before anything can fail."""

        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots.mkdir(parents=True, exist_ok=True)

    def has_producer(self) -> bool:
        """Whether some earlier process already produced evidence in this directory.

        A sealed custody root is the evidence. It is the same condition the custody
        boundary itself refuses to seal over, read here without being relaxed: this asks
        whether a producer exists, and never writes.
        """

        return self.custody.exists() and any(self.custody.iterdir())

    def record_invocation(
        self, argv: Sequence[str], *, program: str = "bve-se-search"
    ) -> None:
        """Claim the directory for this process, unless an earlier one already produced it.

        Once a run has sealed custody it is the producer of these artifacts, and a later
        process -- one that goes on to be refused at the custody boundary, or one that never
        reaches it -- must not be able to describe itself as the command that made them.
        """

        if self.has_producer() and self.invocation.exists():
            return
        self.invocation.write_text(
            json.dumps({"program": program, "argv": list(argv)}, indent=2) + "\n"
        )
        self.render_command()

    def render_command(self) -> None:
        """Write ``reproduce.sh`` from the persisted record, never from the live argv."""

        if not self.invocation.exists():
            return
        record = json.loads(self.invocation.read_text())
        line = " ".join(
            shlex.quote(part) for part in [record["program"], *record["argv"]]
        )
        self.command.write_text(
            "#!/bin/sh\n"
            "# The exact command that produced this directory. A live run re-queries the\n"
            "# sources; pass --replay-corpus custody/ to reproduce it from the sealed bytes.\n"
            f"{line}\n"
        )
        self.command.chmod(0o755)

    def relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


def summary_payload(
    *,
    run_id: str,
    query: str | None,
    problem_id: str,
    interpretation: Sequence[str],
    run_status: str,
    incomplete_reasons: Sequence[str],
    fatal_reasons: Sequence[str],
    shortlist: Shortlist | None,
    elapsed_seconds: float,
    stages: Sequence[tuple[str, float]] = (),
    directory: RunDirectory | None = None,
    exit_code: int | None = None,
) -> dict:
    """Everything the end-of-run summary says, as data. The text view renders this."""

    payload: dict = {
        "run_id": run_id,
        "problem_id": problem_id,
        "query": query,
        "interpretation": list(interpretation),
        "run_status": run_status,
        "convergence_mode": CONVERGENCE_MODE_LIVE,
        "convergence_meaning": LIVE_CONVERGENCE_MEANING,
        "incomplete_reasons": list(incomplete_reasons),
        "fatal_reasons": list(fatal_reasons),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "stages": [{"name": name, "seconds": round(seconds, 1)} for name, seconds in stages],
        "exit_code": exit_code,
    }
    if shortlist is not None:
        payload["counts"] = dict(shortlist.counts)
        payload["blind_spots"] = list(shortlist.blind_spots)
        payload["sources"] = [
            {"family": source.family, "outcome": source.outcome, "queries": source.queries}
            for source in shortlist.sources
        ]
        payload["top"] = [
            {
                "position": entry.position,
                "name": entry.name,
                "asset_id": entry.asset_id,
                "section": entry.section,
                "target_status": entry.target_status,
            }
            for entry in shortlist.entries
        ]
    if directory is not None:
        payload["artifacts"] = {
            name: directory.relative(path)
            for name, path in (
                ("problem", directory.problem),
                ("result", directory.result),
                ("shortlist", directory.shortlist_text),
                ("shortlist_json", directory.shortlist_json),
                ("memo", directory.memo),
                ("run_manifest", directory.run_manifest),
                ("acquisition_ledger", directory.acquisition_ledger),
                ("summary", directory.summary_text),
                ("log", directory.log),
                ("custody", directory.custody),
                ("reproduce", directory.command),
                ("invocation", directory.invocation),
            )
            if path.exists()
        }
        payload["artifact_root"] = str(directory.root)
    return payload


#: How many assets the end-of-run summary names. The counts describe the whole run, so this
#: is a glance at the top of the list, never a claim about its size.
SUMMARY_TOP = 5


def render_summary(payload: dict) -> str:
    """The end-of-run summary, in the order a reader needs it."""

    lines = [
        "",
        f"=== S&E run {payload['run_id']} ===",
    ]
    if payload.get("query"):
        lines.append(f"question: {payload['query']!r}")
        lines.extend(f"   {line}" for line in payload.get("interpretation", ()))
    else:
        lines.append(f"problem: {payload['problem_id']}")
    status = payload["run_status"]
    if payload.get("fatal_reasons"):
        lines.append(f"status: {status} -- UNSCOREABLE, a mandatory source failed")
        lines.extend(f"   - {reason}" for reason in payload["fatal_reasons"])
    else:
        lines.append(f"status: {status} (convergence mode {payload['convergence_mode']})")
        lines.extend(f"   - {reason}" for reason in payload.get("incomplete_reasons", ()))
    counts = payload.get("counts") or {}
    if counts:
        lines.append(
            "counts: "
            + ", ".join(
                f"{label} {counts.get(label, 0)}"
                for label in (
                    "eligible",
                    "review",
                    "excluded",
                    "low_support",
                    "total_candidates",
                )
            )
        )
    if payload.get("blind_spots"):
        # One per line: a run declares seven of these and joining them produces a paragraph
        # nobody reads, which defeats the point of declaring them.
        lines.append(f"blind spots ({len(payload['blind_spots'])}):")
        lines.extend(f"   - {spot}" for spot in payload["blind_spots"])
    failed = [
        source["family"]
        for source in payload.get("sources", ())
        if source["outcome"] in {"FAILED", "PARTIAL"}
    ]
    if failed:
        lines.append("sources not fully delivered: " + ", ".join(failed))
    top = payload.get("top") or []
    if top:
        lines.append(f"top {min(len(top), SUMMARY_TOP)} of {counts.get('shown', len(top))} shown:")
        for entry in top[:SUMMARY_TOP]:
            lines.append(
                f"   {entry['position']}. {entry['name']} "
                f"[{entry['section']}, target {entry['target_status']}]"
            )
    elif "counts" in payload:
        lines.append("no asset reached the shortlist")
    artifacts = payload.get("artifacts") or {}
    if artifacts:
        lines.append(f"artifacts in {payload['artifact_root']}:")
        lines.extend(f"   {name}: {path}" for name, path in artifacts.items())
    stages = payload.get("stages") or []
    if stages:
        lines.append(
            "stages: " + ", ".join(f"{s['name']} {s['seconds']}s" for s in stages)
        )
    lines.append(f"elapsed: {payload['elapsed_seconds']}s")
    return "\n".join(lines)


def write_summary(directory: RunDirectory, payload: dict) -> str:
    """Persist both views of the summary and return the text one."""

    text = render_summary(payload)
    directory.summary_json.write_text(json.dumps(payload, indent=2) + "\n")
    directory.summary_text.write_text(text + "\n")
    return text
