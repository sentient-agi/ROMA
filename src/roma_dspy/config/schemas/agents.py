"""Agent configuration schemas for ROMA-DSPy."""

from pydantic.dataclasses import dataclass
from pydantic import field_validator, model_validator
from typing import List, Dict, Any, Optional

from roma_dspy.config.schemas.base import LLMConfig
from roma_dspy.config.schemas.toolkit import ToolkitConfig
from roma_dspy.types import PredictionStrategy, AgentType, TaskType
from roma_dspy.types.artifact_injection import ArtifactInjectionMode
from roma_dspy.tools.base.manager import ToolkitManager


@dataclass
class AgentConfig:
    """Configuration for an individual agent."""

    llm: Optional[LLMConfig] = None
    prediction_strategy: str = "chain_of_thought"
    toolkits: Optional[List[ToolkitConfig]] = None
    agent_type: Optional[AgentType] = None  # Set internally by AgentsConfig
    enabled: bool = True

    # NEW: Agent type and task type classification (using enum types)
    type: Optional[AgentType] = None  # Agent type (ATOMIZER, PLANNER, EXECUTOR, AGGREGATOR, VERIFIER)
    task_type: Optional[TaskType] = None  # Task type (RETRIEVE, WRITE, THINK, CODE_INTERPRET, IMAGE_GENERATION)

    # NEW: Artifact injection mode (controls which artifacts are visible in context)
    artifact_injection_mode: str = "full"  # none, dependencies, subtask, full

    # NEW: Inline signature support (OPTIONAL)
    signature: Optional[str] = None  # e.g., "goal -> is_atomic: bool, node_type: NodeType"
    signature_instructions: Optional[str] = None  # Custom instructions (inline, Jinja file, or Python module)
    demos: Optional[str] = None  # Python module path to demo list (e.g., "module.path:VARIABLE")

    # Separate agent-specific and strategy-specific configurations
    agent_config: Optional[Dict[str, Any]] = None      # Agent business logic parameters
    strategy_config: Optional[Dict[str, Any]] = None   # Prediction strategy algorithm parameters

    def __post_init__(self):
        """Initialize nested configs with defaults if not provided."""
        if self.llm is None:
            self.llm = LLMConfig()
        if self.toolkits is None:
            self.toolkits = []
        if self.agent_config is None:
            self.agent_config = {}
        if self.strategy_config is None:
            self.strategy_config = {}

        # Normalize signature: empty string becomes None
        if self.signature is not None and self.signature.strip() == "":
            object.__setattr__(self, 'signature', None)

    @field_validator("type", mode="before")
    @classmethod
    def validate_agent_type(cls, v: Optional[str | AgentType]) -> Optional[AgentType]:
        """Validate and convert agent type to enum."""
        if v is None:
            return None
        if isinstance(v, AgentType):
            return v
        try:
            return AgentType.from_string(v)
        except ValueError:
            available = [agent_type.value for agent_type in AgentType]
            raise ValueError(f"Invalid agent type '{v}'. Available: {available}")

    @field_validator("task_type", mode="before")
    @classmethod
    def validate_task_type(cls, v: Optional[str | TaskType]) -> Optional[TaskType]:
        """Validate and convert task type to enum."""
        if v is None:
            return None
        if isinstance(v, TaskType):
            return v
        try:
            return TaskType.from_string(v)
        except ValueError:
            available = [task_type.value for task_type in TaskType]
            raise ValueError(f"Invalid task type '{v}'. Available: {available}")

    @field_validator("artifact_injection_mode")
    @classmethod
    def validate_artifact_injection_mode(cls, v: str) -> str:
        """Validate artifact injection mode against available modes."""
        try:
            ArtifactInjectionMode.from_string(v)
            return v
        except ValueError:
            available = [mode.value for mode in ArtifactInjectionMode]
            raise ValueError(f"Invalid artifact injection mode '{v}'. Available: {available}")

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, v: Optional[str]) -> Optional[str]:
        """Normalize signature string (NO validation - factory handles fallback)."""
        if v is None or v.strip() == "":
            return None  # Empty = use default

        # Just normalize whitespace, don't validate format
        # Let the factory handle invalid signatures with fallback
        return v.strip()

    @field_validator("signature_instructions")
    @classmethod
    def validate_signature_instructions(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalize signature instructions string.

        Supports three formats:
        1. Inline string: Direct instruction text
           Example: "Classify the goal as ATOMIC or NOT"

        2. Jinja template file: Path to .jinja or .jinja2 file
           Example: "config/prompts/atomizer.jinja"

        3. Python module variable: Import variable from module
           Example: "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"

        Behavior when combined with signature:
        - Only signature_instructions: Keep codebase signature + inject instructions
        - Only signature: Override codebase signature with no instructions
        - Both: Override codebase signature + inject instructions

        Note: Actual loading/validation happens in AgentFactory for graceful fallback.
        """
        if v is None or v.strip() == "":
            return None

        # Just normalize, don't validate format
        # Let factory handle validation with fallback
        return v.strip()

    @field_validator("demos")
    @classmethod
    def validate_demos(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalize demos path string.

        Supports format:
        - Python module variable: Import variable from module
          Example: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"

        The variable must be a list of dspy.Example objects.

        Note: Actual loading/validation happens in AgentFactory for graceful fallback.
        """
        if v is None or v.strip() == "":
            return None

        # Basic format check: must contain ':'
        v_stripped = v.strip()
        if ":" not in v_stripped:
            raise ValueError(
                f"Invalid demos path format: '{v_stripped}'. "
                f"Expected format: 'module.path:VARIABLE_NAME'"
            )

        return v_stripped

    @field_validator("prediction_strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        """Validate prediction strategy against available strategies."""
        try:
            PredictionStrategy.from_string(v)
            return v
        except ValueError:
            available = [strategy.value for strategy in PredictionStrategy]
            raise ValueError(f"Invalid prediction strategy '{v}'. Available: {available}")

    @field_validator("toolkits")
    @classmethod
    def validate_toolkits(cls, v: Optional[List[ToolkitConfig]]) -> List[ToolkitConfig]:
        """Validate toolkit configurations."""
        if v is None:
            return []

        manager = ToolkitManager.get_instance()

        for toolkit_config in v:
            try:
                manager.validate_toolkit_config(toolkit_config)
            except Exception as e:
                raise ValueError(f"Invalid toolkit configuration: {e}")

        return v


@dataclass
class AgentsConfig:
    """Configuration for all ROMA agents."""

    atomizer: Optional[AgentConfig] = None
    planner: Optional[AgentConfig] = None
    executor: Optional[AgentConfig] = None
    aggregator: Optional[AgentConfig] = None
    verifier: Optional[AgentConfig] = None

    def __post_init__(self):
        """Initialize agent configs with defaults if not provided."""
        if self.atomizer is None:
            self.atomizer = AgentConfig(
                llm=LLMConfig(temperature=0.1, max_tokens=1000),
                prediction_strategy="chain_of_thought",
                toolkits=[],
                agent_config={"confidence_threshold": 0.8},
                strategy_config={},
                agent_type=AgentType.ATOMIZER
            )
        else:
            self.atomizer.agent_type = AgentType.ATOMIZER

        if self.planner is None:
            self.planner = AgentConfig(
                llm=LLMConfig(temperature=0.3, max_tokens=3000),
                prediction_strategy="chain_of_thought",
                toolkits=[],
                agent_config={"max_subtasks": 10},
                strategy_config={},
                agent_type=AgentType.PLANNER
            )
        else:
            self.planner.agent_type = AgentType.PLANNER

        if self.executor is None:
            self.executor = AgentConfig(
                llm=LLMConfig(temperature=0.5),
                prediction_strategy="chain_of_thought",  # Use CoT instead of ReAct for now
                toolkits=[],
                agent_config={"max_executions": 5},
                strategy_config={},
                agent_type=AgentType.EXECUTOR
            )
        else:
            self.executor.agent_type = AgentType.EXECUTOR

        if self.aggregator is None:
            self.aggregator = AgentConfig(
                llm=LLMConfig(temperature=0.2, max_tokens=4000),
                prediction_strategy="chain_of_thought",
                toolkits=[],
                agent_config={"synthesis_strategy": "hierarchical"},
                strategy_config={},
                agent_type=AgentType.AGGREGATOR
            )
        else:
            self.aggregator.agent_type = AgentType.AGGREGATOR

        if self.verifier is None:
            self.verifier = AgentConfig(
                llm=LLMConfig(temperature=0.1),
                prediction_strategy="chain_of_thought",
                toolkits=[],
                agent_config={"verification_depth": "moderate"},
                strategy_config={},
                agent_type=AgentType.VERIFIER
            )
        else:
            self.verifier.agent_type = AgentType.VERIFIER

    def get_config_for_agent(self, agent_type: AgentType) -> Optional[AgentConfig]:
        """
        Get configuration for a specific agent type.

        Args:
            agent_type: The type of agent to get configuration for

        Returns:
            AgentConfig if found, None otherwise
        """
        agent_map = {
            AgentType.ATOMIZER: self.atomizer,
            AgentType.PLANNER: self.planner,
            AgentType.EXECUTOR: self.executor,
            AgentType.AGGREGATOR: self.aggregator,
            AgentType.VERIFIER: self.verifier
        }
        return agent_map.get(agent_type)
