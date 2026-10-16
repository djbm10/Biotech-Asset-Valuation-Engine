#!/bin/sh
# Treatment and Search-B arms: replay the sealed Search-A baseline custody with each source index.
# Run in your own terminal (background shells get memory-reaped on this machine). ~1-1.5 h each.
set -e
cd "$(dirname "$0")/../.."
R="$HOME/se_runs/bd_cov_v1"; P=research/se_bd_discovery_source_coverage_v1/problems
for spec in A_full:A:full B_base:B:baseline B_full:B:full; do
  name=${spec%%:*}; rest=${spec#*:}; prob=${rest%%:*}; idx=${rest#*:}
  rm -rf "${R:?}/${name:?}"
  PYTHONPATH=src python -m bve.cli.se_search --problem "$P/search_$prob.yaml" \
    --source-index "$R/source_index_$idx.yaml" --replay-corpus "$R/A_base/custody" \
    --output-dir "$R/$name" --format shortlist --allow-incomplete > "$R/$name.log" 2>&1
  echo "$name done"
done
python research/se_bd_discovery_source_coverage_v1/measure.py research/se_bd_discovery_source_coverage_v1/results/A_compare.json A_base="$R/A_base" A_full="$R/A_full"
python research/se_bd_discovery_source_coverage_v1/measure.py research/se_bd_discovery_source_coverage_v1/results/B_compare.json B_base="$R/B_base" B_full="$R/B_full"
