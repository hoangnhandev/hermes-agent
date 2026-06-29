# System Architecture

This document describes the architectural design of the Hermes agent system.

## High-Level Architecture

The Hermes system follows a modular architecture designed for extensibility and scalability. The core components interact as follows:

### 1. Core Agent Logic (`agent/`)
The central intelligence of the system. It manages:
- **Session Management**: Tracking user interactions and state across different platforms.
- **Tool Orchestration**: Dynamically selecting and executing tools/skills based on user intent.
- **Memory**: Utilizing long-term and short-term memory to maintain context.

### 2. Gateway Layer (`gateway/`)
Acts as the communication bridge between the Core Agent and external platforms. It handles:
- **Protocol Translation**: Converting platform-specific messages (e.g., Telegram, Discord) into a common internal format.
- **Routing**: Directing incoming requests to the correct agent session.
- **Platform Adapters**: Implementing the specific APIs for each supported messaging service.

### 3. Skills Ecosystem (`skills/`)
A collection of specialized capabilities that the agent can invoke. Skills are designed to be independent and pluggable.

#### Research Skills
Skills focused on data gathering, analysis, and synthesis.

- **Polymarket Signals** (`skills/research/polymarket-signals/`):
    - **Function**: A calibration-driven prediction market signal system.
    - **Workflow**: Market Discovery $\to$ Price Fetching $\to$ LLM Prediction $\to$ Alert Generation.
    - **Key Components**: 
        - `store.py`: SQLite-based persistence.
        - `markets_client.py`: Gamma API integration.
        - `prices_client.py`: CLOB V1 integration.
        - `resolution_client.py`: Resolution tracking.
        - `predict.py`: LLM-driven signal generation.
    - **Safety**: Implements prompt injection defense and mandatory "PAPER TRADE ONLY" disclaimers.

## Data Flow

1. **Input**: A user sends a message via a supported platform (e.g., Telegram).
2. **Ingestion**: The **Gateway** receives the message and translates it into an internal event.
3. **Processing**: The **Core Agent** analyzes the event, retrieves relevant memory, and decides if a **Skill** is needed.
4. **Execution**: If required, the agent invokes a specific skill (e.g., `polymarket-signals`), which interacts with external APIs (Gamma, CLOB V1).
5. **Output**: The result is passed back to the agent, formatted by the gateway, and sent back to the user.

## Infrastructure

- **Storage**: Primarily SQLite for skill-specific state and potentially larger databases for core agent memory.
- **Concurrency**: Use of WAL mode and file locking to ensure data integrity across concurrent processes.
