#!/bin/bash
# No provisioning, retries, acquisition or provider credentials. Use only on authorized VM.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ "${BVE_AUTHORIZED_CLOUD:-}" = 'YES' ] || {
  echo 'Refusing: authorized cloud execution must be explicitly enabled.' >&2; exit 2;
}
[ "$(awk '/MemAvailable/ {print $2}' /proc/meminfo)" -ge 24000000 ] || {
  echo 'Refusing: need >=24 GB available RAM, in addition to original preflight.' >&2; exit 3;
}
root=/home/djmann/se_runs/bd_cov_v1
python research/se_pilot_handoff_v1/cloud_payload.py verify /srv/bve-payload
python research/se_pilot_handoff_v1/cloud_payload.py environment /srv/bve-payload
exec 9>"$root/.cloud-session.lock"
flock -n 9 || { echo 'Another cloud session holds the lock.' >&2; exit 4; }
[ -z "$(git status --porcelain -- src pyproject.toml research/se_bd_discovery_source_coverage_v1 research/se_pilot_handoff_v1)" ] || {
  echo 'Refusing changed engine/study files.' >&2; exit 5;
}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH=src
session="$root/cloud_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$session"
git rev-parse HEAD > "$session/code_head.txt"
python --version > "$session/python.txt"
# A single timeout bounds ALL arms plus scoring. Failure stops the session; no automatic retry.
# This bounds computation, NOT VM billing. Provider deletion remains separately required.
timeout --signal=TERM --kill-after=120s 36h bash -euo pipefail -c '
  root=$1; session=$2
  study=research/se_bd_discovery_source_coverage_v1
  for arm in A_full B_base B_full; do
    bash "$study/run_replays.sh" "$arm" | tee "$session/$arm.runner.log"
    # Resolve only the output named by this invocation, never newest-directory guessing.
    out=$(sed -n "s/^$arm -> \(.*\) exit=0 .*/\1/p" "$session/$arm.runner.log")
    test -n "$out" && test -s "$out/result.json" && test "$(cat "$out.exit")" = 0
    printf "%s\n" "$out" > "$session/$arm.path"
  done
  python "$study/measure.py" "$session/comparison_A.json" \
    "A_base=$root/A_base" "A_full=$(cat "$session/A_full.path")"
  python "$study/measure.py" "$session/comparison_B.json" \
    "B_base=$(cat "$session/B_base.path")" "B_full=$(cat "$session/B_full.path")"
  touch "$session/COMPLETE"
' -- "$root" "$session" > "$session/session.log" 2>&1
printf 'Completed session: %s\n' "$session"
