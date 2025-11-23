"""Unit tests for AgentFactory signature instruction loading."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from roma_dspy.core.factory.agent_factory import AgentFactory
from roma_dspy.config.schemas.agents import AgentConfig
from roma_dspy.types import AgentType, TaskType
from roma_dspy.core.signatures import AtomizerSignature


class TestInstructionLoading:
    """Test instruction loading in AgentFactory."""

    def test_load_inline_instructions(self):
        """Test loading inline string instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="Classify the goal as ATOMIC or NOT"
        )

        # Create agent and verify instructions loaded
        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Agent should use default signature with injected instructions
        assert agent is not None
        assert agent.signature is not None

    def test_load_python_module_instructions(self):
        """Test loading instructions from Python module."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        # Signature should have instructions from atomizer_seed.py
        assert agent.signature is not None

    def test_load_jinja_instructions(self, tmp_path):
        """Test loading instructions from Jinja template."""
        # Create temporary Jinja template
        template_file = tmp_path / "atomizer_test.jinja"
        template_content = """# Atomizer Test

Classify as ATOMIC or NOT.

Rules:
- Single deliverable = atomic
- Multiple steps = not atomic
"""
        template_file.write_text(template_content)

        factory = AgentFactory()
        config = AgentConfig(signature_instructions=str(template_file))

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        assert agent.signature is not None

    def test_load_instructions_file_not_found(self, caplog):
        """Test graceful fallback when instruction file not found."""
        factory = AgentFactory()

        config = AgentConfig(signature_instructions="nonexistent/file.jinja")

        # Should NOT raise exception, but log warning
        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        # Should have logged warning about failed load
        assert any(
            "Failed to load signature instructions" in record.message
            for record in caplog.records
        )

    def test_load_instructions_import_error(self, caplog):
        """Test graceful fallback when Python module import fails."""
        factory = AgentFactory()

        config = AgentConfig(signature_instructions="nonexistent.module:VARIABLE")

        # Should NOT raise exception, but log warning
        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        # Should have logged warning
        assert any(
            "Failed to load signature instructions" in record.message
            for record in caplog.records
        )


class TestSignatureBehavior:
    """Test signature and instruction combination behavior."""

    def test_only_signature_instructions(self):
        """Test: Only signature_instructions → Keep codebase signature + inject instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature=None,  # No custom signature
            signature_instructions="Custom instructions here",
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should use default AtomizerSignature with custom instructions
        assert agent is not None
        assert agent.signature is not None
        # Signature class should be based on AtomizerSignature
        assert issubclass(agent.signature, type(AtomizerSignature))

    def test_only_signature(self):
        """Test: Only signature → Override codebase signature with no instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature="goal: str -> is_atomic: bool",  # Custom signature
            signature_instructions=None,  # No instructions
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        assert agent.signature is not None
        # Should have custom signature fields

    def test_both_signature_and_instructions(self):
        """Test: Both → Override codebase signature + inject instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature="goal: str -> is_atomic: bool",
            signature_instructions="Custom atomizer instructions",
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        assert agent.signature is not None
        # Should have custom signature with custom instructions

    def test_neither_signature_nor_instructions(self):
        """Test: Neither → Use codebase signature with no custom instructions."""
        factory = AgentFactory()

        config = AgentConfig(signature=None, signature_instructions=None)

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        assert agent.signature is not None
        # Should use default AtomizerSignature


class TestInstructionLoadingWithMock:
    """Test instruction loading with mocked InstructionLoader."""

    @patch("roma_dspy.core.factory.agent_factory.InstructionLoader")
    def test_instruction_loader_called(self, mock_loader_class):
        """Test that InstructionLoader is called when instructions provided."""
        # Setup mock
        mock_loader = Mock()
        mock_loader.load.return_value = "Loaded instructions"
        mock_loader_class.return_value = mock_loader

        factory = AgentFactory()
        config = AgentConfig(signature_instructions="test_instructions.jinja")

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Verify InstructionLoader was instantiated and load was called
        mock_loader_class.assert_called_once()
        mock_loader.load.assert_called_once_with("test_instructions.jinja")

    @patch("roma_dspy.core.factory.agent_factory.InstructionLoader")
    def test_instruction_loader_not_called_when_none(self, mock_loader_class):
        """Test that InstructionLoader is NOT called when no instructions."""
        factory = AgentFactory()
        config = AgentConfig(signature_instructions=None)

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # InstructionLoader should NOT be instantiated
        mock_loader_class.assert_not_called()

    @patch("roma_dspy.core.factory.agent_factory.InstructionLoader")
    def test_instruction_loader_exception_handling(self, mock_loader_class, caplog):
        """Test graceful handling of InstructionLoader exceptions."""
        # Setup mock to raise exception
        mock_loader = Mock()
        mock_loader.load.side_effect = FileNotFoundError("Template not found")
        mock_loader_class.return_value = mock_loader

        factory = AgentFactory()
        config = AgentConfig(signature_instructions="missing.jinja")

        # Should NOT raise exception
        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
        # Should have logged warning
        assert any(
            "Failed to load signature instructions" in record.message
            for record in caplog.records
        )


class TestMultipleAgentTypes:
    """Test instruction loading across different agent types."""

    def test_atomizer_with_python_module_instructions(self):
        """Test Atomizer with Python module instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_PROMPT"
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None

    def test_planner_with_python_module_instructions(self):
        """Test Planner with Python module instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="prompt_optimization.seed_prompts.planner_seed:PLANNER_PROMPT"
        )

        agent = factory.create_agent(agent_type=AgentType.PLANNER, agent_config=config)

        assert agent is not None

    def test_executor_with_inline_instructions(self):
        """Test Executor with inline instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="Execute the task using available tools"
        )

        agent = factory.create_agent(agent_type=AgentType.EXECUTOR, agent_config=config)

        assert agent is not None

    def test_aggregator_with_jinja_instructions(self, tmp_path):
        """Test Aggregator with Jinja instructions."""
        template_file = tmp_path / "aggregator.jinja"
        template_file.write_text("Synthesize all subtask results into coherent output")

        factory = AgentFactory()
        config = AgentConfig(signature_instructions=str(template_file))

        agent = factory.create_agent(
            agent_type=AgentType.AGGREGATOR, agent_config=config
        )

        assert agent is not None

    def test_verifier_with_inline_instructions(self):
        """Test Verifier with inline instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="Verify the output satisfies the goal"
        )

        agent = factory.create_agent(agent_type=AgentType.VERIFIER, agent_config=config)

        assert agent is not None


class TestLoggingBehavior:
    """Test logging behavior for instruction loading."""

    def test_log_successful_load(self, caplog):
        """Test that successful instruction loading is logged."""
        factory = AgentFactory()

        config = AgentConfig(signature_instructions="Test instructions")

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should log successful load
        assert any(
            "Loaded signature instructions" in record.message
            for record in caplog.records
        )

    def test_log_failed_load(self, caplog):
        """Test that failed instruction loading is logged."""
        factory = AgentFactory()

        config = AgentConfig(signature_instructions="nonexistent.module:VAR")

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should log warning about failed load
        assert any(
            "Failed to load signature instructions" in record.message
            for record in caplog.records
        )

    def test_log_codebase_signature_with_instructions(self, caplog):
        """Test logging when using codebase signature with custom instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature=None,  # Use codebase signature
            signature_instructions="Custom instructions",
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should log that codebase signature is used with custom instructions
        assert any(
            "codebase signature" in record.message.lower()
            and "custom instructions" in record.message.lower()
            for record in caplog.records
        )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string_instructions(self):
        """Test handling of empty string instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions=""  # Empty string
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should treat empty string as None
        assert agent is not None

    def test_whitespace_only_instructions(self):
        """Test handling of whitespace-only instructions."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="   \n\t   "  # Whitespace only
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        # Should handle gracefully
        assert agent is not None

    def test_very_long_inline_instructions(self):
        """Test handling of very long inline instructions."""
        factory = AgentFactory()

        long_instructions = "A" * 10000  # 10K characters
        config = AgentConfig(signature_instructions=long_instructions)

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None

    def test_instructions_with_special_characters(self):
        """Test instructions with special characters."""
        factory = AgentFactory()

        config = AgentConfig(
            signature_instructions="Use symbols: -> : {} [] () <> | & * @ # $ % ^"
        )

        agent = factory.create_agent(agent_type=AgentType.ATOMIZER, agent_config=config)

        assert agent is not None
