"""Load exclusion-gate configuration from YAML.

The YAML file (``src/bve/config/exclusion_rules.yaml``) defines per-rule
metadata: gate order, rule IDs, descriptions, default status/cap/routing,
and eligibility flags.  The engine itself does not require the YAML to run
— all rule logic is hard-coded in ``rules.py``.  The YAML is used for:

  - Audit exports (which rules are defined and what their defaults are)
  - Operator overrides (disable a rule, lower a cap, change routing target)
  - Documentation generation

Usage::

    loader = ExclusionRuleConfigLoader()
    all_rules = loader.all_rules()
    rule = loader.get_rule("G4.FAILED_PIVOTAL_SALVAGE")
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_LOG = logging.getLogger("bve.intelligence.exclusions.config_loader")

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "exclusion_rules.yaml"
)


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------

class ExclusionRuleConfig(BaseModel):
    """Per-rule configuration loaded from exclusion_rules.yaml."""
    model_config = ConfigDict(frozen=True)

    rule_id: str
    gate_order: int
    gate_name: str
    description: str
    default_status: str
    default_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    routing_model: Optional[str] = None
    is_company_level: bool = True
    is_asset_level: bool = False
    is_pair_level: bool = False
    blocks_live_ranking: bool = True
    allows_historical_training: bool = True
    enabled: bool = True


class ExclusionGateConfig(BaseModel):
    """All rules for one gate."""
    model_config = ConfigDict(frozen=True)

    gate_id: str
    gate_order: int
    gate_name: str
    rules: list[ExclusionRuleConfig] = Field(default_factory=list)


class ExclusionRulesFile(BaseModel):
    """Top-level structure of exclusion_rules.yaml."""
    model_config = ConfigDict(frozen=True)

    version: str = "1.0"
    gates: list[ExclusionGateConfig] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class ExclusionRuleConfigLoader:
    """Load and cache exclusion rule configuration from YAML.

    Falls back to an empty rule set if the file does not exist so that the
    engine can still run without a config file present.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._rules_file: Optional[ExclusionRulesFile] = None

    def _load(self) -> ExclusionRulesFile:
        if self._rules_file is not None:
            return self._rules_file

        if not self._path.exists():
            _LOG.debug(
                "ExclusionRuleConfigLoader: config file not found at %s — using empty defaults",
                self._path,
            )
            self._rules_file = ExclusionRulesFile()
            return self._rules_file

        try:
            import yaml
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            self._rules_file = ExclusionRulesFile.model_validate(raw)
            _LOG.debug(
                "ExclusionRuleConfigLoader: loaded %d gates from %s",
                len(self._rules_file.gates),
                self._path,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "ExclusionRuleConfigLoader: failed to load config from %s: %s — using empty defaults",
                self._path,
                exc,
            )
            self._rules_file = ExclusionRulesFile()

        return self._rules_file

    def all_rules(self) -> list[ExclusionRuleConfig]:
        """Return all rules across all gates, in gate order."""
        rules: list[ExclusionRuleConfig] = []
        for gate in self._load().gates:
            rules.extend(gate.rules)
        return rules

    def get_rule(self, rule_id: str) -> Optional[ExclusionRuleConfig]:
        """Retrieve one rule by its rule_id (e.g. 'G4.FAILED_PIVOTAL_SALVAGE')."""
        for rule in self.all_rules():
            if rule.rule_id == rule_id:
                return rule
        return None

    def rules_for_gate(self, gate_id: str) -> list[ExclusionRuleConfig]:
        """Return all rules for a specific gate (e.g. 'gate_4_asset_viability')."""
        for gate in self._load().gates:
            if gate.gate_id == gate_id:
                return list(gate.rules)
        return []

    def enabled_rules(self) -> list[ExclusionRuleConfig]:
        """Return only rules with enabled=True."""
        return [r for r in self.all_rules() if r.enabled]
