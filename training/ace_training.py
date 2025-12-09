"""
ACE Training Script - Train ROMA+PTC+ACE on Micro SaaS Scenarios

This script executes training scenarios to build up the ACE skillbook,
preparing the system for production use.

Usage:
    python training/ace_training.py --scenarios training/scenarios.yaml
    python training/ace_training.py --interactive  # Add scenarios interactively
"""

import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import yaml
from loguru import logger

try:
    from roma_dspy.integrations import create_ace_executor, ACE_AVAILABLE
    from roma_dspy.types import TaskType
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure ROMA is installed: pip install -e .")
    exit(1)


class TrainingScenario:
    """Represents a single training scenario."""

    def __init__(
        self,
        name: str,
        goal: str,
        requirements: List[str] = None,
        task_type: str = "CODE_INTERPRET",
        expected_output: Optional[str] = None,
        category: str = "general",
    ):
        self.name = name
        self.goal = goal
        self.requirements = requirements or []
        self.task_type = TaskType[task_type] if isinstance(task_type, str) else task_type
        self.expected_output = expected_output
        self.category = category

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "name": self.name,
            "goal": self.goal,
            "requirements": self.requirements,
            "task_type": self.task_type.value if hasattr(self.task_type, 'value') else str(self.task_type),
            "expected_output": self.expected_output,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingScenario":
        """Create from dictionary."""
        return cls(**data)


class TrainingResults:
    """Tracks training progress and results."""

    def __init__(self, output_path: str = "./training/results"):
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def add_result(
        self,
        scenario: TrainingScenario,
        success: bool,
        output: str,
        metadata: Dict[str, Any],
        error: Optional[str] = None,
    ):
        """Add a training result."""
        result = {
            "timestamp": datetime.now().isoformat(),
            "scenario": scenario.to_dict(),
            "success": success,
            "output_preview": output[:500] if output else None,
            "metadata": metadata,
            "error": error,
        }
        self.results.append(result)

    def save(self):
        """Save results to JSON file."""
        results_file = self.output_path / f"training_results_{self.session_id}.json"
        with open(results_file, "w") as f:
            json.dump(
                {
                    "session_id": self.session_id,
                    "total_scenarios": len(self.results),
                    "successful": sum(1 for r in self.results if r["success"]),
                    "failed": sum(1 for r in self.results if not r["success"]),
                    "results": self.results,
                },
                f,
                indent=2,
            )
        logger.info(f"💾 Results saved to: {results_file}")
        return results_file

    def print_summary(self):
        """Print training summary."""
        total = len(self.results)
        successful = sum(1 for r in self.results if r["success"])
        failed = total - successful

        logger.info("\n" + "=" * 60)
        logger.info("📊 TRAINING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total scenarios: {total}")
        logger.info(f"✅ Successful: {successful} ({successful/total*100:.1f}%)")
        logger.info(f"❌ Failed: {failed} ({failed/total*100:.1f}%)")

        # Category breakdown
        categories = {}
        for result in self.results:
            cat = result["scenario"]["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "success": 0}
            categories[cat]["total"] += 1
            if result["success"]:
                categories[cat]["success"] += 1

        logger.info("\n📁 By Category:")
        for cat, stats in categories.items():
            success_rate = stats["success"] / stats["total"] * 100
            logger.info(f"  {cat}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")

        # Cost summary
        total_cost = sum(
            r["metadata"].get("cost_usd", 0)
            for r in self.results
            if r["success"]
        )
        total_tokens = sum(
            r["metadata"].get("tokens_used", 0)
            for r in self.results
            if r["success"]
        )
        logger.info(f"\n💰 Total Cost: ${total_cost:.4f}")
        logger.info(f"🔢 Total Tokens: {total_tokens:,}")
        logger.info(f"📈 Avg Cost/Scenario: ${total_cost/max(successful, 1):.4f}")


class ACETrainer:
    """Manages ACE training process."""

    def __init__(
        self,
        ptc_base_url: str = "http://localhost:8002",
        skillbook_path: str = "./training/skillbooks/training.json",
        ace_model: str = "gpt-4o-mini",
    ):
        self.executor = create_ace_executor(
            ptc_base_url=ptc_base_url,
            skillbook_path=skillbook_path,
            ace_model=ace_model,
            async_learning=True,
        )
        self.results = TrainingResults()

    async def run_scenario(self, scenario: TrainingScenario) -> bool:
        """Execute a single training scenario."""
        logger.info(f"\n▶️  Running: {scenario.name}")
        logger.info(f"   Goal: {scenario.goal}")
        logger.info(f"   Category: {scenario.category}")

        try:
            result = await self.executor.aforward(
                goal=scenario.goal,
                task_type=scenario.task_type,
                requirements=scenario.requirements,
            )

            # Check for errors in output
            output = result.output if hasattr(result, 'output') else str(result)
            success = "error" not in output.lower()[:200]

            # Extract metadata
            metadata = {}
            if hasattr(result, '_metadata'):
                metadata = result._metadata

            # Log result
            if success:
                logger.info(f"   ✅ Success")
                if 'performance_score' in metadata:
                    logger.info(f"   📊 Score: {metadata['performance_score']:.2f}")
                if 'cost_usd' in metadata:
                    logger.info(f"   💰 Cost: ${metadata['cost_usd']:.6f}")
            else:
                logger.warning(f"   ⚠️  Output contains error indicators")

            # Record result
            self.results.add_result(
                scenario=scenario,
                success=success,
                output=output,
                metadata=metadata,
            )

            return success

        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            self.results.add_result(
                scenario=scenario,
                success=False,
                output="",
                metadata={},
                error=str(e),
            )
            return False

    async def run_all_scenarios(self, scenarios: List[TrainingScenario]):
        """Run all training scenarios."""
        logger.info(f"🎯 Starting training with {len(scenarios)} scenarios\n")

        initial_stats = self.executor.get_learning_stats()
        logger.info(f"📚 Initial skills: {initial_stats['total_skills_learned']}")

        for i, scenario in enumerate(scenarios, 1):
            logger.info(f"\n[{i}/{len(scenarios)}]")
            await self.run_scenario(scenario)

            # Show skill progress every 10 scenarios
            if i % 10 == 0:
                stats = self.executor.get_learning_stats()
                logger.info(f"\n📚 Skills learned: {stats['total_skills_learned']}")

        # Final summary
        final_stats = self.executor.get_learning_stats()
        logger.info(f"\n📚 Final skills: {final_stats['total_skills_learned']}")
        logger.info(f"📈 Skills gained: {final_stats['total_skills_learned'] - initial_stats['total_skills_learned']}")

        self.results.print_summary()
        self.results.save()

        return self.results


def load_scenarios_from_yaml(yaml_path: str) -> List[TrainingScenario]:
    """Load training scenarios from YAML file."""
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    scenarios = []
    for scenario_data in data.get("scenarios", []):
        scenarios.append(TrainingScenario.from_dict(scenario_data))

    logger.info(f"📁 Loaded {len(scenarios)} scenarios from {yaml_path}")
    return scenarios


def load_scenarios_from_json(json_path: str) -> List[TrainingScenario]:
    """Load training scenarios from JSON file."""
    with open(json_path, "r") as f:
        data = json.load(f)

    scenarios = []
    for scenario_data in data.get("scenarios", []):
        scenarios.append(TrainingScenario.from_dict(scenario_data))

    logger.info(f"📁 Loaded {len(scenarios)} scenarios from {json_path}")
    return scenarios


def create_example_scenarios() -> List[TrainingScenario]:
    """Create example training scenarios."""
    scenarios = [
        # Email validation SaaS
        TrainingScenario(
            name="Email Validation API",
            goal="Build a FastAPI endpoint for email validation",
            requirements=[
                "Check MX records",
                "Validate syntax",
                "Block disposable domains",
                "Include API key authentication",
            ],
            category="micro_saas",
        ),
        # URL shortener
        TrainingScenario(
            name="URL Shortener Service",
            goal="Create a URL shortening service",
            requirements=[
                "Generate short codes",
                "Track click analytics",
                "Custom domains support",
                "Rate limiting",
            ],
            category="micro_saas",
        ),
        # Webhook forwarding
        TrainingScenario(
            name="Webhook Forwarder",
            goal="Build a webhook forwarding service",
            requirements=[
                "Receive webhooks",
                "Forward to multiple endpoints",
                "Retry failed deliveries",
                "Log all events",
            ],
            category="automation",
        ),
        # Data validator
        TrainingScenario(
            name="JSON Schema Validator API",
            goal="Create JSON schema validation service",
            requirements=[
                "Validate against JSON schema",
                "Return detailed error messages",
                "Support custom formats",
                "Cache schemas",
            ],
            category="micro_saas",
        ),
        # Screenshot service
        TrainingScenario(
            name="Screenshot Capture API",
            goal="Build website screenshot service",
            requirements=[
                "Capture full page screenshots",
                "Customizable viewport",
                "Upload to S3",
                "Return image URL",
            ],
            category="micro_saas",
        ),
    ]

    logger.info(f"📝 Created {len(scenarios)} example scenarios")
    return scenarios


async def interactive_training():
    """Interactive mode - add scenarios manually."""
    logger.info("🎮 Interactive Training Mode")
    logger.info("Add scenarios one at a time. Type 'done' when finished.\n")

    trainer = ACETrainer()
    scenarios = []

    while True:
        print("\n" + "-" * 60)
        name = input("Scenario name (or 'done' to start training): ").strip()
        if name.lower() == "done":
            break

        goal = input("Goal/Description: ").strip()
        reqs = input("Requirements (comma-separated): ").strip()
        requirements = [r.strip() for r in reqs.split(",") if r.strip()]
        category = input("Category (micro_saas/automation/ai_agent): ").strip() or "general"

        scenario = TrainingScenario(
            name=name,
            goal=goal,
            requirements=requirements,
            category=category,
        )
        scenarios.append(scenario)
        logger.info(f"✅ Added scenario: {name}")

    if scenarios:
        logger.info(f"\n🎯 Starting training with {len(scenarios)} scenarios")
        await trainer.run_all_scenarios(scenarios)
    else:
        logger.warning("No scenarios added")


async def main():
    """Main training entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ACE Training Script")
    parser.add_argument(
        "--scenarios",
        type=str,
        help="Path to scenarios file (YAML or JSON)",
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Run example scenarios",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode - add scenarios manually",
    )
    parser.add_argument(
        "--ptc-url",
        type=str,
        default="http://localhost:8002",
        help="PTC service URL",
    )
    parser.add_argument(
        "--skillbook",
        type=str,
        default="./training/skillbooks/training.json",
        help="Skillbook path",
    )

    args = parser.parse_args()

    # Check ACE availability
    if not ACE_AVAILABLE:
        logger.error("❌ ACE not available")
        logger.error("Install with: pip install /home/user/ace-repo/")
        return

    logger.info("🚀 ACE Training System")
    logger.info("=" * 60)

    # Determine scenarios to run
    scenarios = []

    if args.interactive:
        await interactive_training()
        return

    if args.scenarios:
        # Load from file
        scenario_path = Path(args.scenarios)
        if scenario_path.suffix == ".yaml" or scenario_path.suffix == ".yml":
            scenarios = load_scenarios_from_yaml(str(scenario_path))
        elif scenario_path.suffix == ".json":
            scenarios = load_scenarios_from_json(str(scenario_path))
        else:
            logger.error(f"Unsupported file format: {scenario_path.suffix}")
            return
    elif args.examples:
        # Use example scenarios
        scenarios = create_example_scenarios()
    else:
        # Default: create examples
        logger.info("No scenarios specified. Using example scenarios.")
        logger.info("Use --scenarios <file> or --interactive for custom scenarios.\n")
        scenarios = create_example_scenarios()

    # Create trainer and run
    trainer = ACETrainer(
        ptc_base_url=args.ptc_url,
        skillbook_path=args.skillbook,
    )

    await trainer.run_all_scenarios(scenarios)


if __name__ == "__main__":
    asyncio.run(main())
