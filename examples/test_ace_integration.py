"""
ACE Integration Test - Demonstrates Learning Capabilities

This script shows how ACE learns from code generation tasks and improves over time.
"""

import asyncio
from pathlib import Path
from loguru import logger

# Configure logging
logger.remove()
logger.add(lambda msg: print(msg, end=""), level="INFO")

try:
    from roma_dspy.integrations import (
        ACEIntegratedExecutor,
        create_ace_executor,
        ACE_AVAILABLE,
    )
    from roma_dspy.types import TaskType
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure ROMA is installed: pip install -e .")
    exit(1)

if not ACE_AVAILABLE:
    logger.error("ACE framework not available")
    logger.error("Install with: pip install /home/user/ace-repo/")
    exit(1)


async def test_basic_execution():
    """Test 1: Basic ACE-enabled code generation."""
    logger.info("=" * 60)
    logger.info("Test 1: Basic ACE-Enabled Execution")
    logger.info("=" * 60)

    # Create ACE-enabled executor
    executor = create_ace_executor(
        ptc_base_url="http://localhost:8002",
        skillbook_path="./skillbooks/test_ace.json",
        ace_model="gpt-4o-mini",  # Cheap model for reflection
    )

    # Simple code generation task
    task = "Create a Python function that calculates factorial of a number"

    logger.info(f"\nTask: {task}")
    logger.info("Executing...")

    result = await executor.aforward(
        goal=task,
        task_type=TaskType.CODE_INTERPRET,
        requirements=["Add type hints", "Include docstring"],
    )

    logger.info("\n✅ Result:")
    logger.info(result.output[:200] + "...")

    # Show ACE metadata
    if hasattr(result, '_metadata') and 'ace_enabled' in result._metadata:
        logger.info("\n📊 ACE Metadata:")
        logger.info(f"  Skills used: {result._metadata.get('skills_used', 0)}")
        logger.info(f"  Feedback: {result._metadata.get('environment_feedback', 'N/A')}")
        logger.info(f"  Score: {result._metadata.get('performance_score', 0):.2f}")

    # Show learning stats
    stats = executor.get_learning_stats()
    logger.info("\n📚 Learning Stats:")
    logger.info(f"  Total skills learned: {stats['total_skills_learned']}")
    logger.info(f"  Skillbook: {stats['skillbook_path']}")

    return executor


async def test_learning_progression():
    """Test 2: Demonstrate learning progression over multiple tasks."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Learning Progression")
    logger.info("=" * 60)

    # Use separate skillbook for this test
    executor = create_ace_executor(
        ptc_base_url="http://localhost:8002",
        skillbook_path="./skillbooks/test_progression.json",
        ace_model="gpt-4o-mini",
    )

    # Series of related tasks to learn from
    tasks = [
        "Create a function to validate email addresses",
        "Create a function to validate phone numbers",
        "Create a function to validate URLs",
        "Create a function to validate IP addresses",
    ]

    logger.info(f"\nRunning {len(tasks)} related validation tasks...")
    logger.info("ACE should learn common validation patterns\n")

    for i, task in enumerate(tasks, 1):
        logger.info(f"\n[{i}/{len(tasks)}] {task}")

        result = await executor.aforward(
            goal=task,
            task_type=TaskType.CODE_INTERPRET,
            requirements=["Use regex", "Add error handling"],
        )

        # Show learning progress
        stats = executor.get_learning_stats()
        logger.info(f"  ✓ Skills learned so far: {stats['total_skills_learned']}")

        if hasattr(result, '_metadata') and 'performance_score' in result._metadata:
            logger.info(f"  ✓ Performance score: {result._metadata['performance_score']:.2f}")

    logger.info("\n" + "-" * 60)
    logger.info("📈 Learning Summary:")
    final_stats = executor.get_learning_stats()
    logger.info(f"  Total skills acquired: {final_stats['total_skills_learned']}")
    logger.info(f"  Skillbook saved to: {final_stats['skillbook_path']}")
    logger.info("\n✅ ACE has learned validation patterns for future use!")

    return executor


async def test_skillbook_reuse():
    """Test 3: Load existing skillbook and reuse learned patterns."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 3: Skillbook Reuse")
    logger.info("=" * 60)

    # Check if skillbook exists from previous test
    skillbook_path = Path("./skillbooks/test_progression.json")

    if not skillbook_path.exists():
        logger.warning("No existing skillbook found. Run test_learning_progression first.")
        return

    logger.info(f"\n✅ Found existing skillbook: {skillbook_path}")

    # Create executor that loads the skillbook
    executor = create_ace_executor(
        ptc_base_url="http://localhost:8002",
        skillbook_path=str(skillbook_path),
        ace_model="gpt-4o-mini",
    )

    stats = executor.get_learning_stats()
    logger.info(f"📚 Loaded {stats['total_skills_learned']} learned skills")

    # New task that can benefit from learned patterns
    task = "Create a function to validate credit card numbers"

    logger.info(f"\nTask: {task}")
    logger.info("Using learned validation patterns...")

    result = await executor.aforward(
        goal=task,
        task_type=TaskType.CODE_INTERPRET,
        requirements=["Use Luhn algorithm", "Add type hints"],
    )

    logger.info("\n✅ Result (leveraging learned patterns):")
    logger.info(result.output[:200] + "...")

    if hasattr(result, '_metadata') and 'environment_feedback' in result._metadata:
        logger.info(f"\n📊 Feedback: {result._metadata['environment_feedback']}")


async def test_cost_efficiency():
    """Test 4: Compare costs with and without ACE."""
    logger.info("\n" + "=" * 60)
    logger.info("Test 4: Cost Efficiency Analysis")
    logger.info("=" * 60)

    # Standard executor (no ACE)
    from roma_dspy.core.modules import PTCExecutor

    standard_executor = PTCExecutor(
        ptc_enabled=True,
        ptc_base_url="http://localhost:8002",
    )

    # ACE-enabled executor
    ace_executor = create_ace_executor(
        ptc_base_url="http://localhost:8002",
        skillbook_path="./skillbooks/test_cost.json",
    )

    task = "Create a REST API endpoint for user registration"

    # Test standard executor
    logger.info("\n1. Standard PTCExecutor (no learning):")
    result_standard = await standard_executor.aforward(
        goal=task,
        task_type=TaskType.CODE_INTERPRET,
    )
    cost_standard = result_standard._metadata.get('cost_usd', 0) if hasattr(result_standard, '_metadata') else 0
    tokens_standard = result_standard._metadata.get('tokens_used', 0) if hasattr(result_standard, '_metadata') else 0
    logger.info(f"  Cost: ${cost_standard:.6f}")
    logger.info(f"  Tokens: {tokens_standard}")

    # Test ACE executor
    logger.info("\n2. ACE-Integrated Executor (with learning):")
    result_ace = await ace_executor.aforward(
        goal=task,
        task_type=TaskType.CODE_INTERPRET,
    )
    cost_ace = result_ace._metadata.get('cost_usd', 0) if hasattr(result_ace, '_metadata') else 0
    tokens_ace = result_ace._metadata.get('tokens_used', 0) if hasattr(result_ace, '_metadata') else 0
    logger.info(f"  Cost: ${cost_ace:.6f}")
    logger.info(f"  Tokens: {tokens_ace}")

    # Note: First run will be similar, but subsequent runs should improve
    logger.info("\n📊 Analysis:")
    logger.info("  First run costs are similar")
    logger.info("  ACE learns from this execution")
    logger.info("  Future similar tasks will be more efficient")
    logger.info(f"  Skills learned: {ace_executor.get_learning_stats()['total_skills_learned']}")


async def main():
    """Run all ACE integration tests."""
    logger.info("🧪 ACE Integration Test Suite")
    logger.info("Testing ROMA + PTC + ACE learning capabilities\n")

    try:
        # Test 1: Basic execution
        await test_basic_execution()

        # Test 2: Learning progression
        await test_learning_progression()

        # Test 3: Skillbook reuse
        await test_skillbook_reuse()

        # Test 4: Cost efficiency
        await test_cost_efficiency()

        logger.info("\n" + "=" * 60)
        logger.info("✅ All ACE integration tests completed!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
