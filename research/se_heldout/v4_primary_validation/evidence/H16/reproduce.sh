#!/bin/sh
# The exact command that produced this directory. A live run re-queries the
# sources; pass --replay-corpus custody/ to reproduce it from the sealed bytes.
bve-se-search --query 'Find clinical-stage LAG-3 antibodies for melanoma.' --therapeutic-area ONCOLOGY --as-of 2026-10-11 --source-index /home/djmann/se_runs/aacr_probe5/source_index.yaml --output-dir /home/djmann/se_runs/heldout_h16_v4 --format shortlist --top 20 --progress --allow-incomplete
