"""
Test ROMA + PTC Integration

This script demonstrates the complete integration between ROMA and PTC service.

Prerequisites:
1. PTC service running on http://localhost:8002
2. Kimi API key configured in PTC
3. ROMA installed

Usage:
    python examples/test_ptc_integration.py
"""

import asyncio
from loguru import logger
import sys

# Add src to path
sys.path.insert(0, "/home/user/ROMA/src")

from roma_dspy.core.modules import PTCExecutor
from roma_dspy.types import TaskType


async def test_direct_ptc_call():
    """Test 1: Direct PTC executor call for code generation."""
    print("\n" + "="*80)
    print("TEST 1: Direct PTC Executor Call")
    print("="*80)

    # Create PTC-enabled executor
    executor = PTCExecutor(
        ptc_enabled=True,
        ptc_base_url="http://localhost:8002",
        ptc_timeout=60.0,
    )

    # Simple code generation task
    task = "Create a Python function to calculate factorial recursively"

    print(f"\n📝 Task: {task}")
    print(f"🎯 Routing to: PTC Service (Kimi)")

    try:
        result = await executor.aforward(
            goal=task,
            task_type=TaskType.CODE_INTERPRET,
        )

        print(f"\n✅ Result:")
        print(result.output)

        if hasattr(result, '_metadata'):
            metadata = result._metadata
            print(f"\n📊 Stats:")
            print(f"   Provider: {metadata.get('provider', 'unknown')}")
            print(f"   Tokens: {metadata.get('tokens_used', 0)}")
            print(f"   Cost: ${metadata.get('cost_usd', 0):.6f}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fallback_to_llm():
    """Test 2: Non-code task falls back to LLM."""
    print("\n" + "="*80)
    print("TEST 2: Fallback to LLM (Non-code task)")
    print("="*80)

    executor = PTCExecutor(
        ptc_enabled=True,
        ptc_base_url="http://localhost:8002",
        model="openrouter/google/gemini-2.5-flash",  # Fallback LLM
    )

    task = "Explain the concept of recursion in simple terms"

    print(f"\n📝 Task: {task}")
    print(f"🎯 Expected routing: Standard LLM (not code task)")

    try:
        result = await executor.aforward(goal=task)

        print(f"\n✅ Result:")
        print(result.output if hasattr(result, 'output') else result)

        # This should NOT have PTC metadata
        if hasattr(result, '_metadata') and 'ptc_result' in result._metadata:
            print("\n⚠️  Warning: Task went to PTC when it shouldn't have")
        else:
            print("\n✅ Correctly routed to standard LLM")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


async def test_complex_code_task():
    """Test 3: Complex code generation with requirements."""
    print("\n" + "="*80)
    print("TEST 3: Complex Code Task with Requirements")
    print("="*80)

    executor = PTCExecutor(
        ptc_enabled=True,
        ptc_base_url="http://localhost:8002",
    )

    task = "Create a REST API endpoint for user authentication"
    requirements = [
        "Use FastAPI framework",
        "Include JWT token generation",
        "Add input validation with Pydantic",
        "Include comprehensive docstrings",
    ]

    print(f"\n📝 Task: {task}")
    print(f"📋 Requirements:")
    for req in requirements:
        print(f"   - {req}")
    print(f"🎯 Routing to: PTC Service (Kimi)")

    try:
        result = await executor.aforward(
            goal=task,
            requirements=requirements,
            language="python",
        )

        print(f"\n✅ Result:")
        print(result.output)

        if hasattr(result, '_metadata'):
            metadata = result._metadata
            print(f"\n📊 Stats:")
            print(f"   Provider: {metadata.get('provider', 'unknown')}")
            print(f"   Tokens: {metadata.get('tokens_used', 0)}")
            print(f"   Cost: ${metadata.get('cost_usd', 0):.6f}")

            # Cost comparison
            claude_cost = metadata.get('tokens_used', 0) / 1_000_000 * 9  # Rough estimate
            savings = ((claude_cost - metadata.get('cost_usd', 0)) / claude_cost) * 100 if claude_cost > 0 else 0
            print(f"   Est. Claude cost: ${claude_cost:.6f}")
            print(f"   💰 Savings: {savings:.1f}%")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests."""
    print("\n" + "🚀" * 40)
    print("ROMA + PTC Integration Test Suite")
    print("🚀" * 40)

    results = {}

    # Test 1: Direct PTC call
    results['direct_ptc'] = await test_direct_ptc_call()

    # Test 2: Fallback to LLM
    # results['fallback'] = await test_fallback_to_llm()

    # Test 3: Complex code task
    results['complex_code'] = await test_complex_code_task()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! ROMA + PTC integration is working!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
