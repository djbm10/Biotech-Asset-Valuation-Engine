# Phase 2 Manual Review CLI

Minimal, auditable manual-review workflow for assumption changes.

Tool: `bve-review-phase2`  
No web frontend; terminal-only workflow.

## What It Shows

`show` renders one review case with:
- source document metadata
- extracted event JSON
- extraction confidence score
- ambiguity flag
- extraction rationale
- mapping proposal details
- valuation before/after diff
- reviewer action history

## Commands

Create a case from existing artifacts:

```bash
bve-review-phase2 create-case \
  --case-id case-001 \
  --source-metadata /path/source_document.json \
  --extraction-result /path/extraction_result.json \
  --proposal /path/proposal.json \
  --valuation-diff /path/valuation_diff.json
```

Inspect the case:

```bash
bve-review-phase2 show --case-id case-001
```

Record reviewer action:

```bash
# approve
bve-review-phase2 act --case-id case-001 --action approve \
  --reviewer-id analyst-a --rationale "Evidence is sufficient"

# reject
bve-review-phase2 act --case-id case-001 --action reject \
  --reviewer-id analyst-a --rationale "Signal quality too weak"

# modify (requires override-value)
bve-review-phase2 act --case-id case-001 --action modify \
  --reviewer-id analyst-a --override-value 0.51 \
  --rationale "Use conservative adjustment" \
  --provenance tool=bve-review-phase2 --provenance channel=cli
```

List cases:

```bash
bve-review-phase2 list --status pending
```

## Persistence and Audit Trail

Store root: `outputs/intelligence_phase2/reviews/`
- `cases/<case_id>.json`: full review case state, current status, action history
- `actions.jsonl`: append-only action ledger with timestamps and provenance

Status transitions:
- `pending -> modify | approve | reject`
- `modified -> modify | approve | reject`
- `approved` and `rejected` are terminal
