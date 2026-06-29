# Project Changelog

This document records all significant changes, features, and fixes implemented in the Hermes agent.

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
