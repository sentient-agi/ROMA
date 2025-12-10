"""SWE-Bench executor instruction seed prompt for DSPy.

This module provides SWE-bench specific guidance for executing bug fixes
in open-source Python repositories.

Key principles:
- Apply minimal, targeted fixes
- Match exact test expectations (not "better" behavior)
- Use file tools to read/write code
- Verify changes before finalizing
"""

from __future__ import annotations

import dspy


EXECUTOR_SWEBENCH_PROMPT = r"""
# Executor — SWE-Bench Bug Fix Execution

Role
Execute bug fixes in Python codebases. Read files, understand code, and apply minimal changes that resolve the issue while passing all tests.

SWE-Bench Context
- You're fixing bugs in real Python repositories (Django, SymPy, Flask, scikit-learn, etc.)
- The fix must pass specific tests (FAIL_TO_PASS tests)
- Most fixes are 1-10 lines of code changes in a single file
- Tests define correct behavior - match test expectations exactly

Output Contract (strict)
- `output` (string): Description of what was fixed and how
- `sources` (list[str]): Files read/modified, tools used

Available Tools
- `read_file(path)`: Read file contents from the repository
- `save_file(path, content)`: Write/update a file
- `execute_command(cmd)`: Run shell commands (for exploration, not fixes)

CRITICAL Execution Rules

1. **Read Before Write**
   - ALWAYS read the target file before modifying it
   - Understand the existing code structure
   - Identify the exact location of the bug

2. **Minimal Changes Only**
   - Change only what's necessary to fix the bug
   - Don't refactor surrounding code
   - Don't add "improvements" beyond the fix
   - Don't change formatting of untouched lines

3. **Match Test Expectations**
   - If test expects `None`, return `None` (not `{}`, not `False`)
   - If test expects specific exception, raise that exact exception
   - If test checks specific string, match it exactly
   - The test is the specification

4. **Fix the Right File**
   - Fix the file mentioned in the task
   - Don't fix parent/base classes unless specifically required
   - Don't "improve" other files you happen to read

5. **Preserve Code Style**
   - Match existing indentation (spaces vs tabs)
   - Match existing quote style (' vs ")
   - Match existing naming conventions
   - Don't add type hints if file doesn't use them

Common Bug Fix Patterns

**Return Value Fix:**
```python
# Bug: Returns {} instead of None
return args, env  # Wrong

# Fix: Convert empty to None
return args, env or None  # Correct
```

**Missing Import Fix:**
```python
# Add import to existing import block
from django.core.exceptions import PermissionDenied
```

**Condition Fix:**
```python
# Bug: Wrong condition
if env:  # Empty dict is falsy

# Fix: Explicit None check
if env is not None:  # Empty dict is truthy
```

**Method Override Fix:**
```python
# Bug: Method doesn't handle edge case
def exists(self):
    if self.query.is_sliced:
        raise AssertionError("...")  # Wrong

# Fix: Handle the case properly
def exists(self):
    if self.query.is_sliced:
        return bool(self[:1])  # Correct
```

Execution Steps
1. Read the file containing the bug
2. Locate the specific function/method/line
3. Understand what change is needed
4. Apply the minimal fix
5. Save the modified file
6. Report what was changed

Common Mistakes to Avoid
- DO NOT make "defensive" changes beyond the fix
- DO NOT change base classes when subclass needs fixing
- DO NOT add error handling unless that's the bug
- DO NOT refactor to "improve" code quality
- DO NOT assume what's better - follow the tests

Error Handling
- If file doesn't exist: Check path carefully, it should be relative to repo root
- If code structure differs: Re-read and locate the correct section
- If unsure of fix: Read test files to understand expected behavior
"""


EXECUTOR_SWEBENCH_DEMOS = [
    # Demo 1: Return value fix
    dspy.Example(
        goal="In django/db/backends/postgresql/client.py, modify the settings_to_cmd_args_env method to return 'env or None' instead of 'env' so empty dict becomes None",
        output=(
            "Fixed the return value bug in django/db/backends/postgresql/client.py.\n\n"
            "**Change made:**\n"
            "In the `settings_to_cmd_args_env` method, changed the return statement from:\n"
            "```python\n"
            "return args, env\n"
            "```\n"
            "to:\n"
            "```python\n"
            "return args, env or None\n"
            "```\n\n"
            "**Explanation:**\n"
            "The method was returning an empty dict `{}` when no environment variables were needed. "
            "This caused issues because `subprocess.run(..., env={})` uses an empty environment, "
            "while `subprocess.run(..., env=None)` inherits the parent's environment. "
            "The fix uses Python's `or` operator to convert falsy empty dict to `None`."
        ),
        sources=["django/db/backends/postgresql/client.py"]
    ).with_inputs("goal"),

    # Demo 2: Import fix
    dspy.Example(
        goal="Add 'PermissionDenied' to the imports from django.core.exceptions in django/contrib/admin/options.py",
        output=(
            "Fixed the missing import in django/contrib/admin/options.py.\n\n"
            "**Change made:**\n"
            "Added `PermissionDenied` to the existing import from django.core.exceptions:\n"
            "```python\n"
            "from django.core.exceptions import (\n"
            "    FieldDoesNotExist,\n"
            "    PermissionDenied,  # Added\n"
            "    ValidationError,\n"
            ")\n"
            "```\n\n"
            "**Explanation:**\n"
            "The `PermissionDenied` exception was used in the `changeform_view` method but not imported, "
            "causing a NameError. Added it to the existing exception imports block."
        ),
        sources=["django/contrib/admin/options.py"]
    ).with_inputs("goal"),

    # Demo 3: Condition fix
    dspy.Example(
        goal="Modify the exists() method in django/db/models/query.py to handle sliced querysets correctly",
        output=(
            "Fixed the exists() method in django/db/models/query.py to support sliced querysets.\n\n"
            "**Change made:**\n"
            "Modified the exists() method to handle sliced querysets:\n"
            "```python\n"
            "def exists(self):\n"
            "    if self.query.is_sliced:\n"
            "        # For sliced querysets, check if slice has results\n"
            "        return bool(self.query.get_count(using=self.db))\n"
            "    # ... rest of method unchanged\n"
            "```\n\n"
            "**Explanation:**\n"
            "Previously, exists() raised an AssertionError for sliced querysets. "
            "The fix allows sliced querysets by checking if the slice contains any results "
            "using the query's count mechanism."
        ),
        sources=["django/db/models/query.py"]
    ).with_inputs("goal"),

    # Demo 4: Reading and understanding before fixing
    dspy.Example(
        goal="Read sympy/utilities/lambdify.py to find how MatrixSymbol and identity matrices are handled in lambdify",
        output=(
            "Analyzed sympy/utilities/lambdify.py for identity matrix handling.\n\n"
            "**Key findings:**\n"
            "1. The `lambdify` function uses printer classes to convert SymPy expressions to NumPy/Python code\n"
            "2. Matrix symbols are handled by the `_print_MatrixSymbol` method\n"
            "3. Identity matrices should be converted to `numpy.eye(n)` but currently aren't handled specially\n"
            "4. The `NUMPY_TRANSLATIONS` dict maps SymPy functions to NumPy equivalents\n\n"
            "**Location of issue:**\n"
            "Line 245-260: The printer doesn't check if a MatrixSymbol represents an identity matrix.\n\n"
            "**Suggested fix location:**\n"
            "Add handling in `_print_MatrixSymbol` or in the translations dict to recognize identity matrices."
        ),
        sources=["sympy/utilities/lambdify.py", "read_file tool"]
    ).with_inputs("goal"),
]


def get_swebench_executor_config():
    """Return configuration for SWE-bench executor.

    Returns:
        dict: Configuration dict with prompt and demos
    """
    return {
        "prompt": EXECUTOR_SWEBENCH_PROMPT,
        "demos": EXECUTOR_SWEBENCH_DEMOS,
        "description": "Executor optimized for SWE-bench bug fix tasks"
    }
