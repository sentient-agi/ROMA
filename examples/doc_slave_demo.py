
import asyncio
import logging
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.config.schemas.root import ROMAConfig
from roma_dspy.config.schemas.base import RuntimeConfig, LLMConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing background documentation generator...")

    # Local runtime configuration
    local_config = LLMConfig(
        model="ollama_chat/llama3.1",
        temperature=0.0,
        base_url="http://localhost:11434"
    )
    
    config = ROMAConfig(runtime=RuntimeConfig(timeout=3600))
    # Apply local config to all agents
    for agent in ['atomizer', 'planner', 'executor', 'aggregator', 'verifier']:
        getattr(config.agents, agent).llm = local_config

    solver = RecursiveSolver(config=config)
    target_file = "examples/security_audit_demo.py"

    with open(target_file, "r") as f:
        content = f.read()

    task_prompt = f"""
    Technical Writer Task:
    Generate a comprehensive docstring for the following Python script.
    include: Summary, Key Components, and Configuration Details.

    Script Content:
    ```python
    {content}
    ```
    """

    logger.info(f"Processing {target_file}...")
    try:
        result = await solver.async_solve(task_prompt)
        print("\n--- Generated Documentation ---\n")
        print(result.content)
    except Exception as e:
        logger.error(f"Generation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
