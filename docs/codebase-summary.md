# Codebase Summary

This document provides a high-level overview of the Hermes agent codebase structure and its core components.

## Project Structure

The codebase is organized into several primary directories:

- `agent/`: Contains the core logic for the AI agent, including memory management, tool orchestration, and session handling.
- `gateway/`: Manages connectivity and communication between the agent and various messaging platforms (e.g., Telegram, Discord, Slack).
- `hermes_cli/`: Provides the command-line interface for managing and interacting with the agent.
- `skills/`: A library of modular skills that extend the agent's capabilities. These are further categorized by domain (e.g., `research`, `creative`, `mlops`).
- `plugins/`: Extensible plugins that provide additional functionality or integrations.
- `tests/`: A comprehensive test suite covering unit, integration, and end-to-end tests.
- `web/`, `website/`, `ui-tui/`: Implementations of the web interface, public website, and terminal-based user interface.
- `docs/`: Technical documentation for the project.
- `plans/`: Implementation plans and research reports.

## Key Skills

### Google Ads Copilot (`skills/research/google-ads/`)

The `google-ads` skill is a budget-aware Google Ads management system for the
Vinfast VF3 campaign (Vietnam market), producing honest performance projections.

**Key Features:**
- **Strategy Engine**: Deterministic budget funnel (budget → clicks → leads → sales) from industry CPC/CVR benchmarks, all in VND.
- **Deployment Pipeline**: Four tools — `research` → `creator` → `deploy` → `monitor`/`optimize` — behind an async Telegram approval gate (no auto-spend).
- **Safety Guardrails**: Account-level monthly budget cap, landing-URL + keyword validation, orphan-campaign rollback, centralized VND↔micros conversion.
- **Observability**: Cron-driven metrics sync to Cloudflare D1 + read-only dashboard (`ads-copilot.withly.org`); monthly optimization review (winners/losers/wasted spend).
- **Money Safety**: All user-facing amounts in VND; `ACCOUNT_CURRENCY` env drives the VND↔micros conversion for the Google Ads API.

## Development Standards

- **Modularization**: Code is kept modular to ensure maintainability and scalability.
- **Testing**: High emphasis on test coverage and validation before deployment.
- **Documentation**: All major features and architectural changes are documented in the `./docs` directory.
