#!/bin/sh
# Run ONE remaining arm of the BD coverage pilot: replay the sealed Search-A baseline custody
# with one source index. Never deletes anything: each attempt writes a new directory
# <arm>_<UTC timestamp> and refuses to start unless preflight.py passes (frozen hashes,
# full custody re-verification, ontology data, disk, >= 24 GB RAM).
#
#   research/se_bd_discovery_source_coverage_v1/run_replays.sh A_full|B_base|B_full
#
# Per attempt: <dir>.log (engine output with stage progress), <dir>.time (GNU time -v: peak
# RSS, wall clock), <dir>.exit (exit status), <dir>.mem.tsv (every 30 s, appended and closed
# on each write so a kill cannot erase it: UTC time, process-tree RSS kB, MemAvailable kB).
# An arm is complete when <dir>/result.json exists and <dir>.exit is 0. Run arms one at a time.
#
# The sealed baseline embeds absolute snapshot paths under /home/djmann/se_runs/bd_cov_v1;
# on another machine place (or symlink) the run directory at exactly that path.
set -eu
cd "$(dirname "$0")/../.."
STUDY=research/se_bd_discovery_source_coverage_v1
R="${BVE_COV_ROOT:-/home/djmann/se_runs/bd_cov_v1}"
case "${1:-}" in
  A_full) prob=A; idx=full ;;
  B_base) prob=B; idx=baseline ;;
  B_full) prob=B; idx=full ;;
  *) echo "usage: $0 A_full|B_base|B_full" >&2; exit 2 ;;
esac
if pgrep -f "[b]ve.cli.se_search --problem $STUDY" >/dev/null; then
  echo "another coverage arm is already running; run arms one at a time" >&2; exit 5
fi
python "$STUDY/preflight.py" --root "$R"
out="$R/${1}_$(date -u +%Y%m%dT%H%M%SZ)"
[ -e "$out" ] && { echo "refusing to overwrite $out" >&2; exit 4; }

sample() {  # $1 = pid of the engine's parent (GNU time)
  printf 'utc\ttree_rss_kb\tmem_available_kb\n' >> "$out.mem.tsv"
  while kill -0 "$1" 2>/dev/null; do
    pids=$(ps -eo pid=,ppid= | awk -v root="$1" '
      {parent[$1]=$2} END {keep[root]=1; changed=1
        while (changed) {changed=0; for (p in parent) if (!keep[p] && keep[parent[p]]) {keep[p]=1; changed=1}}
        for (p in keep) printf "%s,", p}')
    rss=$(ps -o rss= -p "${pids%,}" 2>/dev/null | awk '{s+=$1} END {print s+0}')
    avail=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$rss" "$avail" >> "$out.mem.tsv"
    sleep 30
  done
}

set +e
/usr/bin/time -v -o "$out.time" env PYTHONPATH=src python -m bve.cli.se_search \
  --problem "$STUDY/problems/search_$prob.yaml" \
  --source-index "$R/source_index_$idx.yaml" --replay-corpus "$R/A_base/custody" \
  --output-dir "$out" --format shortlist --progress --allow-incomplete > "$out.log" 2>&1 &
engine=$!
sample "$engine" &
sampler=$!
wait "$engine"
status=$?
kill "$sampler" 2>/dev/null
set -e
echo "$status" > "$out.exit"
echo "$1 -> $out exit=$status peak_rss_kb=$(grep 'Maximum resident' "$out.time" 2>/dev/null | awk '{print $NF}')"
exit "$status"
