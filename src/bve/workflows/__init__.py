"""Block 12 — Product Workflow & User Packaging.

Three end-to-end orchestration entry points that compose existing BVE
modules into day-in-the-life commands for BD professionals and analysts:

  evaluate_target  — complete single-company decision report
  morning_screen   — daily ranked screen across the universe
  init_asset       — scaffold minimum files for a new biotech company

All workflows are thin orchestrators: they load existing data, delegate to
existing report/scoring modules, and render Markdown. No new scoring logic
lives here.
"""
