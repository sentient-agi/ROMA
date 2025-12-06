#!/usr/bin/env python3
"""
Phase 1 Validation Script for ROMA + PTC Integration
Validates all exit criteria for Phase 1: Infrastructure Setup
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required packages not installed. Run: uv sync")
    sys.exit(1)

# Initialize console
console = Console()

# Load environment
load_dotenv()


class Phase1Validator:
    """Validates Phase 1 exit criteria."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.results: List[Tuple[str, bool, str]] = []

    def check_env_var(self, var_name: str, allow_placeholder: bool = False) -> Tuple[bool, str]:
        """Check if environment variable is set and configured."""
        value = os.getenv(var_name)

        if not value:
            return False, f"Not set in .env"

        if not allow_placeholder and value.startswith("your_"):
            return False, f"Still using placeholder value"

        return True, f"Configured ({value[:20]}...)" if len(value) > 20 else f"Configured"

    def check_file_exists(self, file_path: Path) -> Tuple[bool, str]:
        """Check if a file exists."""
        if file_path.exists():
            return True, f"Found at {file_path.relative_to(self.project_root)}"
        return False, f"Not found: {file_path.relative_to(self.project_root)}"

    def check_directory_exists(self, dir_path: Path) -> Tuple[bool, str]:
        """Check if a directory exists."""
        if dir_path.exists() and dir_path.is_dir():
            return True, f"Found at {dir_path.relative_to(self.project_root) if dir_path != self.project_root.parent else dir_path}"
        return False, f"Not found"

    def check_docker_compose_service(self, service_name: str) -> Tuple[bool, str]:
        """Check if service is defined in docker-compose.yaml."""
        compose_file = self.project_root / "docker-compose.yaml"

        if not compose_file.exists():
            return False, "docker-compose.yaml not found"

        with open(compose_file) as f:
            content = f.read()
            if f"  {service_name}:" in content or f"  {service_name}\n" in content:
                return True, f"Service defined in docker-compose.yaml"

        return False, f"Service not found in docker-compose.yaml"

    def check_redis_config(self) -> Tuple[bool, str]:
        """Check Redis configuration files."""
        config_file = self.project_root / "docker" / "redis.conf"

        if not config_file.exists():
            return False, "Redis config file not found"

        # Validate config has required settings
        with open(config_file) as f:
            content = f.read()
            required = ["maxmemory", "appendonly", "port 6379"]
            missing = [r for r in required if r not in content]

            if missing:
                return False, f"Config missing: {', '.join(missing)}"

        return True, "Redis configuration valid"

    def check_python_version(self) -> Tuple[bool, str]:
        """Check Python version is 3.12+."""
        version = sys.version_info
        if version.major == 3 and version.minor >= 12:
            return True, f"Python {version.major}.{version.minor}.{version.micro}"
        return False, f"Python {version.major}.{version.minor}.{version.micro} (requires 3.12+)"

    def check_uv_installed(self) -> Tuple[bool, str]:
        """Check if uv is installed."""
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return True, f"Installed: {version}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False, "Not installed (run: curl -LsSf https://astral.sh/uv/install.sh | sh)"

    def check_git_branch(self) -> Tuple[bool, str]:
        """Check that we're on the correct git branch."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=5
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return True, f"On branch: {branch}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return False, "Unable to determine git branch"

    async def run_validation(self):
        """Run all Phase 1 validation checks."""
        console.print(Panel.fit(
            "[bold white]Phase 1: Infrastructure Setup - Validation[/bold white]\n"
            "ROMA + PTC Integration",
            border_style="cyan"
        ))

        # Define validation checks
        checks = [
            ("Environment Configuration", [
                ("DAYTONA_API_KEY set", lambda: self.check_env_var("DAYTONA_API_KEY")),
                ("ANTHROPIC_API_KEY set", lambda: self.check_env_var("ANTHROPIC_API_KEY")),
                ("REDIS_URL configured", lambda: self.check_env_var("REDIS_URL", allow_placeholder=True)),
                ("REDIS_PORT configured", lambda: self.check_env_var("REDIS_PORT", allow_placeholder=True)),
            ]),

            ("Infrastructure Files", [
                ("docker-compose.yaml exists", lambda: self.check_file_exists(self.project_root / "docker-compose.yaml")),
                ("Redis service defined", lambda: self.check_docker_compose_service("redis")),
                ("Redis config file", lambda: self.check_redis_config()),
                (".env.example updated", lambda: self.check_file_exists(self.project_root / ".env.example")),
            ]),

            ("Development Tools", [
                ("Python version 3.12+", lambda: self.check_python_version()),
                ("uv package manager", lambda: self.check_uv_installed()),
                ("Git repository", lambda: self.check_git_branch()),
            ]),

            ("PTC Repository (Manual)", [
                ("open-ptc-agent directory", lambda: self.check_directory_exists(self.project_root.parent / "open-ptc-agent")),
            ]),

            ("Test Scripts", [
                ("Daytona test script", lambda: self.check_file_exists(self.project_root / "scripts" / "ptc" / "test_daytona_sandbox.py")),
                ("Phase 1 validator", lambda: self.check_file_exists(self.project_root / "scripts" / "ptc" / "validate_phase1.py")),
            ]),
        ]

        # Run checks and collect results
        table = Table(title="Validation Results", show_header=True, header_style="bold magenta")
        table.add_column("Category", style="cyan", width=30)
        table.add_column("Check", style="white", width=35)
        table.add_column("Status", style="white", width=10)
        table.add_column("Details", style="dim", width=40)

        total_checks = 0
        passed_checks = 0
        category_results = {}

        for category_name, category_checks in checks:
            category_passed = 0
            category_total = len(category_checks)
            category_display = category_name  # Keep original name for display

            for check_name, check_func in category_checks:
                total_checks += 1
                try:
                    success, details = check_func()
                    status = "[green]✓ PASS[/green]" if success else "[red]✗ FAIL[/red]"

                    if success:
                        passed_checks += 1
                        category_passed += 1

                    table.add_row(category_display, check_name, status, details)
                    category_display = ""  # Only show category name once

                except Exception as e:
                    table.add_row(category_display, check_name, "[yellow]⚠ ERROR[/yellow]", str(e))
                    category_display = ""

            category_results[category_name] = (category_passed, category_total)

        console.print("\n")
        console.print(table)

        # Print summary
        console.print("\n" + "="*80)

        summary_table = Table(show_header=True, header_style="bold cyan")
        summary_table.add_column("Category", style="cyan")
        summary_table.add_column("Passed/Total", style="white")
        summary_table.add_column("Status", style="white")

        for cat_name, cat_checks in checks:
            if cat_name in category_results:
                passed, total = category_results[cat_name]
                status = "[green]✓[/green]" if passed == total else "[red]✗[/red]" if passed == 0 else "[yellow]⚠[/yellow]"
                summary_table.add_row(cat_name, f"{passed}/{total}", status)

        console.print("\n")
        console.print(summary_table)

        # Overall result
        success_rate = (passed_checks / total_checks * 100) if total_checks > 0 else 0

        console.print("\n")
        console.print(Panel.fit(
            f"[bold]Overall Progress[/bold]\n\n"
            f"Passed: {passed_checks}/{total_checks} ({success_rate:.1f}%)\n\n"
            f"Status: [{'green]READY FOR PHASE 2' if passed_checks == total_checks else 'yellow]IN PROGRESS' if passed_checks > total_checks * 0.5 else 'red]NEEDS ATTENTION'}[/]",
            border_style="green" if passed_checks == total_checks else "yellow" if passed_checks > total_checks * 0.5 else "red"
        ))

        # Print next steps if not complete
        if passed_checks < total_checks:
            console.print("\n[bold cyan]Next Steps:[/bold cyan]")

            if not self.check_env_var("DAYTONA_API_KEY")[0]:
                console.print("  1. Create Daytona account at https://app.daytona.io")
                console.print("  2. Generate API key and add to .env file")

            if not self.check_directory_exists(self.project_root.parent / "open-ptc-agent")[0]:
                console.print("  3. Fork https://github.com/Chen-zexi/open-ptc-agent to your GitHub")
                console.print("  4. Clone forked repository to parent directory")
                console.print("     cd .. && git clone https://github.com/YOUR_USERNAME/open-ptc-agent")

            console.print("\n[bold cyan]To start services:[/bold cyan]")
            console.print("  docker-compose up -d redis")

            console.print("\n[bold cyan]To test Daytona:[/bold cyan]")
            console.print("  uv run python scripts/ptc/test_daytona_sandbox.py")

        return passed_checks == total_checks


async def main():
    """Main entry point."""
    validator = Phase1Validator()
    success = await validator.run_validation()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Validation interrupted by user[/yellow]")
        sys.exit(1)
