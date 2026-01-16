# Local Development on Apple Silicon

Configuration guide for running ROMA locally using Ollama on macOS (M-series chips).
Optimized for zero-egress privacy and local development.

## Requirements
*   macOS (Apple Silicon M1+)
*   16GB RAM (Recommended)
*   [Ollama](https://ollama.com/) installed

## Setup

1.  **Start Ollama Server**
    Ensure the Ollama server is running in the background.
    ```bash
    ollama serve
    ```

2.  **Pull Base Model**
    Standard profile uses Llama 3.1 8B.
    ```bash
    ollama pull llama3.1
    ```

## Usage

Use the `local_mac` profile, which sets appropriate timeouts (600s) and disables heavy toolkits to conserve resources.

```bash
# Run agent with local profile
python examples/basic_agent.py --profile local_mac
```

### Validation
To verify local-only execution (privacy check):

```bash
python examples/security_audit_demo.py
```

## Configuration Notes
*   **Timeouts:** Local inference can be significantly slower than cloud APIs. The `local_mac` profile extends `runtime.timeout` to 600s.
*   **Model Selection:** Default is `ollama_chat/llama3.1`. Modify `config/profiles/local_mac.yaml` to use other local models (e.g., Mistral, Gemma).
