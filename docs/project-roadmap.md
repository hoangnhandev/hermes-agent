# Project Roadmap

This document tracks the development phases, milestones, and progress of the Hermes agent.

## Current Focus: Specialized Research Skills

### Polymarket Signals Skill
A system for generating signals from prediction markets.

- [x] **Phase 00: Foundation & Storage**
    - Implement SQLite store with WAL and flock concurrency.
    - Establish basic project structure.
- [x] **Phase 01: Market Data Integration**
    - Implement Gamma API for market discovery.
    - Implement CLOB V1 for price fetching (midpoint/spread).
    - Implement resolution checking and outcome extraction.
- [x] **Phase 02: Signal Generation & Alerting**
    - Implement agent-driven LLM prediction (Mode B).
    - Implement prompt injection defense and randomized delimiters.
    - Implement Telegram-safe alert formatting with mandatory disclaimers.
- [ ] **Phase 03: Crowd Aggregates & Advanced Analysis**
    - Implement aggregation of multiple market signals.
    - Enhance calibration tracking.
- [ ] **Phase 04: Backtesting & Validation**
    - Develop a framework for validating signal accuracy against historical data.
- [ ] **Phase 05: Production Hardening**
    - Optimize for scale and reliability.
    - Implement advanced monitoring.

## Future Milestones

- [ ] **Enhanced Memory Architecture**: Implementation of more sophisticated holographic memory patterns.
- [ ] **Expanded Gateway Support**: Adding more messaging platforms and deeper integration.
- [ ] **Cross-Skill Synergy**: Enabling skills to collaborate and share data seamlessly.
