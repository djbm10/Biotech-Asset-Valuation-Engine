#!/bin/sh
# usage: replay.sh <label> <problem.yaml>   -- development replay on the sealed GUCY2C corpus
set -u
L=$1; P=$2; R=$HOME/se_runs/gucy2c_dev_v1/$L
mkdir -p $R
cd /home/djmann/projects/bve-b8
git rev-parse HEAD > $R/engine_commit.txt; git diff --stat > $R/engine_diff.txt
systemd-run --user --scope -q -p MemoryMax=4500M -p MemorySwapMax=0 \
  timeout 3h /usr/bin/time -v -o $R/run.time \
  .venv/bin/bve-se-search --problem $P --output-dir $R/run --format shortlist \
  --replay-corpus $HOME/se_runs/gucy2c_pilot_v1/run/custody > $R/run.stdout 2> $R/run.stderr
echo $? > $R/run.exit
