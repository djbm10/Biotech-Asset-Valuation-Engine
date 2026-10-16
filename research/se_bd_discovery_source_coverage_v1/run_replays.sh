#!/bin/sh
# Run ONE remaining arm of the BD coverage pilot: replay the sealed Search-A baseline custody
# with one source index. Never deletes anything: each attempt writes a new directory
# <arm>_<UTC timestamp>, and refuses to start if the frozen inputs' hashes have changed.
#
#   research/se_bd_discovery_source_coverage_v1/run_replays.sh A_full|B_base|B_full
#
# Records per attempt: <dir>.log (engine output), <dir>.time (GNU time -v: peak RSS, wall
# clock), <dir>.exit (exit status). An arm is complete when <dir>/result.json exists and
# <dir>.exit is 0. ~1-1.5 h and ~6 GB peak per arm. Run arms one at a time.
set -eu
cd "$(dirname "$0")/../.."
STUDY=research/se_bd_discovery_source_coverage_v1
R="$HOME/se_runs/bd_cov_v1"
case "${1:-}" in
  A_full) prob=A; idx=full ;;
  B_base) prob=B; idx=baseline ;;
  B_full) prob=B; idx=full ;;
  *) echo "usage: $0 A_full|B_base|B_full" >&2; exit 2 ;;
esac
sha256sum -c --quiet "$STUDY/frozen_inputs.sha256"
[ -f "$R/A_base/custody/corpus_seal.json" ] || { echo "baseline custody missing" >&2; exit 3; }
out="$R/${1}_$(date -u +%Y%m%dT%H%M%SZ)"
[ -e "$out" ] && { echo "refusing to overwrite $out" >&2; exit 4; }
set +e
/usr/bin/time -v -o "$out.time" env PYTHONPATH=src python -m bve.cli.se_search \
  --problem "$STUDY/problems/search_$prob.yaml" \
  --source-index "$R/source_index_$idx.yaml" --replay-corpus "$R/A_base/custody" \
  --output-dir "$out" --format shortlist --allow-incomplete > "$out.log" 2>&1
status=$?
set -e
echo "$status" > "$out.exit"
echo "$1 -> $out exit=$status peak_rss_kb=$(grep 'Maximum resident' "$out.time" | awk '{print $NF}')"
exit "$status"
