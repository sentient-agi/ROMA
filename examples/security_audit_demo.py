
import asyncio
import logging
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.config.schemas.base import RuntimeConfig, LLMConfig

# Configure standard logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting local security audit...")

    # Configure local runtime
    local_config = LLMConfig(
        model="ollama_chat/llama3.1",
        temperature=0.0,
        base_url="http://localhost:11434"
    )
    
    config = ROMAConfig(runtime=RuntimeConfig(timeout=3600))
    for agent_config in [config.agents.atomizer, config.agents.planner, config.agents.executor, 
                        config.agents.aggregator, config.agents.verifier]:
        agent_config.llm = local_config

    solver = RecursiveSolver(config=config)

    with open("examples/vulnerable_code.py", "r") as f:
        target_code = f.read()

    task_prompt = f"""
    Security Audit Task:
    Scan the following Python code for hardcoded secrets (API keys, passwords).
    Return a list of findings with line numbers and variable names. Redact actual values.

    Code:
    ```python
    {target_code}
    ```
    """

    try:
        result = await solver.async_solve(task_prompt)
        print("\n--- Audit Report ---\n")
        print(result.content)
    except Exception as e:
        logger.error(f"Audit execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
