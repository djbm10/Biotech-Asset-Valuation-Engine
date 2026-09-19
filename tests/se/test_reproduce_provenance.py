"""``reproduce.sh`` names the process that produced the artifacts, or it names nothing.

The 2026-09-19 acceptance run exposed this. A run completed, sealed its custody and wrote
its artifacts. A second process was then launched into the same directory with one extra
flag; it wrote ``reproduce.sh`` at startup and was *correctly* refused moments later at the
custody boundary, because a sealed acquisition is immutable. The refusal worked. The
bookkeeping did not: the surviving directory then advertised a command that had never
produced anything, and the run that did produce it had its provenance silently overwritten
by a run that failed.

The rule these tests pin: the invocation is persisted once, by the process that claims the
directory, and ``reproduce.sh`` is *derived* from that persisted record rather than from
whatever argv the current process happens to hold. A directory that already holds a sealed
acquisition has a producer, and a later attempt cannot take its place -- whether that
attempt fails, succeeds, or never gets as far as the custody boundary.

Custody itself is not touched by any of this. Recording an invocation is bookkeeping about
a run; it must not create, read past, or relax the custody boundary.
"""

from __future__ import annotations

import json

from bve.se.reporting.run_artifacts import RunDirectory

PRODUCER = ["--query", "dual CD19/BCMA", "--output-dir", "/runs/one"]
LATECOMER = [*PRODUCER, "--allow-incomplete"]


def _sealed(directory: RunDirectory) -> None:
    """Stand in for a completed acquisition: a custody root with bytes in it."""

    directory.custody.mkdir(parents=True, exist_ok=True)
    (directory.custody / "corpus_seal.json").write_text("{}")


class TestTheScriptIsDerivedFromThePersistedInvocation:
    def test_the_invocation_is_persisted_at_run_start(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()

        directory.record_invocation(PRODUCER)

        record = json.loads(directory.invocation.read_text())
        assert record["argv"] == PRODUCER
        assert record["program"] == "bve-se-search"

    def test_the_script_says_what_the_persisted_record_says(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()

        directory.record_invocation(PRODUCER)

        script = directory.command.read_text()
        assert "bve-se-search --query 'dual CD19/BCMA'" in script
        assert "--allow-incomplete" not in script

    def test_the_script_is_rewritten_from_the_record_not_from_argv(self, tmp_path) -> None:
        # Deleting the script and re-deriving it must reproduce the *recorded* command.
        # This is what makes the record, rather than the live process, the authority.
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)
        directory.command.unlink()

        directory.render_command()

        assert "--allow-incomplete" not in directory.command.read_text()
        assert "--query 'dual CD19/BCMA'" in directory.command.read_text()


class TestARejectedRerunCannotTakeCreditForTheRun:
    """The exact 2026-09-19 incident, in both artifacts."""

    def test_a_later_invocation_cannot_overwrite_a_sealed_runs_script(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)
        _sealed(directory)

        directory.record_invocation(LATECOMER)

        script = directory.command.read_text()
        assert "--allow-incomplete" not in script, (
            "reproduce.sh advertised a flag the producing process never passed"
        )

    def test_a_later_invocation_cannot_overwrite_the_persisted_record(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)
        _sealed(directory)

        directory.record_invocation(LATECOMER)

        assert json.loads(directory.invocation.read_text())["argv"] == PRODUCER

    def test_the_refusal_does_not_depend_on_the_latecomer_failing(self, tmp_path) -> None:
        # The producer is decided at the moment the directory is claimed, not by which
        # process happens to exit first. A latecomer that went on to succeed would still
        # not be the process that produced these bytes.
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)
        _sealed(directory)

        directory.record_invocation(LATECOMER)
        directory.render_command()

        assert "--allow-incomplete" not in directory.command.read_text()


class TestADirectoryWithoutAProducerIsStillFree:
    def test_a_run_that_never_sealed_custody_can_be_reclaimed(self, tmp_path) -> None:
        # A run that died in argument parsing or discovery produced no evidence, so it has
        # no claim on the directory and a real run may still write its own provenance.
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)

        directory.record_invocation(LATECOMER)

        assert json.loads(directory.invocation.read_text())["argv"] == LATECOMER
        assert "--allow-incomplete" in directory.command.read_text()

    def test_an_empty_custody_directory_is_not_a_seal(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        directory.record_invocation(PRODUCER)
        directory.custody.mkdir(parents=True, exist_ok=True)

        directory.record_invocation(LATECOMER)

        assert json.loads(directory.invocation.read_text())["argv"] == LATECOMER


class TestCustodyIsUnchanged:
    def test_recording_an_invocation_never_creates_custody(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()

        directory.record_invocation(PRODUCER)

        assert not directory.custody.exists(), (
            "bookkeeping about a run must not bring the custody boundary into being"
        )

    def test_recording_an_invocation_never_writes_into_custody(self, tmp_path) -> None:
        directory = RunDirectory(tmp_path / "run")
        directory.prepare()
        _sealed(directory)
        before = sorted(path.name for path in directory.custody.iterdir())

        directory.record_invocation(PRODUCER)

        assert sorted(path.name for path in directory.custody.iterdir()) == before
