"""Tests for AlertsConfig loading and YAML round-trips."""
from __future__ import annotations

import yaml

from bve.alerts.alert_config import AlertsConfig
from bve.pipeline.watchlist_runner import WatchlistRunnerConfig


class TestAlertsConfig:
    def test_defaults_valid(self):
        cfg = AlertsConfig()
        assert cfg.enabled is True
        assert cfg.thresholds.material_change_abs_floor_millions == 25.0
        assert cfg.thresholds.material_change_pct == 15.0
        assert cfg.thresholds.low_confidence_threshold == 0.5
        assert cfg.local is None
        assert cfg.slack is None

    def test_disabled_config(self):
        cfg = AlertsConfig(enabled=False)
        assert cfg.enabled is False

    def test_local_channel_config(self):
        cfg = AlertsConfig.model_validate(
            {"local": {"output_path": "/tmp/alerts.jsonl", "min_severity": "low"}}
        )
        assert cfg.local is not None
        assert cfg.local.output_path == "/tmp/alerts.jsonl"

    def test_slack_config_env_expansion(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK", "https://hooks.slack.com/test")
        cfg = AlertsConfig.model_validate(
            {"slack": {"webhook_url": "${SLACK_WEBHOOK}"}}
        )
        assert cfg.slack.webhook_url == "https://hooks.slack.com/test"

    def test_thresholds_overrides(self):
        cfg = AlertsConfig.model_validate(
            {
                "thresholds": {
                    "material_change_abs_floor_millions": 50.0,
                    "material_change_pct": 20.0,
                    "low_confidence_threshold": 0.3,
                }
            }
        )
        assert cfg.thresholds.material_change_abs_floor_millions == 50.0
        assert cfg.thresholds.material_change_pct == 20.0
        assert cfg.thresholds.low_confidence_threshold == 0.3


class TestWatchlistRunnerConfigWithAlerts:
    _BASE_YAML = """
polling_interval_seconds: 3600
state_path: outputs/test/state.json
knowledge_db_path: outputs/test/knowledge.db
valuation_output_dir: outputs/test/watchlist
watchlist:
  - company_id: co-1
    asset_id: asset-1
"""

    def test_absent_alerts_leaves_none(self):
        raw = yaml.safe_load(self._BASE_YAML)
        cfg = WatchlistRunnerConfig.model_validate(raw)
        assert cfg.alerts is None

    def test_present_alerts_block_loaded(self):
        raw = yaml.safe_load(
            self._BASE_YAML
            + """
alerts:
  enabled: true
  thresholds:
    material_change_abs_floor_millions: 30.0
  local:
    output_path: outputs/test/alerts.jsonl
"""
        )
        cfg = WatchlistRunnerConfig.model_validate(raw)
        assert cfg.alerts is not None
        alerts_cfg = AlertsConfig.model_validate(
            cfg.alerts if isinstance(cfg.alerts, dict) else cfg.alerts.model_dump()
        )
        assert alerts_cfg.enabled is True
        assert alerts_cfg.local is not None

    def test_present_ranking_block_loaded(self):
        from bve.intelligence.ranking import RankingConfig

        raw = yaml.safe_load(
            self._BASE_YAML
            + """
ranking:
  top_n: 5
  recency_half_life_days: 7.0
"""
        )
        cfg = WatchlistRunnerConfig.model_validate(raw)
        assert cfg.ranking is not None
        rk = RankingConfig.model_validate(
            cfg.ranking if isinstance(cfg.ranking, dict) else cfg.ranking.model_dump()
        )
        assert rk.top_n == 5
        assert rk.recency_half_life_days == 7.0
