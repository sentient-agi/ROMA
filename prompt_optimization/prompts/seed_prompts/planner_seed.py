"""Planner few-shot demos for DSPy.

These examples follow `PlannerSignature`:
- Input: `goal: str`
- Outputs: `subtasks: list[SubTask]`, `dependencies_graph: dict[str, list[str]] | None`

Notes
- SubTask fields used: `goal`, `task_type`, `dependencies`, optional `context_input`.
- Subtask IDs are their 0-based indices as strings ("0", "1", ...).
- `dependencies_graph` mirrors the per-SubTask `dependencies` and is acyclic.
"""

from __future__ import annotations

import dspy
from roma_dspy.core.signatures.base_models.subtask import SubTask
from roma_dspy.types.task_type import TaskType


PLANNER_PROMPT = r"""
# Planner — Instruction Prompt

Role
Plan a goal into minimal, parallelizable subtasks with a precise, acyclic dependency graph. Do not execute; only plan.

Available Tools
If web search tools are available to you, you can use them during planning to:
- Research current events, trends, or market data when planning tasks that require up-to-date information
- Verify task requirements or gather context before decomposing complex goals
- Find relevant documentation, best practices, or domain-specific knowledge to inform your planning
- Improve the quality and accuracy of RETRIEVE task definitions

Output Contract (strict)
- Return only: `subtasks` and `dependencies_graph`. No extra keys, no prose.
- `subtasks`: list[SubTask]. Each SubTask MUST include:
  - `goal`: imperative, concrete objective for the subtask.
  - `task_type`: one of "THINK", "RETRIEVE", "WRITE".
  - `dependencies`: list[str] of subtask IDs it depends on.
  - `context_input` (optional): brief note on what to consume from dependencies; omit when unnecessary.
- `dependencies_graph`: dict[str, list[str]] | null
  - Keys and values are subtask IDs as 0-based indices encoded as strings, e.g., "0", "1".
  - Must be acyclic and consistent with each SubTask's `dependencies`.
  - Use empty lists for independent subtasks; set to `{}` if no dependencies, or `null` if not needed.
- Do not add fields like `id` or `result`. The list index is the subtask ID.

Task Type Guidance (MECE)
- THINK: reasoning, derivations, comparisons, validations; no external retrieval.
- RETRIEVE: fetch/verify external info where freshness, citations, or lookup are essential (replaces "SEARCH").
- WRITE: produce prose/structured text when inputs are known (emails, outlines, drafts, summaries).

Decomposition Principles
- Minimality: Decompose only as much as necessary to reach the goal.
- MECE: Subtasks should not overlap; together they fully cover the goal.
- Parallelization: Prefer independent subtasks with a final synthesis step; add dependencies only when required.
- Granularity: For common tasks, prefer 3–8 total subtasks; keep the number of artefact-producing steps (WRITE/CODE_INTERPRET/IMAGE_GENERATION) to 1–5 unless complexity justifies more.
- Determinism: Each subtask should have a clear, verifiable completion condition.

Dependency Rules
- Use 0-based indices as strings for IDs ("0", "1", ...). The index in `subtasks` is the ID.
- A subtask may only depend on earlier IDs when linear order is natural; otherwise make independent and merge later.
- Keep the graph acyclic; avoid chains longer than necessary.
- Ensure `dependencies_graph` matches each SubTask's `dependencies` exactly.

Context Flow
- Outputs from dependencies are available to dependents; do not recompute.
- When a dependent needs specific artefacts (numbers, citations, outlines), state this succinctly in `context_input`.
- Numeric values from other subtasks are provided after those subtasks complete; reference them rather than re-deriving.

Edge Cases
- If the goal is already atomic, return the minimal valid plan (often 1–3 subtasks) rather than inflating to 3–8.
- If key requirements are unspecified, add an early THINK step to enumerate assumptions or a RETRIEVE step to collect missing facts.

Strict Output Shape
{
  "subtasks": [SubTask, ...],
  "dependencies_graph": {"<id>": ["<id>", ...], ...} | {}
}

Do not execute any steps, and do not include reasoning or commentary in the output.
"""



# Few-shot demos for the Planner
PLANNER_DEMOS = [
    # 1) Minimal, atomic-style goal (single THINK step)
    dspy.Example(
        goal="What is the capital of France?",
        subtasks=[
            SubTask(
                goal="State the capital of France.",
                task_type=TaskType.THINK,
                dependencies=[],
            )
        ],
        dependencies_graph={"0": []},
    ).with_inputs("goal"),

    # 2) Retrieval with formatting (RETRIEVE -> WRITE)
    dspy.Example(
        goal="What is the current price of Bitcoin in USD?",
        subtasks=[
            SubTask(
                goal=(
                    "Fetch the current BTCUSD spot price from a reputable financial source "
                    "with source name and timestamp (prefer primary or leading aggregator)."
                ),
                task_type=TaskType.RETRIEVE,
                dependencies=[],
                context_input="Return price, currency, source, and timestamp.",
            ),
            SubTask(
                goal=(
                    "Format as 'BTCUSD: <price> USD — <source> <timestamp>' ensuring the timestamp is recent."
                ),
                task_type=TaskType.WRITE,
                dependencies=["0"],
                context_input="Use the fetched price, source, and timestamp from 0.",
            ),
        ],
        dependencies_graph={"0": [], "1": ["0"]},
    ).with_inputs("goal"),

    # 3) Two parallel deliverables then bundle (WRITE, WRITE -> WRITE)
    dspy.Example(
        goal="Create a 1-page privacy policy and a separate cookie policy for my blog.",
        subtasks=[
            SubTask(
                goal=(
                    "Draft a clear 1-page privacy policy for a personal blog with headings: "
                    "'Data Collected', 'Use of Data', 'Third-Party Services', 'Data Retention', 'Contact'. "
                    "Neutral tone, plain English, ≤ 450 words."
                ),
                task_type=TaskType.WRITE,
                dependencies=[],
            ),
            SubTask(
                goal=(
                    "Draft a concise cookie policy for the blog covering cookie types, purposes (analytics, preferences), "
                    "opt-out instructions, and update date. Neutral tone, ≤ 450 words."
                ),
                task_type=TaskType.WRITE,
                dependencies=[],
            ),
            SubTask(
                goal=(
                    "Bundle both documents into a single markdown deliverable with H1 headings 'Privacy Policy' and "
                    "'Cookie Policy'. Ensure consistent tone and date stamps."
                ),
                task_type=TaskType.WRITE,
                dependencies=["0", "1"],
                context_input="Use the full texts from 0 and 1; combine into one markdown file with the specified headings.",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": ["0", "1"]},
    ).with_inputs("goal"),

    # 4) Dual retrieval then synthesis and finalization (RETRIEVE, RETRIEVE -> THINK -> WRITE)
    dspy.Example(
        goal="Collect Apple and Microsoft’s latest quarterly results and compare their guidance side-by-side.",
        subtasks=[
            SubTask(
                goal=(
                    "Retrieve Apple's most recent quarterly results: revenue, EPS, guidance highlights, and report date "
                    "from primary sources (investor relations, 10-Q/press release) with citations."
                ),
                task_type=TaskType.RETRIEVE,
                dependencies=[],
                context_input="Include figures, date, source name, and URL.",
            ),
            SubTask(
                goal=(
                    "Retrieve Microsoft's most recent quarterly results: revenue, EPS, guidance highlights, and report date "
                    "from primary sources with citations."
                ),
                task_type=TaskType.RETRIEVE,
                dependencies=[],
                context_input="Include figures, date, source name, and URL.",
            ),
            SubTask(
                goal=(
                    "Create a compact table comparing Apple vs. Microsoft: revenue, EPS, YoY %, guidance summary, and "
                    "reporting dates; note fiscal calendar differences and include units."
                ),
                task_type=TaskType.THINK,
                dependencies=["0", "1"],
                context_input="Use the retrieved metrics and citations from 0 and 1.",
            ),
            SubTask(
                goal=(
                    "Wrap the table with a 2–3 sentence summary and list citations underneath."
                ),
                task_type=TaskType.WRITE,
                dependencies=["2"],
                context_input="Insert the table from 2, then add brief summary and citation list.",
            ),
        ],
        dependencies_graph={"0": [], "1": [], "2": ["0", "1"], "3": ["2"]},
    ).with_inputs("goal"),
]

