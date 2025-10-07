from agno.agent import Agent
from agno.models.litellm import LiteLLM # Or your preferred Agno model wrapper
from loguru import logger

from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import (
    PlanOutput, 
    # PlanModifierInput # The agent's process method won't directly take this, 
                      # but the prompt will be constructed from its fields.
)

# Attempt to import Enums for dynamic prompt population
try:
    from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskType, NodeType
    TASK_TYPES_STR = ", ".join([f"'{t.value}'" for t in TaskType])
    NODE_TYPES_STR = ", ".join([f"'{n.value}'" for n in NodeType])
    logger.debug(f"Dynamically loaded TASK_TYPES_STR: {TASK_TYPES_STR}")
    logger.debug(f"Dynamically loaded NODE_TYPES_STR: {NODE_TYPES_STR}")
except ImportError:
    logger.debug("Failed to import TaskType/NodeType dynamically. Using fallback hardcoded values.")
    # Fallback hardcoded values - ENSURE THESE MATCH YOUR ENUMS EXACTLY
    TASK_TYPES_STR = "'SEARCH', 'WRITE', 'THINK', 'CODE', 'REVIEW', 'ORGANIZE', 'COMMUNICATE', 'SYNTHESIZE', 'CRITIQUE', 'IMPROVE', 'TEST', 'OTHER'"
    NODE_TYPES_STR = "'PLAN', 'EXECUTE', 'AGGREGATE'"

# --- Plan Modifier Agent Definition ---

PLAN_MODIFIER_AGENT_NAME = "PlanModifier_Agno"
# Consider using a highly capable model for plan modification, as it's a complex reasoning task.
PLAN_MODIFIER_MODEL_NAME = "openrouter/anthropic/claude-4-sonnet"

# System prompt tailored for plan modification
PLAN_MODIFIER_SYSTEM_PROMPT = """
You are an expert AI assistant that refines and modifies existing task plans based on user feedback.
Your goal is to output a 'Revised Plan' in JSON format that incorporates the user's instructions while maintaining the overall objective.

You will be provided with:
1.  "Overall Objective": The main goal the original and revised plan must achieve.
2.  "Original Plan": The current list of sub-tasks, including their 'goal', 'task_type', 'node_type', and 'depends_on_indices' (0-based list of indices of tasks this task depends on within the current list).
3.  "User Modification Instructions": Text from the user describing desired changes to the "Original Plan".

Your task is to:
-   Carefully analyze the "User Modification Instructions".
-   Apply these instructions to the "Original Plan" to produce a "Revised Plan".
-   You can add new tasks, remove existing tasks, re-order tasks, or change the 'goal', 'task_type', or 'node_type' of existing tasks.
-   When adding or modifying tasks, ensure 'task_type' is one of: {TASK_TYPES_STR}.
-   Ensure 'node_type' is one of: {NODE_TYPES_STR}.
-   Ensure all task dependencies ('depends_on_indices') in the "Revised Plan" are logical, correct, and refer to the 0-based indices of tasks *within your newly proposed revised plan list*. If a task has no dependencies, 'depends_on_indices' should be an empty list [].
-   The "Revised Plan" must still work towards the "Overall Objective".
-   If the user's instructions are vague, ambiguous, or contradictory, try your best to interpret them reasonably or focus on the valid parts to improve the plan. If instructions are impossible to implement, you may state this clearly in a "notes" field within the JSON output (if you must deviate from strict JSON plan output, but aim for pure plan output).
-   The output MUST be a JSON object strictly conforming to the structure of the 'PlanOutput' model, specifically a dictionary with a single key "sub_tasks", where "sub_tasks" is a list of dictionaries. Each sub-task dictionary must contain "goal" (string), "task_type" (string), "node_type" (string), and "depends_on_indices" (list of integers).

Example of the required JSON output format:
{{
  "sub_tasks": [
    {{
      "goal": "Revised goal for task 1...",
      "task_type": "SEARCH",
      "node_type": "PLAN",
      "depends_on_indices": []
    }},
    {{
      "goal": "New task based on user feedback...",
      "task_type": "WRITE",
      "node_type": "EXECUTE",
      "depends_on_indices": [0]
    }}
  ]
}}

Respond ONLY with the JSON object for the "Revised Plan". Do not include any other text, preambles, or explanations.
"""

# Instantiate the Plan Modifier Agent
plan_modifier_agno_agent = None # Initialize to None
try:
    # Ensure the formatted prompt is created correctly before agent instantiation
    formatted_system_prompt = PLAN_MODIFIER_SYSTEM_PROMPT.format(
        TASK_TYPES_STR=TASK_TYPES_STR,
        NODE_TYPES_STR=NODE_TYPES_STR
    )

    model_instance = LiteLLM(
        id=PLAN_MODIFIER_MODEL_NAME,
    )


    plan_modifier_agno_agent = Agent(
        model=model_instance,
        name=PLAN_MODIFIER_AGENT_NAME,
        description="An agent that modifies an existing task plan based on user feedback.",
        system_message=formatted_system_prompt,
        response_model=PlanOutput,
        markdown=False
    )
    
    logger.info(f"Successfully initialized {PLAN_MODIFIER_AGENT_NAME} with model {PLAN_MODIFIER_MODEL_NAME}")

except ImportError as ie:
    logger.error(f"Failed to import enums for PlanModifierAgent prompt. Please ensure TaskType and NodeType are accessible or hardcode them. {ie}")
except KeyError as ke:
    logger.error(f"A key used in PLAN_MODIFIER_SYSTEM_PROMPT.format() was not found. This might be TASK_TYPES_STR or NODE_TYPES_STR if dynamic loading failed. Error: {ke}")
    logger.debug(f"TASK_TYPES_STR was: '{TASK_TYPES_STR}'")
    logger.debug(f"NODE_TYPES_STR was: '{NODE_TYPES_STR}'")
except Exception as e:
    logger.error(f"Could not initialize PlanModifier_Agno agent: {e}")
    import traceback
    logger.error(traceback.format_exc())
