# Project Changelog

This document records all significant changes, features, and fixes implemented in the Hermes agent.

## [2026-07-02]

### Changed
- **google-ads skill — closed the monitor→report→optimize loop** (plan `260702-0927-google-ads-flow-completion`, 8 wires). Skeleton had the schema/read-path; this wires the missing connections. Money-safety preserved: no new spend path.
    - **Wire 1**: `has_conversion_tracking` flag now derived from `GOOGLE_ADS_CONVERSION_ACTION_ID` env (placeholders rejected) and preserved across `save_campaign`/`reconcile_campaigns` (was reset to 0 every sync by `INSERT OR REPLACE`).
    - **Wire 2**: monitor now syncs keyword-level metrics (`keyword_view` GAQL) into `daily_metrics` as `entity_type='keyword'` (was campaign-only) — unblocks keyword CPA/CTR + optimize.
    - **Wire 3**: optimize emits concrete entity-typed actions (`SCALE_BUDGET`/`PAUSE_KEYWORD`/`ADD_NEGATIVE`/`PAUSE_CAMPAIGN`), recommend-only (`status='recommended'`, no auto-mutate), with name resolution + `magnitude`/`expected` columns.
    - **Wire 4**: detected anomalies now ping the Telegram report channel (best-effort, deduped per entity+type+day via `alert_sent`); Telegram outage never blocks sync.
    - **Wire 5 (full stack)**: D1 `anomalies` table + Workers `/api/sync` accepts them + GET `/api/anomalies` + dashboard "Anomaly Alerts" panel. `synced_to_d1` flag decoupled from `alert_sent`.
    - **Wire 6a**: deploy now applies campaign-level negative keywords from `keyword_seeds.negative` (`CampaignCriterion`, non-fatal).
    - **Wire 6b**: money-safety fix — real `google-ads.env` `MONTHLY_BUDGET` 500→5,000,000 VND (was read as 500 VND/mo, capping every deploy at near-zero); added `ACCOUNT_CURRENCY=VND`; non-blocking warn when `<1M`.
    - **Wire 6c**: anomaly "today" + daily-report "yesterday" now account-local (`ACCOUNT_TZ`, default Asia/Ho_Chi_Minh) to match `segments.date`; GAQL windows stay UTC.
    - Follow-ups from code review applied: `save_anomaly` idempotent per (entity,type,day) (no row accumulation during Telegram outage); sync.js anomaly inserts isolated per-row (one bad row no longer fails the whole sync).
    - Verified statically (compile + targeted integration tests); live API verify pending Developer Token (Test mode). SKILL.md updated.

## [2026-06-26]

### Added
- **Polymarket Signals Skill**: Implemented a calibration-driven prediction market signal system.
    - Added SQLite store with WAL+flock concurrency for safe data persistence.
    - Added Gamma API integration for market discovery.
    - Added CLOB V1 integration for real-time price fetching.
    - Added resolution tracking and outcome extraction.
    - Added LLM-driven signal generation (Mode B) with prompt injection defenses.
    - Added Telegram-safe alert formatting with mandatory "PAPER TRADE ONLY" disclaimers.
    - Signal-only implementation (no trading functionality).
