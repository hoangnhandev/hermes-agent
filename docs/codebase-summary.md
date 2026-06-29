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

### Polymarket Signals (`skills/research/polymarket-signals/`)

The `polymarket-signals` skill is a calibration-driven prediction market signal system designed to identify and alert on significant market movements and predictions.

**Key Features:**
- **Data Persistence**: Uses a SQLite store with WAL (Write-Ahead Logging) and flock concurrency for efficient and safe data management.
- **Market Discovery**: Integrates with the Gamma API to discover events based on specific tag slugs.
- **Price Analysis**: Fetches real-time price data from CLOB V1 endpoints, calculating midpoints and spreads.
- **Resolution Tracking**: Monitors market resolutions and extracts outcomes, with quarantine mechanisms for void or non-binary markets.
- **LLM Prediction**: Employs an agent-driven prediction mode (Mode B) with robust prompt injection defenses and randomized delimiters to ensure prediction integrity.
- **Alerting**: Generates Telegram-safe alerts with a mandatory "UNCALIBRATED — PAPER TRADE ONLY" disclaimer to ensure responsible usage.
- **Signal-Only Implementation**: Focused exclusively on signal generation; does not handle trading keys or order placement.

## Development Standards

- **Modularization**: Code is kept modular to ensure maintainability and scalability.
- **Testing**: High emphasis on test coverage and validation before deployment.
- **Documentation**: All major features and architectural changes are documented in the `./docs` directory.
