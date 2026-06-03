"""
bve.backtest_research — no-lookahead historical M&A backtest research pipeline.

Modules
-------
source_registry        : Provenance schema and source reliability rules
deal_seed_loader       : Load and validate deal seeds (verified/unverified)
snapshot_dates         : Compute pre-announcement snapshot windows
leakage_guard          : Strict no-look-ahead enforcement before scoring
sec_client             : Point-in-time SEC EDGAR data with provenance
clinicaltrials_client  : Point-in-time ClinicalTrials.gov data with provenance
openfda_client         : Point-in-time FDA approval data with provenance
company_press_release_client : Parse raw press-release HTML/text files
historical_market_data_client : Point-in-time market cap via yfinance
deal_researcher        : Orchestrate per-deal research across all sources
acquirer_snapshot_builder : Build acquirer profiles as of snapshot date
target_snapshot_builder   : Build target profiles as of snapshot date
asset_snapshot_builder    : Build lead-asset profiles as of snapshot date
candidate_universe_builder : Find realistic alternative targets per deal
hard_negative_generator    : Generate hard negatives meeting all criteria
feature_store          : Assemble feature matrix with full provenance
rnpv_config_builder    : Generate rNPV YAML configs for each target snapshot
vrtx_regn_dataset_builder  : Main dataset-building CLI entrypoint
vrtx_regn_backtest_runner  : Leakage audit + scoring + ranking + metrics
report_writer          : Generate markdown report
"""
