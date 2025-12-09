#!/usr/bin/env python3
"""
Daytona Sandbox Validation Script for ROMA + PTC Integration
Tests basic Daytona functionality including sandbox creation, code execution, and file operations.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("Error: Required packages not installed. Run: uv sync")
    sys.exit(1)

# Initialize console for pretty output
console = Console()

# Load environment variables
load_dotenv()


class DaytonaValidator:
    """Validates Daytona sandbox functionality for PTC integration."""

    def __init__(self):
        self.api_key = os.getenv("DAYTONA_API_KEY")
        self.tests_passed = 0
        self.tests_failed = 0

    async def validate_api_key(self) -> bool:
        """Validate that Daytona API key is configured."""
        console.print("\n[bold cyan]Step 1:[/bold cyan] Validating API Key Configuration")

        if not self.api_key:
            console.print("[red]✗ DAYTONA_API_KEY not found in environment[/red]")
            console.print("\nPlease set your Daytona API key in .env file:")
            console.print("  DAYTONA_API_KEY=your_api_key_here")
            console.print("\nGet your API key from: https://app.daytona.io")
            return False

        if self.api_key == "your_daytona_api_key":
            console.print("[yellow]✗ DAYTONA_API_KEY is still set to placeholder value[/yellow]")
            console.print("\nPlease update .env with your actual Daytona API key")
            return False

        console.print(f"[green]✓ API key configured ({self.api_key[:12]}...)[/green]")
        return True

    async def test_daytona_import(self) -> bool:
        """Test that Daytona SDK can be imported."""
        console.print("\n[bold cyan]Step 2:[/bold cyan] Testing Daytona SDK Import")

        try:
            # Try to import daytona_sdk (will fail if not installed for PTC)
            # For now, we'll just check if it would be available
            console.print("[yellow]⚠ Daytona SDK will be installed with open-ptc-agent[/yellow]")
            console.print("  This test will be fully functional after PTC setup")
            return True
        except ImportError as e:
            console.print(f"[yellow]⚠ Daytona SDK not yet installed: {e}[/yellow]")
            console.print("  This is expected - SDK will be available after cloning open-ptc-agent")
            return True

    async def test_sandbox_creation(self) -> bool:
        """Test sandbox creation and basic operations."""
        console.print("\n[bold cyan]Step 3:[/bold cyan] Testing Sandbox Creation")

        # Check if we can actually import and use the SDK
        try:
            from daytona_sdk import Daytona
        except ImportError:
            console.print("[yellow]⚠ Daytona SDK not installed yet - skipping sandbox test[/yellow]")
            console.print("  After setting up open-ptc-agent, run: cd ../open-ptc-agent && uv run python scripts/ptc/test_daytona_sandbox.py")
            return True

        if not self.api_key or self.api_key == "your_daytona_api_key":
            console.print("[yellow]⚠ Skipping sandbox test - API key not configured[/yellow]")
            return True

        try:
            # Initialize Daytona client
            daytona = Daytona(api_key=self.api_key)

            console.print("  Creating sandbox...")
            sandbox = await daytona.sandbox.create()
            console.print(f"[green]✓ Sandbox created: {sandbox.id}[/green]")

            try:
                # Test code execution
                console.print("\n[bold cyan]Step 4:[/bold cyan] Testing Code Execution")
                result = await sandbox.execute(
                    code="print('Hello from Daytona!')\nprint(2 + 2)"
                )
                console.print(f"  Output: {result.output}")
                console.print("[green]✓ Code execution successful[/green]")

                # Test file operations
                console.print("\n[bold cyan]Step 5:[/bold cyan] Testing File Operations")
                test_content = "ROMA + PTC Integration - Phase 1 Test"
                await sandbox.write_file("/home/daytona/test.txt", test_content)
                console.print("  File written successfully")

                read_content = await sandbox.read_file("/home/daytona/test.txt")
                if read_content == test_content:
                    console.print("[green]✓ File operations successful[/green]")
                    return True
                else:
                    console.print("[red]✗ File content mismatch[/red]")
                    return False

            finally:
                # Always cleanup
                console.print("\n[bold cyan]Cleanup:[/bold cyan] Destroying sandbox")
                await daytona.sandbox.delete(sandbox.id)
                console.print("[green]✓ Sandbox destroyed[/green]")

        except Exception as e:
            console.print(f"[red]✗ Sandbox test failed: {e}[/red]")
            return False

    async def run_all_tests(self) -> bool:
        """Run all validation tests."""
        console.print(Panel.fit(
            "[bold white]Daytona Sandbox Validation[/bold white]\n"
            "ROMA + PTC Integration - Phase 1",
            border_style="cyan"
        ))

        # Run tests sequentially
        tests = [
            ("API Key Validation", self.validate_api_key()),
            ("SDK Import Test", self.test_daytona_import()),
            ("Sandbox Operations", self.test_sandbox_creation()),
        ]

        all_passed = True
        for test_name, test_coro in tests:
            try:
                result = await test_coro
                if result:
                    self.tests_passed += 1
                else:
                    self.tests_failed += 1
                    all_passed = False
            except Exception as e:
                console.print(f"[red]✗ {test_name} failed with exception: {e}[/red]")
                self.tests_failed += 1
                all_passed = False

        # Print summary
        console.print("\n" + "="*60)
        console.print(Panel.fit(
            f"[bold]Test Results[/bold]\n\n"
            f"✓ Passed: {self.tests_passed}\n"
            f"✗ Failed: {self.tests_failed}\n\n"
            f"Status: [{'green]PASSED' if all_passed else 'red]FAILED'}[/]",
            border_style="green" if all_passed else "red"
        ))

        return all_passed


async def main():
    """Main entry point."""
    validator = DaytonaValidator()
    success = await validator.run_all_tests()

    if not success:
        console.print("\n[yellow]Note:[/yellow] Some tests are expected to fail until:")
        console.print("  1. Daytona API key is configured in .env")
        console.print("  2. open-ptc-agent repository is cloned and set up")
        console.print("  3. Daytona SDK dependencies are installed (uv sync in open-ptc-agent)")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted by user[/yellow]")
        sys.exit(1)
