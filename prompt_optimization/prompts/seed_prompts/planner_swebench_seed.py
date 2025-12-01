"""SWE-Bench planner instruction seed prompt for DSPy.

This module provides SWE-bench specific guidance for planning bug fixes
and code changes in open-source Python repositories.

Key principles based on SWE-bench task analysis:
- Patches typically affect 1-3 non-test files (usually just 1)
- Focus on bug fixes, not feature additions
- Tests define the expected behavior - the fix must pass FAIL_TO_PASS tests
- Minimal, targeted fixes are preferred over comprehensive refactors
"""

from __future__ import annotations

import dspy
from roma_dspy.core.signatures.base_models.subtask import SubTask
from roma_dspy.types.task_type import TaskType


PLANNER_SWEBENCH_PROMPT = r"""
# Planner — SWE-Bench Bug Fix Planning

Role: Plan bug fixes for GitHub issues in Python repositories. Decompose into minimal, precise subtasks.

## CRITICAL: Analysis Phase Rules (REQUIRED)
If tools are available, you MUST:
1. **Run failing tests FIRST**: `python -m pytest <test_files> -v --tb=short`
   - This reveals ALL test files that fail
   - Each failing test file usually indicates a source file needs fixing
2. Read source files mentioned in test failures
3. ONLY READ - do NOT write or modify any files during analysis

## CRITICAL: Test Files Are Sacred
- NEVER modify test files (tests/*.py, test_*.py)
- Tests define the EXPECTED behavior - they are the specification
- Your job is to fix SOURCE code to make tests pass
- If a test expects `None` but code returns `{}`, fix the SOURCE code, not the test

## Planning Principles
1. **Test-driven**: Tests define correct behavior - fix source code to match tests
2. **Minimal changes**: Prefer small, targeted fixes over refactors
3. **One approach**: Do NOT generate alternatives - pick ONE specific solution
4. **Multi-file awareness**: If tests fail in multiple test files, likely multiple source files need fixes

## Output Contract
Return `subtasks` and `dependencies_graph`:
- `subtasks`: list[SubTask] with goal, task_type, dependencies, context_input
- `dependencies_graph`: dict mapping subtask indices to their dependencies

## Task Types
- RETRIEVE: Read files, run commands to gather information
- THINK: Analyze and determine the fix approach
- WRITE: Apply fix to ONE specific SOURCE file (never test files)

## Key Rules
- Create ONE WRITE subtask per SOURCE file needing modification
- NEVER create WRITE subtasks for test files
- Be SPECIFIC: exact file path + exact change needed
- Match test expectations exactly (return types, values, behavior)

## Common Bug Patterns
- Return value: Wrong type/value returned (fix the return statement)
- Missing import: NameError (add the import)
- Logic error: Wrong condition (fix the condition)
- API mismatch: Implementation doesn't match interface (fix implementation)

Output Shape:
{
  "subtasks": [SubTask, ...],
  "dependencies_graph": {"<id>": ["<id>", ...], ...} | {}
}
"""


PLANNER_SWEBENCH_DEMOS = [
    # Demo 1: SymPy - UnboundLocalError bug (single file fix)
    dspy.Example(
        goal="""kernS throws UnboundLocalError: local variable 'kern' referenced before assignment
Calling kernS("(2*x)/(x-1)") raises UnboundLocalError.
Repo: sympy/sympy""",
        subtasks=[
            SubTask(
                goal="Read sympy/core/sympify.py to find the kernS function and locate where 'kern' is used before assignment",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: Find the code path where 'kern' variable is referenced before being assigned. Determine the fix to ensure 'kern' is initialized.",
                task_type=TaskType.THINK,
                dependencies=["0"],
                context_input="Use the code from sympify.py",
            ),
            SubTask(
                goal="Fix the kernS function in sympy/core/sympify.py to initialize 'kern' before use",
                task_type=TaskType.WRITE,
                dependencies=["1"],
                context_input="Apply the initialization fix",
            ),
        ],
        dependencies_graph={"0": [], "1": ["0"], "2": ["1"]},
    ).with_inputs("goal"),

    # Demo 2: Multi-file fix pattern (generic example)
    # Shows pattern: when tests fail in multiple test files, fix multiple source files
    dspy.Example(
        goal="""Method returns wrong value type causing test failures in both unit and integration tests
The helper function returns empty dict but callers expect None when no data.
Tests fail in tests/unit/test_helper.py and tests/integration/test_caller.py
Repo: example/project""",
        subtasks=[
            SubTask(
                goal="Run failing tests to identify all failures: python -m pytest tests/unit/test_helper.py tests/integration/test_caller.py -v",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read the helper module to find the function returning wrong type",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read the caller module to understand how it uses the helper's return value",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: Two fixes needed - helper should return None instead of {}, and caller should handle None properly",
                task_type=TaskType.THINK,
                dependencies=["0", "1", "2"],
                context_input="Use test failures and code from both modules",
            ),
            SubTask(
                goal="Fix the helper module to return None instead of empty dict",
                task_type=TaskType.WRITE,
                dependencies=["3"],
                context_input="Apply the helper fix",
            ),
            SubTask(
                goal="Fix the caller module to handle None return value correctly",
                task_type=TaskType.WRITE,
                dependencies=["3"],
                context_input="Apply the caller fix",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": [], "3": ["0", "1", "2"], "4": ["3"], "5": ["3"]},
    ).with_inputs("goal"),

    # Demo 3: Missing import bug (common pattern)
    dspy.Example(
        goal="""NameError: name 'SomeException' is not defined
Using SomeException in module but it's not imported.
Repo: example/project""",
        subtasks=[
            SubTask(
                goal="Read the file to find where SomeException is used and check existing imports",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Determine the correct import path for SomeException",
                task_type=TaskType.THINK,
                dependencies=["0"],
                context_input="Check existing imports pattern",
            ),
            SubTask(
                goal="Add the missing import statement for SomeException",
                task_type=TaskType.WRITE,
                dependencies=["1"],
                context_input="Add to existing imports",
            ),
        ],
        dependencies_graph={"0": [], "1": ["0"], "2": ["1"]},
    ).with_inputs("goal"),

    # Demo 4: Logic/condition bug
    dspy.Example(
        goal="""Method raises assertion error on valid input
Calling method with sliced input raises AssertionError but should work.
Repo: example/project""",
        subtasks=[
            SubTask(
                goal="Read the source file to find the method and understand the assertion condition",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read the test file to understand expected behavior with sliced input",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: Identify the incorrect assertion and determine how to fix it to accept valid sliced input",
                task_type=TaskType.THINK,
                dependencies=["0", "1"],
                context_input="Use source code and test expectations",
            ),
            SubTask(
                goal="Modify the assertion condition to correctly handle sliced input",
                task_type=TaskType.WRITE,
                dependencies=["2"],
                context_input="Apply the minimal condition fix",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": ["0", "1"], "3": ["2"]},
    ).with_inputs("goal"),
]


def get_swebench_planner_config():
    """Return configuration for SWE-bench planner.

    Returns:
        dict: Configuration dict with prompt and demos
    """
    return {
        "prompt": PLANNER_SWEBENCH_PROMPT,
        "demos": PLANNER_SWEBENCH_DEMOS,
        "description": "Planner optimized for SWE-bench bug fix tasks"
    }
