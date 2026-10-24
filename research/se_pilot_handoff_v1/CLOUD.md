# Frozen coverage experiment: cloud runbook

Prepared 2026-10-23. No VM provisioned, no charges incurred. Only A_base is complete.
These commands are an operator handoff for execution after explicit paid-cloud authorization;
they are not a request for the user to run commands. The agent can execute them when authorized.

## Machine and cost

Prefer one x86-64 Linux CPU VM with 32 GB RAM, at least 40 GB free disk, no GPU,
no backups, no extra volumes, no autoscaling. A 32 GB shared CPU plan can be cheaper but
may be unavailable; an 8-vCPU/32-GB Hetzner CCX33 is a straightforward fallback.
Use Debian 12 and Python 3.11.17 (uv-managed interpreter); preserve the original absolute paths.

Official sources checked 2026-10-23:
- https://www.hetzner.com/cloud/ (cost-optimized availability is currently limited)
- https://www.hetzner.com/cloud/general-purpose/ (CCX33 specification, included local disk)
- https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
  (EU CCX33 EUR 0.2219/hour, excluding IPv4/tax; CX53 EUR 0.0473/hour if available)
- https://docs.hetzner.com/cloud/billing/faq/ (stopped servers still bill until deleted)

Planning estimate, NOT measured runtime: 12–36 hours for three sequential arms, plus up
to 4 hours setup/retrieval. At EUR 0.2219/hour: EUR 3.55–8.88 for 16–40 hours.
A 48-hour ceiling is EUR 10.65 compute; request an all-in budget of EUR 15 including tax
and small IPv4 charges, subject to live checkout confirmation. Included local disk means
EUR 0 additional storage. Payload about 1.5 GB plus ontology; budget 10 GB return transfer,
well below EU included traffic, so expected extra transfer EUR 0. No snapshots/backups or
object storage are required. API cost EUR 0: sealed replay has an explicit network guard;
no acquisition or paid LLM calls. Dependency downloads are the only required runtime setup
network traffic. 32 GB sufficiency remains unmeasured.

A process timeout is NOT a billing cap. Before provisioning, authorization must cover one
VM, maximum checkout rate/all-in budget, 48-hour deletion deadline and retrieval procedure.
Set a provider budget alert and schedule the operator/agent to collect and delete the VM
before that deadline. If reliable teardown supervision is unavailable, do not provision.
No provider token goes into the VM or payload. No unattended automatic retries.

## 1. Prepare locally (implemented; no cloud access)

From the committed repository, with a NEW destination:

```bash
.venv/bin/python research/se_pilot_handoff_v1/cloud_payload.py prepare /tmp/bve-cloud-payload-final-v1
.venv/bin/python research/se_pilot_handoff_v1/cloud_payload.py verify /tmp/bve-cloud-payload-final-v1
sha256sum /tmp/bve-cloud-payload-final-v1/manifest.json
```

The manifest records code HEAD, Python version, exact installed package versions and every
payload file's bytes/hash. It copies A_base (including result, custody, snapshots and manifest),
corpus_A, both frozen source indexes, acquisition report and all ontology files. Symlinks in
ontology are dereferenced. The source corpus is retained for audit even though replay consumes
the sealed baseline and embedded source-index text. Prior failed attempts are retained locally
but not transferred. No home directory, Git credentials, .env, .claude, .serena, AGENTS edits,
meeting notes or advice files are packaged. Copying/hash verification streams bytes.

Inspect `manifest.json` before transfer. Save its SHA-256 separately, to authenticate the
manifest on receipt. Code comes from the already-authorized repository at that exact HEAD;
do not copy the working tree or credentials to cloud.

## 2. Transfer/setup (requires cloud authorization)

Use SSH keys and verify the host fingerprint through the provider console. Restrict inbound
SSH to the operator's address. Use rsync over SSH (do not disable host-key checking):

```bash
rsync -a --partial --info=progress2 /tmp/bve-cloud-payload-final-v1/ bve@HOST:/srv/bve-payload/
```

On the authorized VM, administrator creates an unprivileged `bve` user and gives it ownership
of empty `/srv/bve-payload`, `/home/djmann/se_runs` and `/home/djmann/projects` directories.
Install `git`, `rsync`, `time`, `procps`, `util-linux`, `coreutils` and `uv` using the provider
image/package procedure. Confirm uv supply provenance before using its managed interpreter.
Clone the repository without embedding a token in a command/URL; for a private repository use
a temporary read-only deploy key and revoke it after cloning.

```bash
git clone https://github.com/djbm10/Biotech-Asset-Valuation-Engine.git /home/djmann/projects/bve-b8
cd /home/djmann/projects/bve-b8
# First authenticate manifest.json against the hash retained locally.
PIN=$(python3 -c 'import json; print(json.load(open("/srv/bve-payload/manifest.json"))["code_head"])')
git checkout --detach "$PIN"
python3 research/se_pilot_handoff_v1/cloud_payload.py verify /srv/bve-payload
# Verify manifest SHA-256 against the locally retained value too.
sha256sum /srv/bve-payload/manifest.json
# These targets MUST NOT already exist. No merge, overwrite or deletion.
test ! -e /home/djmann/se_runs/bd_cov_v1
cp -a /srv/bve-payload/runs /home/djmann/se_runs/bd_cov_v1
# The TRACKED data symlink points at this other original checkout path.
# Create its target; do not replace the symlink or dirty the code checkout.
mkdir -p /home/djmann/projects/biotech-asset-valuation-engine/data/se
test ! -e /home/djmann/projects/biotech-asset-valuation-engine/data/se/ontology
cp -a /srv/bve-payload/ontology /home/djmann/projects/biotech-asset-valuation-engine/data/se/ontology
test -d data/se/ontology/current
uv python install 3.11.17
uv venv --python 3.11.17 .venv
uv pip install --python .venv/bin/python -r /srv/bve-payload/requirements.txt
uv pip install --python .venv/bin/python --no-deps -e .
source .venv/bin/activate
python -m pytest tests/se -q
python research/se_bd_discovery_source_coverage_v1/preflight.py
```

Exact versions are captured from the recovered environment, not the stale 3.12/2.12.5 notes.
Fresh cloud installation has not been tested: if a pinned wheel cannot be installed, stop and
diagnose; do not silently loosen versions. Preflight verifies the 14,194 embedded snapshot
paths at their original `/home/djmann/se_runs/bd_cov_v1/A_base` location. There is no path rewrite
or equivalence assumption. The cloned repo also retains its original absolute path for any
new replay snapshot paths. Do not bypass the 24 GB threshold.

## 3. Execute sequentially, collect and score

```bash
BVE_AUTHORIZED_CLOUD=YES bash research/se_pilot_handoff_v1/cloud_execute.sh
```

Use a persistent SSH terminal/session. The wrapper locks the session, requires >=24 GB
available RAM as well as the unchanged original preflight, limits numerical library threads,
and runs A_full, B_base, B_full sequentially within one 36-hour timeout. It writes a new
`cloud_TIMESTAMP` session with exact arm paths, logs, code/Python version and separate A/B
comparison JSONs. Original runner records per-arm time, memory samples and exit code.
Failure stops the sequence; incomplete output never gets scored. A completed wrapper has
`COMPLETE`. A timeout may leave partial artifacts; preserve them and inspect logs.

Keep the baseline manifest alongside the recovered-runtime pins: A_base lacks a full
historical dependency lock, so passing regression tests is not proof of cross-environment
replay equivalence. Review this provenance limitation before claiming a scientific conclusion.

The existing measure.py is invoked separately for A_base/A_full and B_base/B_full. It does
not itself declare a GO. Assess the preregistered success criterion from both comparisons,
including comparator promotion and wrong-target/modality findings. Run-level status and
source failures also need review; exit 0 with --allow-incomplete is not scientific completeness.

Before teardown, on cloud seal the return trees and retain the two manifest hashes separately:

```bash
python research/se_pilot_handoff_v1/cloud_payload.py seal /home/djmann/se_runs/bd_cov_v1
python research/se_pilot_handoff_v1/cloud_payload.py seal /home/djmann/projects/bve-b8/outputs/se
sha256sum /home/djmann/se_runs/bd_cov_v1/manifest.json /home/djmann/projects/bve-b8/outputs/se/manifest.json
```

These are additional transport manifests, not rewrites of nested custody manifests. If
`outputs/se` does not exist, no replay snapshots were written there; record that and omit
its seal/transfer. If an old transport manifest exists, stop and use a fresh collection tree.
Retrieve ALL run data and replay snapshots into a NEW local staging directory:

```bash
rsync -a --partial bve@HOST:/home/djmann/se_runs/bd_cov_v1/ /tmp/bve-cloud-return-v1/runs/
rsync -a --partial bve@HOST:/home/djmann/projects/bve-b8/outputs/se/ /tmp/bve-cloud-return-v1/repo_outputs_se/
```

Verify locally, comparing the manifest hashes with those retained from cloud:

```bash
.venv/bin/python research/se_pilot_handoff_v1/cloud_payload.py verify /tmp/bve-cloud-return-v1/runs
.venv/bin/python research/se_pilot_handoff_v1/cloud_payload.py verify /tmp/bve-cloud-return-v1/repo_outputs_se
sha256sum /tmp/bve-cloud-return-v1/runs/manifest.json /tmp/bve-cloud-return-v1/repo_outputs_se/manifest.json
``` Include every new custody seal and snapshot, not just result.json. The session's
`.path` files identify exactly which three directories were scored. Use fresh destinations
for a second attempt; never overwrite a historical run. Full post-transfer custody validation
requires restoring snapshot trees at the same original absolute paths; existing files must
match hashes, and only absent paths may be copied. Re-run `validate_seal(...,
verify_snapshots=True)` on each new arm. Do not mark a run accepted merely from COMPLETE.

## 4. Cleanup after verified retrieval

After return manifest, custody and result checks succeed, delete the paid VM in the provider
console/API under the authorized teardown plan, and release its IP. Confirm zero remaining
VMs, volumes, snapshots and backups for this job and inspect final billing. Power-off does
not stop billing. No local or historical data deletion is part of this procedure. If retrieval
fails, preserve partial local copies and resolve within the authorized deadline; extension
requires explicit authorization. This package deliberately contains no provisioning/deletion
API code or cloud credentials.
