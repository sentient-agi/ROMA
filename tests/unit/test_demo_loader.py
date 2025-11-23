"""Unit tests for DemoLoader."""

import pytest
from unittest.mock import patch, MagicMock
import dspy

from roma_dspy.core.utils.demo_loader import DemoLoader, load_demos


class TestDemoLoader:
    """Test suite for DemoLoader utility."""

    def test_load_valid_executor_demos(self):
        """Test loading valid EXECUTOR_DEMOS from seed prompts."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 10
        assert all(isinstance(d, dspy.Example) for d in demos)
        assert all(hasattr(d, "with_inputs") for d in demos)

    def test_load_valid_verifier_demos(self):
        """Test loading valid VERIFIER_DEMOS from seed prompts."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.verifier_seed:VERIFIER_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 11
        assert all(isinstance(d, dspy.Example) for d in demos)

    def test_load_valid_planner_demos(self):
        """Test loading valid PLANNER_DEMOS from seed prompts."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.planner_seed:PLANNER_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 4

    def test_load_valid_atomizer_demos(self):
        """Test loading valid ATOMIZER_DEMOS from seed prompts."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.atomizer_seed:ATOMIZER_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 6

    def test_load_aggregator_demos_empty(self):
        """Test loading AGGREGATOR_DEMOS (intentionally empty)."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.aggregator_seed:AGGREGATOR_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 0

    def test_invalid_module_path(self):
        """Test error handling for invalid module path."""
        loader = DemoLoader()

        with pytest.raises(ImportError) as excinfo:
            loader.load("nonexistent.module:DEMOS")

        assert "Cannot import module" in str(excinfo.value)
        assert "nonexistent.module" in str(excinfo.value)

    def test_invalid_format_missing_colon(self):
        """Test error handling for format missing colon."""
        loader = DemoLoader()

        with pytest.raises(ValueError) as excinfo:
            loader.load("just_a_string")

        # Check the actual error message format
        assert "Invalid demos path format" in str(excinfo.value)
        assert "Expected format" in str(excinfo.value)

    def test_invalid_format_empty_module(self):
        """Test error handling for empty module name."""
        loader = DemoLoader()

        with pytest.raises(ValueError) as excinfo:
            loader.load(":VARIABLE")

        assert "must be non-empty" in str(excinfo.value)

    def test_invalid_format_empty_variable(self):
        """Test error handling for empty variable name."""
        loader = DemoLoader()

        with pytest.raises(ValueError) as excinfo:
            loader.load("module.path:")

        assert "must be non-empty" in str(excinfo.value)

    def test_variable_not_found(self):
        """Test error handling when variable doesn't exist in module."""
        loader = DemoLoader()

        with pytest.raises(AttributeError) as excinfo:
            loader.load("prompt_optimization.seed_prompts.executor_seed:NONEXISTENT")

        assert "has no attribute" in str(excinfo.value)
        assert "NONEXISTENT" in str(excinfo.value)

    def test_variable_not_a_list(self):
        """Test error handling when variable is not a list."""
        loader = DemoLoader()

        with pytest.raises(TypeError) as excinfo:
            loader.load(
                "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_PROMPT"
            )

        assert "must be a list" in str(excinfo.value)
        assert "str" in str(excinfo.value)  # EXECUTOR_PROMPT is a string

    def test_empty_string_input(self):
        """Test error handling for empty string."""
        loader = DemoLoader()

        with pytest.raises(ValueError) as excinfo:
            loader.load("")

        assert "must be a non-empty string" in str(excinfo.value)

    def test_none_input(self):
        """Test error handling for None input."""
        loader = DemoLoader()

        with pytest.raises(ValueError) as excinfo:
            loader.load(None)

        assert "must be a non-empty string" in str(excinfo.value)

    def test_lru_cache_behavior(self):
        """Test that LRU cache works correctly."""
        loader = DemoLoader()

        # First load
        demos1 = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        # Second load (should hit cache)
        demos2 = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        # Should return the same object (from cache)
        assert demos1 == demos2
        assert len(demos1) == 10

    def test_clear_cache(self):
        """Test cache clearing."""
        loader = DemoLoader()

        # Load once
        demos1 = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        # Clear cache
        loader.clear_cache()

        # Load again (should reload, not hit cache)
        demos2 = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        # Should still be equal but reloaded
        assert demos1 == demos2
        assert len(demos2) == 10

    def test_load_demos_convenience_function(self):
        """Test the load_demos convenience function."""
        demos = load_demos(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        assert isinstance(demos, list)
        assert len(demos) == 10
        assert all(isinstance(d, dspy.Example) for d in demos)

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        loader = DemoLoader()

        # Path with extra whitespace
        demos = loader.load(
            "  prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS  "
        )

        # Should still load successfully (after strip)
        assert isinstance(demos, list)
        assert len(demos) == 10

    def test_multiple_colons_in_path(self):
        """Test handling of path with multiple colons (invalid)."""
        loader = DemoLoader()

        # Only first colon should be used as separator
        with pytest.raises((ImportError, AttributeError)):
            loader.load("module:sub:VARIABLE")

    @patch("roma_dspy.core.utils.demo_loader.importlib.import_module")
    def test_import_error_logged(self, mock_import):
        """Test that import errors are logged."""
        mock_import.side_effect = ImportError("Test import error")

        loader = DemoLoader()

        with pytest.raises(ImportError):
            loader.load("test.module:VARIABLE")

        mock_import.assert_called_once_with("test.module")

    def test_custom_demos_from_examples(self):
        """Test loading custom demos from examples module."""
        loader = DemoLoader()

        demos = loader.load("examples.custom_demos_example:MEDICAL_EXECUTOR_DEMOS")

        assert isinstance(demos, list)
        assert len(demos) == 3  # 3 medical demos
        assert all(isinstance(d, dspy.Example) for d in demos)

    def test_demo_structure_executor(self):
        """Test that loaded executor demos have correct structure."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )

        # Check first demo
        demo = demos[0]
        assert hasattr(demo, "goal")
        assert hasattr(demo, "output")
        assert hasattr(demo, "sources")

        # Verify it's been processed with with_inputs
        assert hasattr(demo, "with_inputs")

    def test_demo_structure_verifier(self):
        """Test that loaded verifier demos have correct structure."""
        loader = DemoLoader()
        demos = loader.load(
            "prompt_optimization.seed_prompts.verifier_seed:VERIFIER_DEMOS"
        )

        # Check first demo
        demo = demos[0]
        assert hasattr(demo, "goal")
        assert hasattr(demo, "candidate_output")
        assert hasattr(demo, "verdict")
        assert hasattr(demo, "feedback")

    def test_concurrent_loads(self):
        """Test that concurrent loads work correctly (thread safety)."""
        import concurrent.futures

        loader = DemoLoader()

        def load_demos():
            return loader.load(
                "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
            )

        # Load concurrently from multiple threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(load_demos) for _ in range(10)]
            results = [f.result() for f in futures]

        # All results should be successful and equal
        assert all(len(r) == 10 for r in results)
        assert all(r == results[0] for r in results)

    def test_base_path_parameter_exists(self):
        """Test that base_path parameter can be provided."""
        from pathlib import Path

        loader = DemoLoader(base_path=Path("/tmp"))

        # Should still work (base_path currently not used, but for API consistency)
        demos = loader.load(
            "prompt_optimization.seed_prompts.executor_seed:EXECUTOR_DEMOS"
        )
        assert len(demos) == 10


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_module_path(self):
        """Test with very long module path."""
        loader = DemoLoader()

        # This should fail with ImportError (module doesn't exist)
        long_path = ".".join(["very", "long", "module", "path"] * 10) + ":VARIABLE"

        with pytest.raises(ImportError):
            loader.load(long_path)

    def test_unicode_in_path(self):
        """Test with unicode characters in path."""
        loader = DemoLoader()

        # Should raise ImportError for non-existent module
        with pytest.raises(ImportError):
            loader.load("module_ñoño:VARIABLE")

    def test_special_characters_in_variable_name(self):
        """Test with special characters in variable name."""
        loader = DemoLoader()

        # Python variable names can't have special chars, should raise AttributeError
        with pytest.raises(AttributeError):
            loader.load("prompt_optimization.seed_prompts.executor_seed:EXECUTOR-DEMOS")

    def test_numeric_variable_name(self):
        """Test with numeric variable name (invalid Python identifier)."""
        loader = DemoLoader()

        with pytest.raises(AttributeError):
            loader.load("prompt_optimization.seed_prompts.executor_seed:123")

    def test_load_empty_demo_list(self):
        """Test loading an empty demo list (valid case)."""
        loader = DemoLoader()

        # AGGREGATOR_DEMOS is intentionally empty
        demos = loader.load(
            "prompt_optimization.seed_prompts.aggregator_seed:AGGREGATOR_DEMOS"
        )

        assert demos == []
        assert isinstance(demos, list)
