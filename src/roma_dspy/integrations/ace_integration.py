"""ACE (Agentic Context Engine) Integration for ROMA + PTC.

This module integrates ACE's learning capabilities with ROMA's PTCExecutor,
enabling the system to learn from each code generation task and improve over time.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Dict, Any, List
from loguru import logger
from pathlib import Path

try:
    from ace import (
        OnlineACE,
        Skillbook,
        Agent,
        Reflector,
        SkillManager,
        Sample,
        TaskEnvironment,
        EnvironmentResult,
        AgentOutput,
        AsyncLearningPipeline,
        ThreadSafeSkillbook,
        LiteLLMClient,
    )
    ACE_AVAILABLE = True
except ImportError:
    ACE_AVAILABLE = False
    logger.warning("ACE not available. Install with: pip install ace-framework")

from roma_dspy.core.modules.ptc_executor import PTCExecutor
from roma_dspy.types import TaskType


class CodeGenerationEnvironment(TaskEnvironment):
    """
    Environment for evaluating code generation tasks.

    Provides feedback based on:
    - Successful code generation
    - Syntax validity
    - Token efficiency
    - Cost effectiveness
    """

    def evaluate(self, sample: Sample, agent_output: AgentOutput) -> EnvironmentResult:
        """Evaluate code generation quality."""
        feedback_parts = []
        metrics = {}

        # Check if code was generated
        if not agent_output.final_answer or len(agent_output.final_answer) < 10:
            return EnvironmentResult(
                feedback="Code generation failed - no output produced",
                ground_truth=sample.ground_truth,
                metrics={"success": 0.0, "quality": 0.0},
            )

        # Parse metadata from agent output
        metadata = getattr(agent_output, 'metadata', {})

        # Success check
        success = "error" not in agent_output.final_answer.lower()[:200]
        metrics["success"] = 1.0 if success else 0.0
        feedback_parts.append("✅ Generated code" if success else "❌ Generation error")

        # Cost efficiency
        cost = metadata.get('cost_usd', 0.0)
        tokens = metadata.get('tokens_used', 0)
        if cost > 0:
            efficiency = 1.0 / (cost * 100)  # Lower cost = higher efficiency
            metrics["cost_efficiency"] = min(efficiency, 1.0)
            feedback_parts.append(f"💰 Cost: ${cost:.4f} ({tokens} tokens)")

        # Code quality heuristics
        code_length = len(agent_output.final_answer)
        has_comments = "#" in agent_output.final_answer or '"""' in agent_output.final_answer
        has_types = ":" in agent_output.final_answer and "->" in agent_output.final_answer

        quality_score = 0.0
        if code_length > 50:
            quality_score += 0.3
        if has_comments:
            quality_score += 0.4
        if has_types:
            quality_score += 0.3

        metrics["quality"] = quality_score
        feedback_parts.append(f"📊 Quality: {quality_score:.1%}")

        # Compare to ground truth if available
        if sample.ground_truth:
            matches_intent = sample.ground_truth.lower() in agent_output.final_answer.lower()
            metrics["intent_match"] = 1.0 if matches_intent else 0.5
            feedback_parts.append(
                "✅ Matches intent" if matches_intent else "⚠️ Partial intent match"
            )

        # Overall score
        overall = sum(metrics.values()) / len(metrics)
        metrics["overall"] = overall

        feedback = " | ".join(feedback_parts)
        if overall >= 0.8:
            feedback = f"🎉 Excellent! {feedback}"
        elif overall >= 0.6:
            feedback = f"✅ Good! {feedback}"
        else:
            feedback = f"⚠️ Needs improvement: {feedback}"

        return EnvironmentResult(
            feedback=feedback,
            ground_truth=sample.ground_truth,
            metrics=metrics,
        )


class ACEPTCAgent(Agent):
    """
    ACE-compatible wrapper for PTCExecutor.

    Translates between ACE's Sample format and PTCExecutor's interface.
    """

    def __init__(self, ptc_executor: PTCExecutor, llm_client: Optional[Any] = None):
        """
        Initialize ACE agent wrapper.

        Args:
            ptc_executor: The PTC executor to wrap
            llm_client: Optional LLM client (not used, PTCExecutor has its own)
        """
        super().__init__(llm_client=llm_client or "dummy")
        self.ptc_executor = ptc_executor

    async def forward(
        self,
        question: str,
        context: str = "",
        skillbook: Optional[Skillbook] = None,
    ) -> AgentOutput:
        """
        Execute code generation task using PTCExecutor.

        Args:
            question: The code generation task description
            context: Additional context (requirements, constraints)
            skillbook: Current skillbook with learned patterns

        Returns:
            AgentOutput with generated code and metadata
        """
        # Add skillbook context to the task if available
        enhanced_prompt = question
        if skillbook and len(skillbook.skills()) > 0:
            # Add learned patterns to prompt
            skills_summary = self._summarize_skills(skillbook)
            enhanced_prompt = f"{question}\n\n{skills_summary}"

        # Add context as requirements
        requirements = []
        if context:
            requirements = [line.strip() for line in context.split("\n") if line.strip()]

        # Execute via PTCExecutor
        try:
            result = await self.ptc_executor.aforward(
                goal=enhanced_prompt,
                requirements=requirements,
                task_type=TaskType.CODE_INTERPRET,
            )

            # Extract metadata
            metadata = {}
            if hasattr(result, '_metadata'):
                metadata = result._metadata

            # Format output
            final_answer = result.output if hasattr(result, 'output') else str(result)

            return AgentOutput(
                final_answer=final_answer,
                reasoning="",  # PTCExecutor doesn't expose reasoning steps
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"PTCExecutor error: {e}")
            return AgentOutput(
                final_answer=f"Error: {str(e)}",
                reasoning="",
                metadata={"error": str(e)},
            )

    def _summarize_skills(self, skillbook: Skillbook) -> str:
        """Summarize learned skills for prompt enhancement."""
        skills = skillbook.skills()
        if not skills:
            return ""

        # Take top 5 most relevant skills
        top_skills = list(skills[:5])

        summary_parts = ["Based on previous learnings:"]
        for skill in top_skills:
            # Each skill has name and description
            summary_parts.append(f"- {skill.name}: {skill.description}")

        return "\n".join(summary_parts)


class ACEIntegratedExecutor(PTCExecutor):
    """
    PTCExecutor with ACE learning capabilities.

    Automatically learns from each execution:
    - Successful patterns
    - Common pitfalls
    - Optimization strategies
    - Token efficiency techniques

    Usage:
        executor = ACEIntegratedExecutor(
            ptc_enabled=True,
            ptc_base_url="http://localhost:8002",
            ace_enabled=True,
            skillbook_path="./skillbooks/code_gen.json",
        )

        result = await executor.aforward("Create a FastAPI endpoint")
        # ACE learns in background, improves future executions
    """

    def __init__(
        self,
        *args,
        ace_enabled: bool = True,
        skillbook_path: Optional[str] = None,
        ace_model: str = "gpt-4o-mini",  # Cheap model for reflection
        async_learning: bool = True,  # Non-blocking learning
        **kwargs,
    ):
        """
        Initialize ACE-integrated executor.

        Args:
            ace_enabled: Whether to enable ACE learning
            skillbook_path: Path to load/save skillbook
            ace_model: LLM model for ACE reflection (cheap is fine)
            async_learning: Learn in background (recommended)
            *args, **kwargs: Passed to PTCExecutor
        """
        super().__init__(*args, **kwargs)

        self.ace_enabled = ace_enabled and ACE_AVAILABLE
        self.skillbook_path = Path(skillbook_path) if skillbook_path else None
        self.async_learning = async_learning

        if not self.ace_enabled:
            if not ACE_AVAILABLE:
                logger.warning("ACE not available - learning disabled")
            return

        # Initialize ACE components
        self._init_ace(ace_model)

        logger.info(
            f"ACE learning {'enabled' if self.ace_enabled else 'disabled'} "
            f"(async={async_learning})"
        )

    def _init_ace(self, ace_model: str):
        """Initialize ACE learning system."""
        # Load or create skillbook
        if self.skillbook_path and self.skillbook_path.exists():
            try:
                self.skillbook = Skillbook.load(str(self.skillbook_path))
                logger.info(f"Loaded skillbook with {len(self.skillbook.skills())} skills")
            except Exception as e:
                logger.warning(f"Failed to load skillbook: {e}")
                self.skillbook = Skillbook()
        else:
            self.skillbook = Skillbook()

        # Thread-safe wrapper for async learning
        if self.async_learning:
            self.skillbook = ThreadSafeSkillbook(self.skillbook)

        # Create LLM client for ACE
        self.ace_llm = LiteLLMClient(model=ace_model)

        # Create ACE components
        self.ace_agent = ACEPTCAgent(ptc_executor=self, llm_client=self.ace_llm)
        self.ace_reflector = Reflector(llm_client=self.ace_llm)
        self.ace_skill_manager = SkillManager(llm_client=self.ace_llm)
        self.ace_environment = CodeGenerationEnvironment()

        # Create ACE learning loop
        self.ace_loop = OnlineACE(
            skillbook=self.skillbook,
            agent=self.ace_agent,
            reflector=self.ace_reflector,
            skill_manager=self.ace_skill_manager,
            async_learning=self.async_learning,
            max_reflector_workers=2,  # Limit concurrent learning
        )

    async def aforward(
        self,
        goal: str,
        task_type: Optional[TaskType] = None,
        **kwargs: Any
    ) -> Any:
        """
        Execute with ACE learning.

        Wraps standard execution with ACE's learn-from-experience loop.
        """
        if not self.ace_enabled:
            # No ACE - use standard execution
            return await super().aforward(goal=goal, task_type=task_type, **kwargs)

        # Create ACE sample
        sample = Sample(
            question=goal,
            context="\n".join(kwargs.get('requirements', [])),
            metadata={
                "task_type": task_type.value if task_type else "code",
                "language": kwargs.get('language', 'python'),
            },
        )

        # Execute with ACE (learns automatically)
        try:
            ace_result = await self.ace_loop.step(
                sample=sample,
                environment=self.ace_environment,
            )

            # Save skillbook if path specified
            if self.skillbook_path and len(self.skillbook.skills()) > 0:
                self._save_skillbook()

            # Extract result
            return self._convert_ace_result(ace_result)

        except Exception as e:
            logger.error(f"ACE execution error: {e}, falling back to standard")
            return await super().aforward(goal=goal, task_type=task_type, **kwargs)

    def _save_skillbook(self):
        """Save skillbook to disk (async-safe)."""
        try:
            if self.skillbook_path:
                self.skillbook_path.parent.mkdir(parents=True, exist_ok=True)

                # Handle thread-safe wrapper
                sb = self.skillbook
                if isinstance(sb, ThreadSafeSkillbook):
                    sb = sb._skillbook

                sb.save(str(self.skillbook_path))
                logger.debug(f"Saved skillbook ({len(sb.skills())} skills)")
        except Exception as e:
            logger.warning(f"Failed to save skillbook: {e}")

    def _convert_ace_result(self, ace_result):
        """Convert ACE result back to PTCExecutor format."""
        # ACE result contains agent_output
        agent_output = ace_result.agent_output

        # Return in PTCExecutor format
        import dspy
        return dspy.Prediction(
            output=agent_output.final_answer,
            sources=[f"PTC/ACE"],
            _metadata={
                **agent_output.metadata,
                "ace_enabled": True,
                "skills_used": len(self.skillbook.skills()),
                "environment_feedback": ace_result.environment_result.feedback,
                "performance_score": ace_result.performance_score,
            }
        )

    def get_learning_stats(self) -> Dict[str, Any]:
        """Get ACE learning statistics."""
        if not self.ace_enabled:
            return {"ace_enabled": False}

        skills = self.skillbook.skills() if hasattr(self.skillbook, 'skills') else []

        return {
            "ace_enabled": True,
            "total_skills_learned": len(skills),
            "skillbook_path": str(self.skillbook_path) if self.skillbook_path else None,
            "async_learning": self.async_learning,
        }


# Convenience function
def create_ace_executor(
    ptc_base_url: str = "http://localhost:8002",
    skillbook_path: str = "./skillbooks/roma_ptc.json",
    ace_model: str = "gpt-4o-mini",
    **kwargs,
) -> ACEIntegratedExecutor:
    """
    Create ACE-enabled PTCExecutor with sensible defaults.

    Args:
        ptc_base_url: PTC service URL
        skillbook_path: Where to save learned skills
        ace_model: Cheap model for reflection
        **kwargs: Additional PTCExecutor args

    Returns:
        ACEIntegratedExecutor ready to learn

    Example:
        >>> executor = create_ace_executor()
        >>> result = await executor.aforward("Create a REST API")
        >>> print(executor.get_learning_stats())
    """
    return ACEIntegratedExecutor(
        ptc_enabled=True,
        ptc_base_url=ptc_base_url,
        ace_enabled=True,
        skillbook_path=skillbook_path,
        ace_model=ace_model,
        async_learning=True,
        **kwargs,
    )
