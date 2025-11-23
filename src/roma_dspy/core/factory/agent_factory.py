"""Factory for creating agent instances with signature fallback."""

from typing import Type, Optional, Dict, List, Any
import itertools
import dspy

from loguru import logger

from roma_dspy.core.modules import (
    Atomizer,
    Planner,
    Executor,
    Aggregator,
    Verifier,
    BaseModule,
)
from roma_dspy.core.signatures import (
    AtomizerSignature,
    PlannerSignature,
    ExecutorSignature,
    AggregatorSignature,
    VerifierSignature,
)
from roma_dspy.core.utils import InstructionLoader
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.types import AgentType, TaskType


class AgentFactory:
    """
    Factory for creating agent instances with signature fallback.

    Key Features:
    1. Default signatures for each agent type
    2. Inline signature parsing from config
    3. Graceful fallback on parsing errors
    4. Validation and error reporting
    """

    # Default signature mapping (includes Verifier)
    DEFAULT_SIGNATURES: Dict[AgentType, Type[dspy.Signature]] = {
        AgentType.ATOMIZER: AtomizerSignature,
        AgentType.PLANNER: PlannerSignature,
        AgentType.EXECUTOR: ExecutorSignature,
        AgentType.AGGREGATOR: AggregatorSignature,
        AgentType.VERIFIER: VerifierSignature,
    }

    # Module class mapping (includes Verifier)
    MODULE_CLASSES: Dict[AgentType, Type[BaseModule]] = {
        AgentType.ATOMIZER: Atomizer,
        AgentType.PLANNER: Planner,
        AgentType.EXECUTOR: Executor,
        AgentType.AGGREGATOR: Aggregator,
        AgentType.VERIFIER: Verifier,
    }

    _signature_counter = itertools.count()

    def create_agent(
        self,
        agent_type: AgentType,
        agent_config: AgentConfig,
        task_type: Optional[TaskType] = None,
    ) -> BaseModule:
        """
        Create agent instance with signature resolution.

        Signature Resolution Order:
        1. Try agent_config.signature (inline override)
        2. Fall back to default signature for agent_type
        3. On parsing error, log warning and use default

        Args:
            agent_type: Type of agent (ATOMIZER, PLANNER, EXECUTOR, AGGREGATOR, VERIFIER)
            agent_config: Configuration with optional signature override
            task_type: Task type for logging/debugging

        Returns:
            Configured agent instance

        Raises:
            ValueError: If agent_type is invalid or config is malformed
        """
        if agent_type not in self.MODULE_CLASSES:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # Resolve signature with fallback
        signature = self._resolve_signature(agent_type, agent_config, task_type)

        # Load demos from config (if provided)
        config_demos = self._load_demos(
            agent_type, getattr(agent_config, "demos", None)
        )

        # Get module class
        module_class = self.MODULE_CLASSES[agent_type]

        # Create instance with resolved signature and demos
        instance = module_class(
            signature=signature, config=agent_config, config_demos=config_demos
        )

        logger.info(
            f"Created {agent_type.value} agent "
            f"(task_type={task_type.value if task_type else 'default'}, "
            f"signature={'custom' if agent_config.signature else 'default'}, "
            f"demos={len(config_demos)})"
        )

        return instance

    def _resolve_signature(
        self,
        agent_type: AgentType,
        agent_config: AgentConfig,
        task_type: Optional[TaskType],
    ) -> Type[dspy.Signature]:
        """
        Resolve signature with robust fallback mechanism.

        Instruction Loading:
        - Supports inline strings, Jinja files (.jinja/.jinja2), and Python modules (module:VAR)
        - On load error, falls back to no instructions with warning

        Behavior:
        - Only signature_instructions: Keep codebase signature + inject instructions
        - Only signature: Override codebase signature with no instructions
        - Both: Override codebase signature + inject instructions
        - Neither: Use codebase signature with no instructions

        Returns:
            dspy.Signature class (either parsed or default)
        """
        default_signature = self.DEFAULT_SIGNATURES[agent_type]

        # Load signature instructions from any source (inline/file/module)
        loaded_instructions = self._load_instructions(
            agent_type, agent_config.signature_instructions
        )

        # No custom signature - use codebase signature with loaded instructions
        if not agent_config.signature:
            signature = self._clone_signature(default_signature, loaded_instructions)
            logger.debug(
                f"Using codebase signature for {agent_type.value}"
                f"{' with custom instructions' if loaded_instructions else ''}"
            )
            return signature

        # Custom signature - override codebase signature (with optional instructions)
        try:
            custom_signature = self._parse_inline_signature(
                agent_config.signature, loaded_instructions
            )

            logger.info(
                f"Using custom signature for {agent_type.value}: "
                f"{agent_config.signature}"
                f"{' with custom instructions' if loaded_instructions else ''}"
            )

            return custom_signature

        except Exception as e:
            # Parsing failed - fall back to default with warning
            logger.warning(
                f"Failed to parse inline signature for {agent_type.value} "
                f"(task_type={task_type}): {agent_config.signature}. "
                f"Error: {e}. Falling back to default signature."
            )

            return default_signature

    def _load_instructions(
        self, agent_type: AgentType, instructions: Optional[str]
    ) -> Optional[str]:
        """
        Load signature instructions from any source.

        Supports:
        1. Inline strings (passthrough)
        2. Jinja template files (.jinja, .jinja2)
        3. Python module variables (module.path:VARIABLE)

        Args:
            agent_type: Agent type for logging
            instructions: Instruction string (inline, file path, or module path)

        Returns:
            Loaded instruction text or None
        """
        if not instructions:
            return None

        try:
            loader = InstructionLoader()
            loaded = loader.load(instructions)
            logger.debug(
                f"Loaded signature instructions for {agent_type.value} "
                f"from: {instructions}"
            )
            return loaded

        except Exception as e:
            logger.warning(
                f"Failed to load signature instructions for {agent_type.value} "
                f"from '{instructions}': {e}. "
                f"Proceeding without custom instructions."
            )
            return None

    def _load_demos(
        self, agent_type: AgentType, demos_path: Optional[str]
    ) -> List[Any]:
        """
        Load few-shot demos from Python module variable.

        Supports:
        - Python module variables (module.path:VARIABLE)
          Example: "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"

        Args:
            agent_type: Agent type for logging
            demos_path: Demos path in format "module.path:VARIABLE"

        Returns:
            List of dspy.Example objects (or empty list on error)
        """
        if not demos_path:
            return []

        try:
            from roma_dspy.core.utils.demo_loader import DemoLoader

            loader = DemoLoader()
            loaded_demos = loader.load(demos_path)
            logger.debug(
                f"Loaded {len(loaded_demos)} demos for {agent_type.value} "
                f"from: {demos_path}"
            )
            return loaded_demos

        except Exception as e:
            logger.warning(
                f"Failed to load demos for {agent_type.value} "
                f"from '{demos_path}': {e}. "
                f"Proceeding without demos."
            )
            return []

    @staticmethod
    def _parse_inline_signature(
        signature_str: str, instructions: Optional[str] = None
    ) -> Type[dspy.Signature]:
        """
        Parse DSPy inline signature string.

        Formats supported:
        - "input -> output"
        - "input: type -> output: type"
        - "field1, field2: type -> output1, output2: type"

        Args:
            signature_str: Inline signature string
            instructions: Optional instructions for the signature

        Returns:
            dspy.Signature class

        Raises:
            ValueError: If signature_str is malformed

        Examples:
            >>> _parse_inline_signature("goal -> is_atomic: bool")
            >>> _parse_inline_signature(
            ...     "goal: str -> output: str, sources: list[str]",
            ...     instructions="Execute task with tools"
            ... )
        """
        if not signature_str or "->" not in signature_str:
            raise ValueError(
                f"Invalid signature format: '{signature_str}'. Must contain '->'"
            )

        # Clean signature string
        signature_str = signature_str.strip()

        # DSPy.Signature can be created from string directly
        if instructions:
            signature = dspy.Signature(signature_str, instructions=instructions)
        else:
            signature = dspy.Signature(signature_str)

        return signature

    @classmethod
    def get_default_signature(cls, agent_type: AgentType) -> Type[dspy.Signature]:
        """Get default signature for agent type (utility method)."""
        return cls.DEFAULT_SIGNATURES[agent_type]

    @classmethod
    def _clone_signature(
        cls, base_signature: Type[dspy.Signature], instructions: Optional[str]
    ) -> Type[dspy.Signature]:
        """
        Create a unique Signature subclass so each agent can mutate instructions independently.
        """
        attrs: Dict[str, object] = {"__module__": base_signature.__module__}
        if instructions:
            attrs["__doc__"] = instructions
        name = f"{base_signature.__name__}Instance{next(cls._signature_counter)}"
        return type(name, (base_signature,), attrs)
