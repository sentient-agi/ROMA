# ROMA-DSPy Project Overview

This document provides a comprehensive overview of the ROMA-DSPy project, its structure, and how to interact with it.

## Project Overview

ROMA-DSPy is a Python-based framework for building hierarchical and recursive AI agents. It leverages the DSPy library to define and compose agents, and uses a recursive approach to break down complex tasks into smaller, manageable subtasks. The framework is designed to be highly configurable and extensible, allowing users to define their own agents, toolkits, and configurations.

The core of the framework is the `RecursiveSolver`, which orchestrates the execution of tasks. The solver uses a set of agents to perform different functions:

*   **Atomizer:** Determines if a task is atomic or needs to be broken down further.
*   **Planner:** Breaks down complex tasks into a series of subtasks.
*   **Executor:** Executes atomic tasks, potentially using toolkits to interact with external systems.
*   **Aggregator:** Aggregates the results of subtasks into a final answer.
*   **Verifier:** Verifies the final answer against the original goal.

## Building and Running

The project uses `just` as a command runner to simplify common tasks. The `justfile` in the root of the project provides a list of available commands.

### Docker

The recommended way to run the project is using Docker. The `docker-compose.yaml` file defines the services required to run the application, including a PostgreSQL database, MinIO for S3-compatible storage, and the ROMA-DSPy API server.

*   **Build and start all services:**
    ```bash
    just setup
    ```
*   **Start services without the setup wizard:**
    ```bash
    just docker-up
    ```
*   **Start services with MLflow for observability:**
    ```bash
    just docker-up-full
    ```
*   **Stop all services:**
    ```bash
    just docker-down
    ```

### Local Development

For local development, you can install the project and its dependencies using `pip`:

```bash
pip install -e .
```

To run the tests:

```bash
just test
```

To run the linter:

```bash
just lint
```

To run the type checker:

just typecheck

### CLI

The project provides a command-line interface for interacting with the framework. The main command is `solve`, which takes a task as input and returns the result.

*   **Solve a task:**
    ```bash
    roma-dspy solve "What is the capital of France?"
    ```
*   **Solve a task with a specific profile:**
    ```bash
    roma-dspy solve "Analyze the latest financial news" --profile crypto_agent
    ```

## Development Conventions

*   **Configuration:** The project uses OmegaConf for layered configuration. Configuration files are located in the `config` directory. The `general.yaml` profile provides a good starting point for understanding the configuration options.
*   **Testing:** The project uses `pytest` for testing. Tests are located in the `tests` directory, and are organized into `unit` and `integration` tests.
*   **Code Style:** The project uses `ruff` for linting and formatting.
*   **Type Checking:** The project uses `mypy` for static type checking.
*   **Toolkits:** The framework can be extended with toolkits, which are collections of tools that can be used by agents. Toolkits are located in the `src/roma_dspy/tools` directory.
