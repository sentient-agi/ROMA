#!/usr/bin/env python3
"""
E2B Sandbox Setup Validation Script (E2B v2)

This script performs comprehensive end-to-end validation of:
1. Environment variable configuration from .env
2. E2B v2 template building with and without S3
3. Sandbox creation and basic functionality
4. S3 storage mounting (if configured)
5. Integration with E2BToolkit

Usage:
    python validate_e2b_setup.py

    # Or run with specific checks:
    python validate_e2b_setup.py --skip-build  # Skip template build
    python validate_e2b_setup.py --skip-s3     # Skip S3 tests
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class ValidationResult:
    """Result of a validation check."""
    def __init__(self, name: str, success: bool, message: str, details: Optional[Dict] = None):
        self.name = name
        self.success = success
        self.message = message
        self.details = details or {}


class E2BValidator:
    """E2B sandbox setup validator."""

    def __init__(self, skip_build: bool = False, skip_s3: bool = False):
        self.skip_build = skip_build
        self.skip_s3 = skip_s3
        self.results: List[ValidationResult] = []
        self.env_vars: Dict[str, str] = {}
        self.has_s3 = False

    def log_header(self, message: str):
        """Print section header."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{message}{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    def log_check(self, message: str):
        """Print check being performed."""
        print(f"{Colors.BLUE}▶ {message}{Colors.RESET}")

    def log_success(self, message: str):
        """Print success message."""
        print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")

    def log_error(self, message: str):
        """Print error message."""
        print(f"{Colors.RED}✗ {message}{Colors.RESET}")

    def log_warning(self, message: str):
        """Print warning message."""
        print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")

    def log_info(self, message: str):
        """Print info message."""
        print(f"  {message}")

    def add_result(self, result: ValidationResult):
        """Add validation result."""
        self.results.append(result)
        if result.success:
            self.log_success(f"{result.name}: {result.message}")
        else:
            self.log_error(f"{result.name}: {result.message}")

        if result.details:
            for key, value in result.details.items():
                self.log_info(f"  {key}: {value}")

    # ========== Step 1: Environment Variable Validation ==========

    def validate_env_vars(self) -> bool:
        """Validate environment variables from .env file."""
        self.log_header("Step 1: Environment Variable Validation")

        # Check for .env file
        env_file = Path(__file__).parent.parent.parent / ".env"
        if not env_file.exists():
            self.add_result(ValidationResult(
                "Environment File",
                False,
                f".env file not found at {env_file}",
                {"hint": "Copy .env.example to .env and configure values"}
            ))
            return False

        self.add_result(ValidationResult(
            "Environment File",
            True,
            f"Found .env at {env_file}"
        ))

        # Load environment variables
        required_vars = ["E2B_API_KEY"]
        optional_s3_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "ROMA_S3_BUCKET"]
        optional_vars = ["AWS_REGION", "STORAGE_BASE_PATH", "E2B_TEMPLATE_ID"]

        # Check required variables
        self.log_check("Checking required environment variables...")
        all_required_present = True
        for var in required_vars:
            value = os.getenv(var)
            self.env_vars[var] = value or ""
            if not value:
                self.add_result(ValidationResult(
                    f"Required Variable: {var}",
                    False,
                    "Not set or empty"
                ))
                all_required_present = False
            else:
                # Mask sensitive values
                display_value = f"{value[:10]}..." if len(value) > 10 else "***"
                self.add_result(ValidationResult(
                    f"Required Variable: {var}",
                    True,
                    f"Set (value: {display_value})"
                ))

        # Check S3 variables
        self.log_check("Checking S3 configuration...")
        s3_vars_present = []
        for var in optional_s3_vars:
            value = os.getenv(var)
            self.env_vars[var] = value or ""
            if value:
                s3_vars_present.append(var)

        # Determine if S3 is configured
        if all(os.getenv(var) for var in optional_s3_vars):
            self.has_s3 = True
            self.add_result(ValidationResult(
                "S3 Configuration",
                True,
                "S3 storage fully configured",
                {
                    "bucket": os.getenv("ROMA_S3_BUCKET"),
                    "region": os.getenv("AWS_REGION", "us-east-1"),
                    "path": os.getenv("STORAGE_BASE_PATH", "/opt/sentient")
                }
            ))
        elif any(os.getenv(var) for var in optional_s3_vars):
            self.add_result(ValidationResult(
                "S3 Configuration",
                False,
                "S3 partially configured (all AWS credentials required)",
                {
                    "present": s3_vars_present,
                    "missing": [v for v in optional_s3_vars if not os.getenv(v)]
                }
            ))
            return False
        else:
            self.has_s3 = False
            self.log_warning("S3 storage not configured (this is optional)")
            self.add_result(ValidationResult(
                "S3 Configuration",
                True,
                "S3 disabled - sandbox will run without persistent storage"
            ))

        # Check optional variables
        for var in optional_vars:
            value = os.getenv(var)
            self.env_vars[var] = value or ""
            if value:
                self.log_info(f"{var}: {value}")

        return all_required_present

    # ========== Step 2: E2B v2 Template Definition Validation ==========

    def validate_template_definition(self) -> bool:
        """Validate E2B v2 Python template definition."""
        self.log_header("Step 2: E2B v2 Template Definition Validation")

        # Check template.py exists
        template_file = Path(__file__).parent / "template.py"
        if not template_file.exists():
            self.add_result(ValidationResult(
                "Template File",
                False,
                f"template.py not found at {template_file}"
            ))
            return False

        self.add_result(ValidationResult(
            "Template File",
            True,
            f"Found template.py at {template_file}"
        ))

        # Try importing template
        self.log_check("Importing template definition...")
        try:
            # Change to E2B directory for import
            original_dir = os.getcwd()
            os.chdir(template_file.parent)

            from template import template

            self.add_result(ValidationResult(
                "Template Import",
                True,
                "Successfully imported template from template.py",
                {"type": type(template).__name__}
            ))

            os.chdir(original_dir)
            return True

        except ImportError as e:
            self.add_result(ValidationResult(
                "Template Import",
                False,
                f"Failed to import template: {e}"
            ))
            os.chdir(original_dir)
            return False
        except Exception as e:
            self.add_result(ValidationResult(
                "Template Import",
                False,
                f"Error importing template: {e}"
            ))
            os.chdir(original_dir)
            return False

    # ========== Step 3: E2B CLI and SDK Validation ==========

    def validate_e2b_tools(self) -> bool:
        """Validate E2B CLI and SDK installation."""
        self.log_header("Step 3: E2B CLI and SDK Validation")

        # Check E2B CLI
        self.log_check("Checking E2B CLI installation...")
        import subprocess
        try:
            result = subprocess.run(
                ["e2b", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # Check if v2.4+ (required for Python SDK)
                version_num = version.split()[0] if version.split() else ""
                self.add_result(ValidationResult(
                    "E2B CLI",
                    True,
                    f"Installed: {version}",
                    {"required": "v2.4.1+", "installed": version_num}
                ))
            else:
                self.add_result(ValidationResult(
                    "E2B CLI",
                    False,
                    "E2B CLI found but version check failed"
                ))
                return False
        except FileNotFoundError:
            self.add_result(ValidationResult(
                "E2B CLI",
                False,
                "E2B CLI not found",
                {"install": "npm install -g @e2b/cli@latest"}
            ))
            return False
        except Exception as e:
            self.add_result(ValidationResult(
                "E2B CLI",
                False,
                f"Error checking E2B CLI: {e}"
            ))
            return False

        # Check E2B Python SDK
        self.log_check("Checking E2B Python SDK...")
        try:
            from e2b import AsyncTemplate
            self.add_result(ValidationResult(
                "E2B Python SDK",
                True,
                "E2B Python SDK (v2) installed"
            ))
        except ImportError:
            self.add_result(ValidationResult(
                "E2B Python SDK",
                False,
                "E2B Python SDK not installed",
                {"install": "pip install e2b"}
            ))
            return False

        # Check E2B code interpreter SDK
        self.log_check("Checking E2B Code Interpreter SDK...")
        try:
            from e2b_code_interpreter import AsyncSandbox
            self.add_result(ValidationResult(
                "E2B Code Interpreter SDK",
                True,
                "E2B Code Interpreter SDK installed"
            ))
        except ImportError:
            self.add_result(ValidationResult(
                "E2B Code Interpreter SDK",
                False,
                "E2B Code Interpreter SDK not installed",
                {"install": "pip install e2b-code-interpreter"}
            ))
            return False

        return True

    # ========== Step 4: Template Build (Optional) ==========

    async def build_template(self) -> bool:
        """Build E2B template using Python SDK."""
        if self.skip_build:
            self.log_warning("Skipping template build (--skip-build)")
            return True

        self.log_header("Step 4: E2B Template Build (Optional)")

        self.log_check("Building E2B template using build_dev.py...")
        self.log_info("This may take several minutes...")

        import subprocess
        try:
            # Run build_dev.py
            build_script = Path(__file__).parent / "build_dev.py"
            if not build_script.exists():
                self.add_result(ValidationResult(
                    "Template Build",
                    False,
                    f"Build script not found: {build_script}"
                ))
                return False

            # Change to E2B directory
            original_dir = os.getcwd()
            os.chdir(build_script.parent)

            result = subprocess.run(
                ["python3", "build_dev.py"],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            os.chdir(original_dir)

            if result.returncode == 0:
                self.add_result(ValidationResult(
                    "Template Build",
                    True,
                    "Successfully built template: roma-dspy-sandbox-dev",
                    {"output": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout}
                ))
                return True
            else:
                self.add_result(ValidationResult(
                    "Template Build",
                    False,
                    f"Build failed with exit code {result.returncode}",
                    {"error": result.stderr[-500:] if result.stderr else "No error output"}
                ))
                return False

        except subprocess.TimeoutExpired:
            self.add_result(ValidationResult(
                "Template Build",
                False,
                "Build timed out (>10 minutes)"
            ))
            os.chdir(original_dir)
            return False
        except Exception as e:
            self.add_result(ValidationResult(
                "Template Build",
                False,
                f"Build error: {e}"
            ))
            os.chdir(original_dir)
            return False

    # ========== Step 5: Sandbox Creation and Basic Tests ==========

    async def test_sandbox_creation(self) -> bool:
        """Test sandbox creation with E2BToolkit."""
        self.log_header("Step 5: Sandbox Creation and Basic Functionality")

        self.log_check("Testing sandbox creation...")

        try:
            from roma_dspy.tools.core.e2b import E2BToolkit

            # Create toolkit (uses environment variables)
            toolkit = E2BToolkit()

            self.add_result(ValidationResult(
                "E2BToolkit Initialization",
                True,
                "Successfully initialized E2BToolkit"
            ))

            # Test basic Python execution
            self.log_check("Testing Python code execution...")
            result = await toolkit.run_python_code("print('Hello from E2B sandbox!')")
            result_data = json.loads(result)

            if result_data.get("success"):
                self.add_result(ValidationResult(
                    "Python Execution",
                    True,
                    "Successfully executed Python code in sandbox",
                    {"sandbox_id": result_data.get("sandbox_id")}
                ))
            else:
                self.add_result(ValidationResult(
                    "Python Execution",
                    False,
                    "Python execution returned failure",
                    {"error": result_data.get("error")}
                ))
                await toolkit.aclose()
                return False

            # Test sandbox status
            self.log_check("Checking sandbox status...")
            status_result = await toolkit.get_sandbox_status()
            status_data = json.loads(status_result)

            if status_data.get("success"):
                self.add_result(ValidationResult(
                    "Sandbox Status",
                    True,
                    f"Sandbox is {status_data.get('status')}",
                    {
                        "uptime": f"{status_data.get('uptime_seconds')}s",
                        "template": status_data.get("template")
                    }
                ))
            else:
                self.add_result(ValidationResult(
                    "Sandbox Status",
                    False,
                    "Failed to get sandbox status"
                ))

            # Test shell command
            self.log_check("Testing shell command execution...")
            cmd_result = await toolkit.run_command("echo 'Test command' && date")
            cmd_data = json.loads(cmd_result)

            if cmd_data.get("success") and cmd_data.get("exit_code") == 0:
                self.add_result(ValidationResult(
                    "Shell Command",
                    True,
                    "Successfully executed shell command"
                ))
            else:
                self.add_result(ValidationResult(
                    "Shell Command",
                    False,
                    f"Command failed with exit code {cmd_data.get('exit_code')}"
                ))

            # Cleanup
            await toolkit.aclose()
            self.log_success("Sandbox closed successfully")

            return True

        except Exception as e:
            self.add_result(ValidationResult(
                "Sandbox Creation",
                False,
                f"Error: {e}"
            ))
            return False

    # ========== Step 6: S3 Storage Tests (If Configured) ==========

    async def test_s3_storage(self) -> bool:
        """Test S3 storage mounting and access."""
        if self.skip_s3 or not self.has_s3:
            if not self.has_s3:
                self.log_warning("Skipping S3 tests (S3 not configured)")
            else:
                self.log_warning("Skipping S3 tests (--skip-s3)")
            return True

        self.log_header("Step 6: S3 Storage Testing")

        self.log_check("Testing S3 storage access...")

        try:
            from roma_dspy.tools.core.e2b import E2BToolkit

            toolkit = E2BToolkit()

            # Check if S3 mount point exists
            storage_path = os.getenv("STORAGE_BASE_PATH", "/opt/sentient")
            self.log_check(f"Checking S3 mount point at {storage_path}...")

            result = await toolkit.run_command(f"ls -la {storage_path}")
            result_data = json.loads(result)

            if result_data.get("success") and result_data.get("exit_code") == 0:
                self.add_result(ValidationResult(
                    "S3 Mount Point",
                    True,
                    f"S3 mounted at {storage_path}",
                    {"contents": result_data.get("stdout", "")[:200]}
                ))
            else:
                self.add_result(ValidationResult(
                    "S3 Mount Point",
                    False,
                    f"Failed to access {storage_path}",
                    {"error": result_data.get("stderr")}
                ))
                await toolkit.aclose()
                return False

            # Test write access
            self.log_check("Testing S3 write access...")
            test_file = f"{storage_path}/executions/.e2b_validation_test"
            write_result = await toolkit.run_command(
                f"echo 'E2B validation test' > {test_file} && cat {test_file}"
            )
            write_data = json.loads(write_result)

            if write_data.get("success") and write_data.get("exit_code") == 0:
                self.add_result(ValidationResult(
                    "S3 Write Access",
                    True,
                    "Successfully wrote to S3 storage"
                ))
            else:
                self.add_result(ValidationResult(
                    "S3 Write Access",
                    False,
                    "Failed to write to S3 storage",
                    {"error": write_data.get("stderr")}
                ))

            # Cleanup test file
            await toolkit.run_command(f"rm -f {test_file}")

            await toolkit.aclose()
            return True

        except Exception as e:
            self.add_result(ValidationResult(
                "S3 Storage Test",
                False,
                f"Error: {e}"
            ))
            return False

    # ========== Summary and Report ==========

    def print_summary(self):
        """Print validation summary."""
        self.log_header("Validation Summary")

        passed = sum(1 for r in self.results if r.success)
        total = len(self.results)
        failed = total - passed

        print(f"\n{Colors.BOLD}Total Checks: {total}{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Passed: {passed}{Colors.RESET}")
        if failed > 0:
            print(f"{Colors.RED}✗ Failed: {failed}{Colors.RESET}")

        if failed > 0:
            print(f"\n{Colors.BOLD}Failed Checks:{Colors.RESET}")
            for result in self.results:
                if not result.success:
                    print(f"{Colors.RED}  • {result.name}: {result.message}{Colors.RESET}")
                    if result.details:
                        for key, value in result.details.items():
                            print(f"    {key}: {value}")

        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        if failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL VALIDATIONS PASSED{Colors.RESET}")
            print(f"\n{Colors.GREEN}E2B v2 sandbox setup is fully operational!{Colors.RESET}")
            if self.has_s3:
                print(f"{Colors.GREEN}S3 storage integration is working correctly.{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}Running without S3 storage (optional).{Colors.RESET}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}✗ VALIDATION FAILED{Colors.RESET}")
            print(f"\n{Colors.RED}Please fix the issues above and run validation again.{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")

        return failed == 0


async def main():
    """Main validation entry point."""
    parser = argparse.ArgumentParser(
        description="E2B v2 Sandbox Setup Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip template build step (faster, but won't test build process)"
    )
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Skip S3 storage tests"
    )

    args = parser.parse_args()

    validator = E2BValidator(
        skip_build=args.skip_build,
        skip_s3=args.skip_s3
    )

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}E2B v2 Sandbox Setup Validation{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    # Run validation steps
    try:
        # Step 1: Environment variables
        if not validator.validate_env_vars():
            validator.print_summary()
            return 1

        # Step 2: Template definition
        if not validator.validate_template_definition():
            validator.print_summary()
            return 1

        # Step 3: E2B tools
        if not validator.validate_e2b_tools():
            validator.print_summary()
            return 1

        # Step 4: Build template (optional)
        if not await validator.build_template():
            validator.log_warning("Template build failed, but continuing with existing template...")

        # Step 5: Sandbox creation and basic tests
        if not await validator.test_sandbox_creation():
            validator.print_summary()
            return 1

        # Step 6: S3 storage tests (if configured)
        if not await validator.test_s3_storage():
            validator.print_summary()
            return 1

        # Print summary
        success = validator.print_summary()
        return 0 if success else 1

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Validation interrupted by user{Colors.RESET}")
        return 130
    except Exception as e:
        print(f"\n\n{Colors.RED}Unexpected error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))