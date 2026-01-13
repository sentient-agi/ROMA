"""Dataset loaders for prompt optimization."""

import dspy
from datasets import load_dataset
import random
from typing import Optional, Tuple, List, Union
import pandas as pd

def load_aimo_datasets(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load AIMO math datasets with configurable sizes.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """

    # Load training/validation split from AIMO
    train_split = load_dataset("AI-MO/aimo-validation-aime")['train']
    train_split = [
        dspy.Example({
            "goal": x['problem'],
            'solution': x['solution'],
            'answer': x['answer'],
        }).with_inputs("goal")
        for x in train_split
    ]

    # Shuffle with fixed seed
    random.Random(seed).shuffle(train_split)
    tot_num = len(train_split)

    # Load test split from AIME 2025
    test_split = load_dataset("MathArena/aime_2025")['train']
    test_split = [
        dspy.Example({
            "goal": x['problem'],
            'answer': x['answer'],
        }).with_inputs("goal")
        for x in test_split
    ]

    # Return full dataset if no_split is True
    if no_split:
        return train_split + test_split

    # Split datasets
    train_set = train_split[:train_size]
    val_set = train_split[tot_num // 2:tot_num // 2 + val_size]

    # Repeat test set if needed to reach desired size
    test_set = (test_split * ((test_size // len(test_split)) + 1))[:test_size]

    return train_set, val_set, test_set


def load_abgen_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load ABGen dataset with configurable sizes.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """
    # Helper function to prepare user prompt for the ABGen dataset
    def prepare_goal(example):
        research_background = f"Research Background:\n{example['research_background']}\n"
        method = f"Method Section:\n{example['method']}\n"
        main_experiment = f"Main Experiment Setup\n{example['main_experiment']['experiment_setup']}\n\n Main Experiment Results\n{example['main_experiment']['results']}\n"

        ablation_module = example["ablation_study"]["module_name"]

        return f"Research Context:\n{research_background}{method}{main_experiment}\n\n Design an ablation study about {ablation_module} based on the research context above."

    # Load dataset ONCE to ensure deterministic ordering
    raw_dataset = load_dataset("yale-nlp/AbGen")['human_evaluation']
    
    # Convert to list immediately to lock in the ordering
    raw_list = list(raw_dataset)
    
    # Build examples with deterministic ordering (preserve original dataset order)
    all_examples = [
        dspy.Example({
            "goal": prepare_goal(x),
            'solution': x['ablation_study']['experiment_setup'],
            'answer': x['ablation_study']['research_objective'],
        }).with_inputs("goal")
        for x in raw_list
    ]

    tot_num = len(all_examples)

    # Return full dataset if no_split is True (deterministic order)
    if no_split:
        return all_examples

    # Split datasets (no shuffling - preserves original order)
    train_set = all_examples[:train_size]
    val_set = all_examples[tot_num // 2:tot_num // 2 + val_size]
    test_set = all_examples[:test_size]  # Use first test_size items for test

    return train_set, val_set, test_set


def load_frames_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    tsv_path: str = "hf://datasets/google/frames-benchmark/test.tsv",
    sep: str = "\t",
    text_column: Optional[str] = None,
    answer_column: Optional[str] = None,
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load the Google FRAMES benchmark TSV, then deterministically split into train/val/test.

    If column names are unknown, tries to infer text/answer columns; override via
    `text_column` and `answer_column` when you know them.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        tsv_path: Path to the TSV file
        sep: Separator character for TSV
        text_column: Name of the text/question column
        answer_column: Name of the answer column
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """
    # Read TSV
    df = pd.read_csv(tsv_path, sep=sep)

    if df.empty:
        return [], [], []

    # Case-insensitive column resolver
    lower_to_orig = {c.lower(): c for c in df.columns}

    def pick(col_candidates, explicit_lower: Optional[str]):
        if explicit_lower:
            # Use explicit if present
            return lower_to_orig.get(explicit_lower, explicit_lower)
        for c in col_candidates:
            if c in lower_to_orig:
                return lower_to_orig[c]
        return None

    text_col = pick(
        ["prompt", "question", "input", "instruction", "goal", "query", "text"],
        text_column.lower() if text_column else None,
    )
    ans_col = pick(
        ["answer", "target", "label", "output", "response", "gold"],
        answer_column.lower() if answer_column else None,
    )

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[text_col]) if text_col and text_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if ans_col and ans_col in row and not pd.isna(row[ans_col]):
            payload["answer"] = str(row[ans_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Return full dataset if no_split is True
    if no_split:
        return examples

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    # If not enough left, fill from start to keep sizes
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_simpleqa_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    csv_path: str = "hf://datasets/basicv8vc/SimpleQA/simple_qa_test_set.csv",
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load the SimpleQA CSV (columns: problem, answer), then deterministically split into train/val/test.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        csv_path: Path to the CSV file
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_csv(csv_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    problem_col = lower_to_orig.get("problem", "problem")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[problem_col]) if problem_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Return full dataset if no_split is True
    if no_split:
        return examples

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_simpleqa_verified_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    csv_path: str = "hf://datasets/google/simpleqa-verified/simpleqa_verified.csv",
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load the SimpleQA-Verified CSV (columns: problem, answer), then deterministically split into train/val/test.

    Note: Requires Hugging Face auth (e.g., `huggingface-cli login`) to access the dataset.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        csv_path: Path to the CSV file
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_csv(csv_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    problem_col = lower_to_orig.get("problem", "problem")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[problem_col]) if problem_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Return full dataset if no_split is True
    if no_split:
        return examples

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set

def load_seal0_dataset(
    train_size: int = 5,
    val_size: int = 5,
    test_size: int = 15,
    seed: int = 0,
    parquet_path: str = "hf://datasets/vtllms/sealqa/seal-0.parquet",
    no_split: bool = False
) -> Union[Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]], List[dspy.Example]]:
    """
    Load the SEAL-0 Parquet (columns: question, answer), then deterministically split into train/val/test.

    Note: Requires Hugging Face auth (e.g., `huggingface-cli login`) to access the dataset.

    Args:
        train_size: Number of training examples
        val_size: Number of validation examples
        test_size: Number of test examples
        seed: Random seed for reproducibility
        parquet_path: Path to the Parquet file
        no_split: If True, returns entire dataset as single list (ignores size params)

    Returns:
        If no_split=True: List of all examples
        If no_split=False: Tuple of (train_set, val_set, test_set)
    """
    df = pd.read_parquet(parquet_path)

    if df.empty:
        return [], [], []

    # Resolve columns case-insensitively
    lower_to_orig = {c.lower(): c for c in df.columns}
    question_col = lower_to_orig.get("question", "question")
    answer_col = lower_to_orig.get("answer", "answer")

    # Build DSPy examples
    examples: List[dspy.Example] = []
    for _, row in df.iterrows():
        goal_text = str(row[question_col]) if question_col in row else str(row.to_dict())
        payload = {"goal": goal_text}
        if answer_col in row and not pd.isna(row[answer_col]):
            payload["answer"] = str(row[answer_col])
        examples.append(dspy.Example(payload).with_inputs("goal"))

    # Deterministic shuffle
    rng = random.Random(seed)
    rng.shuffle(examples)

    # Return full dataset if no_split is True
    if no_split:
        return examples

    # Helper to take n items, repeating if needed
    def take(exs: List[dspy.Example], n: int) -> List[dspy.Example]:
        if n <= len(exs):
            return exs[:n]
        if not exs:
            return []
        reps = (n + len(exs) - 1) // len(exs)
        return (exs * reps)[:n]

    # Split sequentially from the shuffled list
    train_set = take(examples, train_size)
    remain = examples[len(train_set):]
    val_set = take(remain, val_size)
    remain = remain[len(val_set):]
    test_set = take(remain if remain else examples, test_size)

    return train_set, val_set, test_set