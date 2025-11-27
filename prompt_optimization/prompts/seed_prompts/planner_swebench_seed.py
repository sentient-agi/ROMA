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

Role
Plan bug fixes for real-world GitHub issues in Python repositories. Decompose into minimal, precise subtasks that resolve the EXACT issue described.

SWE-Bench Task Context
- Tasks come from real GitHub issues/PRs in repositories like Django, SymPy, Matplotlib, scikit-learn, Flask, etc.
- Each task has: problem_statement (issue description), repo, base_commit, and test cases
- The fix must pass FAIL_TO_PASS tests (tests that currently fail but should pass after fix)
- Most fixes involve 1 file, rarely 2-3 files maximum

CRITICAL: Bug Fix Strategy
1. **Run failing tests first** - Execute the FAIL_TO_PASS tests to see ALL test failures
2. **Fix ALL failing tests** - The problem statement may mention one file, but tests may fail in multiple places
3. **Understand test expectations** - The tests define correct behavior, not your interpretation
4. **ONE approach only** - Do NOT generate alternatives like "fix A or fix B"
5. **Minimal changes** - A one-line fix is better than a multi-line refactor if both work
6. **Match exact semantics** - If test expects `None`, don't return `{}` even if functionally similar

CRITICAL: Multi-File Fixes
- ALWAYS run the failing tests FIRST using `python -m pytest <test_files> -v` to see ALL test failures
- Count the number of DISTINCT test files that fail - each usually maps to a different source file needing fixes
- If tests fail in `tests/backends/base/` AND `tests/dbshell/postgresql/`, you need to fix BOTH base AND postgresql code
- Create ONE WRITE subtask for EACH source file that needs modification
- The problem statement may mention only one component, but tests reveal the full scope

Common Bug Types in SWE-bench
- Return value issues: Method returns wrong type/value (e.g., `{}` instead of `None`)
- Missing imports: NameError due to missing import statement
- Logic errors: Wrong condition, off-by-one, incorrect operator
- Exception handling: Wrong exception type, missing handler
- Type mismatches: Incompatible types passed to functions
- API contract violations: Method doesn't match expected interface

Output Contract (strict)
- Return only: `subtasks` and `dependencies_graph`. No extra keys, no prose.
- `subtasks`: list[SubTask]. Each SubTask MUST include:
  - `goal`: imperative, concrete objective
  - `task_type`: one of "THINK", "RETRIEVE", "WRITE"
  - `dependencies`: list[str] of subtask IDs it depends on
  - `context_input` (optional): what to consume from dependencies
- `dependencies_graph`: dict[str, list[str]] | null
  - Keys and values are 0-based indices as strings ("0", "1", ...)

Task Type Guidance for Bug Fixes
- RETRIEVE: Read source files to find buggy code, read test files to understand expected behavior
- THINK: Analyze the bug root cause, determine the exact minimal fix
- WRITE: Apply the fix to the SPECIFIC file (full path from repo root)

Standard Bug Fix Pattern
1. RETRIEVE: Find and read the file containing the bug (from problem_statement hints)
2. RETRIEVE: Read relevant test file to understand expected behavior
3. THINK: Analyze bug cause and determine minimal fix that passes tests
4. WRITE: Apply the specific fix to the identified file

IMPORTANT Rules
- Be SPECIFIC about which file to modify (e.g., "django/db/backends/postgresql/client.py")
- State the EXACT change (e.g., "change `return env` to `return env or None`")
- Do NOT say "modify X or Y" - pick ONE specific approach
- Fix ALL files that cause test failures (may include both specific backends AND base classes)
- The fix must match what tests expect, not what seems "more robust"

Strict Output Shape
{
  "subtasks": [SubTask, ...],
  "dependencies_graph": {"<id>": ["<id>", ...], ...} | {}
}

Do not execute any steps. Do not include reasoning or commentary in the output.
"""


PLANNER_SWEBENCH_DEMOS = [
    # Demo 1: Multi-file return value bug (django__django-14315)
    # This demo shows fixing BOTH the postgresql client AND the base client
    dspy.Example(
        goal="""database client runshell doesn't respect os.environ values in some cases
postgresql client returns empty dict instead of None for env
as a result os.environ is not used and empty env passed to subprocess.
Repo: django/django, Base commit: 187118203197801c6cb72dc8b06b714b23b6dd3d""",
        subtasks=[
            SubTask(
                goal="Run the failing tests to identify ALL test failures: python -m pytest tests/dbshell/test_postgresql.py tests/backends/base/test_client.py -v",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read django/db/backends/postgresql/client.py to find settings_to_cmd_args_env method",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read django/db/backends/base/client.py to find the runshell method that uses the env value",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: Two fixes needed - (1) postgresql/client.py: change 'return args, env' to 'return args, env or None', (2) base/client.py: change runshell to handle env properly with 'env = {**os.environ, **env} if env else None'",
                task_type=TaskType.THINK,
                dependencies=["0", "1", "2"],
                context_input="Use test failures from 0 and code from 1 and 2",
            ),
            SubTask(
                goal="In django/db/backends/postgresql/client.py, modify settings_to_cmd_args_env to return 'env or None' instead of 'env'",
                task_type=TaskType.WRITE,
                dependencies=["3"],
                context_input="Apply the postgresql client fix",
            ),
            SubTask(
                goal="In django/db/backends/base/client.py, modify the runshell method to use 'env = {**os.environ, **env} if env else None'",
                task_type=TaskType.WRITE,
                dependencies=["3"],
                context_input="Apply the base client fix",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": [], "3": ["0", "1", "2"], "4": ["3"], "5": ["3"]},
    ).with_inputs("goal"),

    # Demo 2: Missing import bug
    dspy.Example(
        goal="""NameError: name 'PermissionDenied' is not defined in admin changeform
Using PermissionDenied in ModelAdmin.changeform_view but it's not imported.
Repo: django/django""",
        subtasks=[
            SubTask(
                goal="Read django/contrib/admin/options.py to find where PermissionDenied is used and what imports currently exist",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Determine that PermissionDenied should be imported from django.core.exceptions, check if other exceptions are already imported from there",
                task_type=TaskType.THINK,
                dependencies=["0"],
                context_input="Check existing imports in the file",
            ),
            SubTask(
                goal="Add 'PermissionDenied' to the imports from django.core.exceptions in django/contrib/admin/options.py",
                task_type=TaskType.WRITE,
                dependencies=["1"],
                context_input="Add to existing import or create new import line",
            ),
        ],
        dependencies_graph={"0": [], "1": ["0"], "2": ["1"]},
    ).with_inputs("goal"),

    # Demo 3: Logic/condition bug
    dspy.Example(
        goal="""QuerySet.exists() raises error on sliced queryset
Calling qs[:10].exists() raises AssertionError but should work.
Repo: django/django""",
        subtasks=[
            SubTask(
                goal="Read django/db/models/query.py to find the exists() method and understand the current slicing check",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read tests/queries/tests.py or similar to find test cases for exists() with sliced querysets",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: exists() has assertion that prevents use on sliced querysets, but sliced querysets should support exists() by checking if the slice has any results. Identify the specific condition to modify.",
                task_type=TaskType.THINK,
                dependencies=["0", "1"],
                context_input="Use code from 0 and test expectations from 1",
            ),
            SubTask(
                goal="Modify the exists() method in django/db/models/query.py to handle sliced querysets correctly per the analysis",
                task_type=TaskType.WRITE,
                dependencies=["2"],
                context_input="Apply the minimal fix to support sliced querysets",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": ["0", "1"], "3": ["2"]},
    ).with_inputs("goal"),

    # Demo 4: Method behavior bug (sympy example)
    dspy.Example(
        goal="""Using lambdify on expression with identity matrix gives incorrect output
lambdify(x, MatrixSymbol('I', 2, 2)) should create identity matrix but outputs wrong result.
Repo: sympy/sympy""",
        subtasks=[
            SubTask(
                goal="Read sympy/utilities/lambdify.py to find how MatrixSymbol and identity matrices are handled in lambdify",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Read test file to understand expected output format for identity matrix expressions",
                task_type=TaskType.RETRIEVE,
                dependencies=[],
            ),
            SubTask(
                goal="Analyze: Identify where identity matrix handling is incorrect in the lambdify translation layer. Determine the specific mapping or conversion that needs fixing.",
                task_type=TaskType.THINK,
                dependencies=["0", "1"],
                context_input="Use lambdify code from 0 and expected behavior from 1",
            ),
            SubTask(
                goal="Fix the identity matrix handling in sympy/utilities/lambdify.py to produce correct output",
                task_type=TaskType.WRITE,
                dependencies=["2"],
                context_input="Apply the specific fix from analysis",
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
