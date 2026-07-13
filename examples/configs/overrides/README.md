# Analyst confidential overrides

One file per ticker: `examples/configs/overrides/<TICKER>.yaml` (e.g. `BEAM.yaml`).
These are **confidential** and **git-ignored** — only this README and
`EXAMPLE.yaml.example` are committed.

## How it works

When `bve-asset` loads a config, `pipeline/config_resolver.load_resolved_config`
looks up the ticker (from `company.ticker`) and, if an override file exists here,
deep-merges its `confidential_overrides` onto the auto-generated config:

- dict keys recurse; list elements merge by index; a leaf override wins.
- Overriding any value driver (`asset` / `trials` / `market_model` / `company`)
  elevates `_meta.evidence_level` from `coarse` to `full`.
- The `private:` section is **never** merged into the engine config and never
  reaches `outputs/` — it is returned only in the resolver provenance for
  downstream memos/screens.

## Schema

See `EXAMPLE.yaml.example`. Copy it to `<TICKER>.yaml` and edit:

```bash
cp EXAMPLE.yaml.example BEAM.yaml
```
