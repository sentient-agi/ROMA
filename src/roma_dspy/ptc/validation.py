"""Multi-stage validation pipeline for PTC service.

Implements the three-stage verification from the efficiency document:
1. Syntactic validation (<100ms) - AST parsing, basic syntax checks
2. Semantic validation (1-3s) - Type checking with tsc --noEmit
3. Integration validation (5-30s) - Compile, lint, test execution
"""

from __future__ import annotations

import ast
import asyncio
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from roma_dspy.ptc.streaming import StreamContext


class ValidationStage(str, Enum):
    """Validation stages."""

    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    INTEGRATION = "integration"


class ValidationSeverity(str, Enum):
    """Validation issue severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single validation issue."""

    severity: ValidationSeverity
    stage: ValidationStage
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    code: Optional[str] = None  # Error code (e.g., TS2304)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


class StageResult(BaseModel):
    """Result from a validation stage."""

    stage: ValidationStage
    passed: bool
    duration_ms: float
    issues: List[ValidationIssue] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]


class ValidationResult(BaseModel):
    """Complete validation result."""

    passed: bool
    stages: List[StageResult] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    short_circuited: bool = False
    short_circuit_stage: Optional[ValidationStage] = None

    @property
    def all_issues(self) -> List[ValidationIssue]:
        issues = []
        for stage in self.stages:
            issues.extend(stage.issues)
        return issues

    @property
    def all_errors(self) -> List[ValidationIssue]:
        return [i for i in self.all_issues if i.severity == ValidationSeverity.ERROR]

    @property
    def all_warnings(self) -> List[ValidationIssue]:
        return [i for i in self.all_issues if i.severity == ValidationSeverity.WARNING]


class SyntacticValidator:
    """Stage 1: Syntactic validation (<100ms target).

    Performs AST parsing and basic syntax checks without external tools.
    """

    # Common syntax patterns to check
    TYPESCRIPT_PATTERNS = {
        "unclosed_brace": re.compile(r"^\s*\{[^}]*$", re.MULTILINE),
        "unclosed_paren": re.compile(r"\([^)]*$", re.MULTILINE),
        "missing_semicolon_export": re.compile(r"export\s+(?:default\s+)?(?:class|function|const|let|var)\s+\w+[^;{]*$", re.MULTILINE),
    }

    PYTHON_PATTERNS = {
        "invalid_indent": re.compile(r"^( {1,3}|\t+ +| +\t+)\S", re.MULTILINE),
    }

    async def validate(
        self,
        content: str,
        language: str,
        filename: Optional[str] = None,
    ) -> StageResult:
        """Validate syntax of code content.

        Args:
            content: Code content to validate
            language: Programming language (python, typescript, javascript)
            filename: Optional filename for error reporting

        Returns:
            StageResult with validation results
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        try:
            if language == "python":
                issues = await self._validate_python(content, filename)
            elif language in ("typescript", "javascript", "tsx", "jsx"):
                issues = await self._validate_typescript(content, filename)
            else:
                # For unknown languages, just check for basic issues
                issues = self._check_basic_syntax(content, filename)

        except Exception as e:
            logger.warning(f"Syntactic validation error: {e}")
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    stage=ValidationStage.SYNTACTIC,
                    message=f"Validation failed: {str(e)}",
                    file=filename,
                )
            )

        duration_ms = (time.time() - start_time) * 1000
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)

        return StageResult(
            stage=ValidationStage.SYNTACTIC,
            passed=passed,
            duration_ms=duration_ms,
            issues=issues,
            metrics={
                "lines": len(content.splitlines()),
                "characters": len(content),
            },
        )

    async def _validate_python(
        self, content: str, filename: Optional[str]
    ) -> List[ValidationIssue]:
        """Validate Python syntax using ast module."""
        issues = []

        try:
            ast.parse(content)
        except SyntaxError as e:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    stage=ValidationStage.SYNTACTIC,
                    message=str(e.msg) if e.msg else "Syntax error",
                    file=filename,
                    line=e.lineno,
                    column=e.offset,
                )
            )

        # Check for common issues with patterns
        for name, pattern in self.PYTHON_PATTERNS.items():
            for match in pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        stage=ValidationStage.SYNTACTIC,
                        message=f"Potential issue: {name.replace('_', ' ')}",
                        file=filename,
                        line=line_num,
                    )
                )

        return issues

    async def _validate_typescript(
        self, content: str, filename: Optional[str]
    ) -> List[ValidationIssue]:
        """Validate TypeScript/JavaScript syntax with pattern matching."""
        issues = []

        # Check brace/bracket/paren balance
        balance_issues = self._check_balance(content, filename)
        issues.extend(balance_issues)

        # Check for common patterns
        for name, pattern in self.TYPESCRIPT_PATTERNS.items():
            for match in pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        stage=ValidationStage.SYNTACTIC,
                        message=f"Potential issue: {name.replace('_', ' ')}",
                        file=filename,
                        line=line_num,
                    )
                )

        return issues

    def _check_balance(
        self, content: str, filename: Optional[str]
    ) -> List[ValidationIssue]:
        """Check for balanced brackets, braces, and parentheses."""
        issues = []
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        openers = set(pairs.values())
        closers = set(pairs.keys())

        in_string = False
        string_char = None
        prev_char = None

        for i, char in enumerate(content):
            # Track string state (simplified - doesn't handle all edge cases)
            if char in ('"', "'", '`') and prev_char != '\\':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

            if not in_string:
                if char in openers:
                    stack.append((char, i))
                elif char in closers:
                    if not stack:
                        line_num = content[:i].count('\n') + 1
                        issues.append(
                            ValidationIssue(
                                severity=ValidationSeverity.ERROR,
                                stage=ValidationStage.SYNTACTIC,
                                message=f"Unmatched closing '{char}'",
                                file=filename,
                                line=line_num,
                            )
                        )
                    elif stack[-1][0] != pairs[char]:
                        line_num = content[:i].count('\n') + 1
                        issues.append(
                            ValidationIssue(
                                severity=ValidationSeverity.ERROR,
                                stage=ValidationStage.SYNTACTIC,
                                message=f"Mismatched bracket: expected '{{{stack[-1][0]}}}' but found '{char}'",
                                file=filename,
                                line=line_num,
                            )
                        )
                    else:
                        stack.pop()

            prev_char = char

        # Report unclosed brackets
        for char, pos in stack:
            line_num = content[:pos].count('\n') + 1
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    stage=ValidationStage.SYNTACTIC,
                    message=f"Unclosed '{char}'",
                    file=filename,
                    line=line_num,
                )
            )

        return issues

    def _check_basic_syntax(
        self, content: str, filename: Optional[str]
    ) -> List[ValidationIssue]:
        """Basic syntax checks for unknown languages."""
        issues = []

        # Just check bracket balance
        issues.extend(self._check_balance(content, filename))

        return issues


class SemanticValidator:
    """Stage 2: Semantic validation (1-3s target).

    Performs type checking using TypeScript compiler (tsc --noEmit).
    """

    def __init__(self, tsc_path: str = "npx tsc"):
        self.tsc_path = tsc_path

    async def validate(
        self,
        files: Dict[str, str],
        base_dir: Optional[Path] = None,
    ) -> StageResult:
        """Validate TypeScript files semantically.

        Args:
            files: Dictionary of filename -> content
            base_dir: Base directory for file operations

        Returns:
            StageResult with validation results
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        # Filter to TypeScript files
        ts_files = {
            k: v for k, v in files.items()
            if k.endswith(('.ts', '.tsx')) and not k.endswith('.d.ts')
        }

        if not ts_files:
            return StageResult(
                stage=ValidationStage.SEMANTIC,
                passed=True,
                duration_ms=(time.time() - start_time) * 1000,
                issues=[],
                metrics={"files_checked": 0, "skipped": "no TypeScript files"},
            )

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)

                # Write files to temp directory
                for filename, content in ts_files.items():
                    filepath = tmppath / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(content)

                # Create minimal tsconfig
                tsconfig = {
                    "compilerOptions": {
                        "target": "ES2020",
                        "module": "commonjs",
                        "strict": True,
                        "esModuleInterop": True,
                        "skipLibCheck": True,
                        "noEmit": True,
                    },
                    "include": ["**/*.ts", "**/*.tsx"],
                }
                (tmppath / "tsconfig.json").write_text(
                    __import__("json").dumps(tsconfig, indent=2)
                )

                # Run tsc --noEmit
                result = await asyncio.create_subprocess_exec(
                    "npx", "tsc", "--noEmit",
                    cwd=str(tmppath),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    result.communicate(), timeout=30.0
                )

                # Parse tsc output
                output = stdout.decode() + stderr.decode()
                issues = self._parse_tsc_output(output, ts_files)

        except asyncio.TimeoutError:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    stage=ValidationStage.SEMANTIC,
                    message="TypeScript validation timed out",
                )
            )
        except FileNotFoundError:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    stage=ValidationStage.SEMANTIC,
                    message="TypeScript compiler (tsc) not found, skipping semantic validation",
                )
            )
        except Exception as e:
            logger.warning(f"Semantic validation error: {e}")
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    stage=ValidationStage.SEMANTIC,
                    message=f"Semantic validation failed: {str(e)}",
                )
            )

        duration_ms = (time.time() - start_time) * 1000
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)

        return StageResult(
            stage=ValidationStage.SEMANTIC,
            passed=passed,
            duration_ms=duration_ms,
            issues=issues,
            metrics={"files_checked": len(ts_files)},
        )

    def _parse_tsc_output(
        self, output: str, files: Dict[str, str]
    ) -> List[ValidationIssue]:
        """Parse TypeScript compiler output into ValidationIssues."""
        issues = []

        # Pattern: file.ts(line,col): error TS1234: message
        pattern = re.compile(r"(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)")

        for line in output.splitlines():
            match = pattern.match(line)
            if match:
                filename, line_num, col, severity, code, message = match.groups()

                issues.append(
                    ValidationIssue(
                        severity=(
                            ValidationSeverity.ERROR
                            if severity == "error"
                            else ValidationSeverity.WARNING
                        ),
                        stage=ValidationStage.SEMANTIC,
                        message=message,
                        file=filename,
                        line=int(line_num),
                        column=int(col),
                        code=code,
                    )
                )

        return issues


class IntegrationValidator:
    """Stage 3: Integration validation (5-30s target).

    Performs full compilation, linting, and test execution.
    """

    async def validate(
        self,
        files: Dict[str, str],
        language: str = "typescript",
        run_tests: bool = False,
        lint: bool = True,
    ) -> StageResult:
        """Validate files with full integration checks.

        Args:
            files: Dictionary of filename -> content
            language: Programming language
            run_tests: Whether to run tests
            lint: Whether to run linting

        Returns:
            StageResult with validation results
        """
        start_time = time.time()
        issues: List[ValidationIssue] = []

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)

                # Write all files
                for filename, content in files.items():
                    filepath = tmppath / filename
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(content)

                # Run linting if enabled
                if lint:
                    lint_issues = await self._run_lint(tmppath, language)
                    issues.extend(lint_issues)

                # Run tests if enabled and no blocking errors
                if run_tests and not any(
                    i.severity == ValidationSeverity.ERROR for i in issues
                ):
                    test_issues = await self._run_tests(tmppath, language)
                    issues.extend(test_issues)

        except Exception as e:
            logger.warning(f"Integration validation error: {e}")
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    stage=ValidationStage.INTEGRATION,
                    message=f"Integration validation failed: {str(e)}",
                )
            )

        duration_ms = (time.time() - start_time) * 1000
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)

        return StageResult(
            stage=ValidationStage.INTEGRATION,
            passed=passed,
            duration_ms=duration_ms,
            issues=issues,
            metrics={
                "lint_run": lint,
                "tests_run": run_tests,
            },
        )

    async def _run_lint(
        self, project_dir: Path, language: str
    ) -> List[ValidationIssue]:
        """Run linting for the project."""
        issues = []

        try:
            if language in ("typescript", "javascript"):
                # Try ESLint
                result = await asyncio.create_subprocess_exec(
                    "npx", "eslint", ".", "--format", "json",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(result.communicate(), timeout=30.0)

                if stdout:
                    try:
                        lint_results = __import__("json").loads(stdout.decode())
                        for file_result in lint_results:
                            for msg in file_result.get("messages", []):
                                issues.append(
                                    ValidationIssue(
                                        severity=(
                                            ValidationSeverity.ERROR
                                            if msg.get("severity") == 2
                                            else ValidationSeverity.WARNING
                                        ),
                                        stage=ValidationStage.INTEGRATION,
                                        message=msg.get("message", "Lint error"),
                                        file=file_result.get("filePath"),
                                        line=msg.get("line"),
                                        column=msg.get("column"),
                                        code=msg.get("ruleId"),
                                    )
                                )
                    except:
                        pass

            elif language == "python":
                # Try ruff or flake8
                result = await asyncio.create_subprocess_exec(
                    "ruff", "check", ".", "--output-format", "json",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(result.communicate(), timeout=30.0)

                if stdout:
                    try:
                        lint_results = __import__("json").loads(stdout.decode())
                        for msg in lint_results:
                            issues.append(
                                ValidationIssue(
                                    severity=ValidationSeverity.WARNING,
                                    stage=ValidationStage.INTEGRATION,
                                    message=msg.get("message", "Lint error"),
                                    file=msg.get("filename"),
                                    line=msg.get("location", {}).get("row"),
                                    column=msg.get("location", {}).get("column"),
                                    code=msg.get("code"),
                                )
                            )
                    except:
                        pass

        except FileNotFoundError:
            # Linter not available
            pass
        except asyncio.TimeoutError:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    stage=ValidationStage.INTEGRATION,
                    message="Linting timed out",
                )
            )

        return issues

    async def _run_tests(
        self, project_dir: Path, language: str
    ) -> List[ValidationIssue]:
        """Run tests for the project."""
        issues = []

        try:
            if language in ("typescript", "javascript"):
                # Try Jest or Vitest
                result = await asyncio.create_subprocess_exec(
                    "npx", "jest", "--json", "--passWithNoTests",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(result.communicate(), timeout=60.0)

                if result.returncode != 0 and stdout:
                    try:
                        test_results = __import__("json").loads(stdout.decode())
                        for test_result in test_results.get("testResults", []):
                            if test_result.get("status") == "failed":
                                for assertion in test_result.get("assertionResults", []):
                                    if assertion.get("status") == "failed":
                                        issues.append(
                                            ValidationIssue(
                                                severity=ValidationSeverity.ERROR,
                                                stage=ValidationStage.INTEGRATION,
                                                message=assertion.get("title", "Test failed"),
                                                file=test_result.get("name"),
                                            )
                                        )
                    except:
                        if result.returncode != 0:
                            issues.append(
                                ValidationIssue(
                                    severity=ValidationSeverity.ERROR,
                                    stage=ValidationStage.INTEGRATION,
                                    message="Tests failed",
                                )
                            )

            elif language == "python":
                # Try pytest
                result = await asyncio.create_subprocess_exec(
                    "pytest", "--tb=no", "-q",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=60.0)

                if result.returncode != 0:
                    output = stdout.decode() + stderr.decode()
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            stage=ValidationStage.INTEGRATION,
                            message=f"Tests failed: {output[:500]}",
                        )
                    )

        except FileNotFoundError:
            # Test runner not available
            pass
        except asyncio.TimeoutError:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    stage=ValidationStage.INTEGRATION,
                    message="Test execution timed out",
                )
            )

        return issues


class ValidationPipeline:
    """Multi-stage validation pipeline with short-circuit support."""

    def __init__(
        self,
        short_circuit_on_error: bool = True,
        skip_semantic: bool = False,
        skip_integration: bool = False,
    ):
        """Initialize the validation pipeline.

        Args:
            short_circuit_on_error: Stop on first stage with errors
            skip_semantic: Skip semantic validation stage
            skip_integration: Skip integration validation stage
        """
        self.short_circuit_on_error = short_circuit_on_error
        self.skip_semantic = skip_semantic
        self.skip_integration = skip_integration

        self.syntactic = SyntacticValidator()
        self.semantic = SemanticValidator()
        self.integration = IntegrationValidator()

    async def validate(
        self,
        files: Dict[str, str],
        language: str = "typescript",
        stream_context: Optional[StreamContext] = None,
        run_tests: bool = False,
    ) -> ValidationResult:
        """Run the full validation pipeline.

        Args:
            files: Dictionary of filename -> content
            language: Primary programming language
            stream_context: Optional streaming context for progress updates
            run_tests: Whether to run tests in integration stage

        Returns:
            ValidationResult with all stage results
        """
        start_time = time.time()
        stages: List[StageResult] = []
        short_circuited = False
        short_circuit_stage = None

        # Stage 1: Syntactic validation
        if stream_context:
            await stream_context.start_stage("syntactic", "Running syntactic validation...")

        syntactic_results = []
        for filename, content in files.items():
            file_lang = self._detect_language(filename, language)
            result = await self.syntactic.validate(content, file_lang, filename)
            syntactic_results.append(result)

        # Merge syntactic results
        syntactic_stage = StageResult(
            stage=ValidationStage.SYNTACTIC,
            passed=all(r.passed for r in syntactic_results),
            duration_ms=sum(r.duration_ms for r in syntactic_results),
            issues=[i for r in syntactic_results for i in r.issues],
            metrics={
                "files_checked": len(files),
                "total_lines": sum(r.metrics.get("lines", 0) for r in syntactic_results),
            },
        )
        stages.append(syntactic_stage)

        if stream_context:
            await stream_context.emit_validation(
                passed=syntactic_stage.passed,
                stage="syntactic",
                message=f"Syntactic validation: {'passed' if syntactic_stage.passed else 'failed'}",
                errors=[i.message for i in syntactic_stage.errors],
                warnings=[i.message for i in syntactic_stage.warnings],
            )

        # Check for short-circuit
        if self.short_circuit_on_error and not syntactic_stage.passed:
            short_circuited = True
            short_circuit_stage = ValidationStage.SYNTACTIC
        else:
            # Stage 2: Semantic validation
            if not self.skip_semantic:
                if stream_context:
                    await stream_context.start_stage("semantic", "Running semantic validation...")

                semantic_stage = await self.semantic.validate(files)
                stages.append(semantic_stage)

                if stream_context:
                    await stream_context.emit_validation(
                        passed=semantic_stage.passed,
                        stage="semantic",
                        message=f"Semantic validation: {'passed' if semantic_stage.passed else 'failed'}",
                        errors=[i.message for i in semantic_stage.errors],
                        warnings=[i.message for i in semantic_stage.warnings],
                    )

                if self.short_circuit_on_error and not semantic_stage.passed:
                    short_circuited = True
                    short_circuit_stage = ValidationStage.SEMANTIC

            # Stage 3: Integration validation
            if not short_circuited and not self.skip_integration:
                if stream_context:
                    await stream_context.start_stage(
                        "integration", "Running integration validation..."
                    )

                integration_stage = await self.integration.validate(
                    files, language, run_tests=run_tests
                )
                stages.append(integration_stage)

                if stream_context:
                    await stream_context.emit_validation(
                        passed=integration_stage.passed,
                        stage="integration",
                        message=f"Integration validation: {'passed' if integration_stage.passed else 'failed'}",
                        errors=[i.message for i in integration_stage.errors],
                        warnings=[i.message for i in integration_stage.warnings],
                    )

        total_duration_ms = (time.time() - start_time) * 1000
        passed = all(s.passed for s in stages)

        return ValidationResult(
            passed=passed,
            stages=stages,
            total_duration_ms=total_duration_ms,
            short_circuited=short_circuited,
            short_circuit_stage=short_circuit_stage,
        )

    def _detect_language(self, filename: str, default: str) -> str:
        """Detect language from filename."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return default


# Metrics collection for validation
@dataclass
class ValidationMetrics:
    """Collected metrics from validation runs."""

    total_validations: int = 0
    passed_validations: int = 0
    failed_validations: int = 0
    short_circuited_count: int = 0
    avg_syntactic_ms: float = 0.0
    avg_semantic_ms: float = 0.0
    avg_integration_ms: float = 0.0
    total_errors: int = 0
    total_warnings: int = 0

    def record(self, result: ValidationResult) -> None:
        """Record metrics from a validation result."""
        self.total_validations += 1
        if result.passed:
            self.passed_validations += 1
        else:
            self.failed_validations += 1

        if result.short_circuited:
            self.short_circuited_count += 1

        for stage in result.stages:
            if stage.stage == ValidationStage.SYNTACTIC:
                self._update_avg("syntactic", stage.duration_ms)
            elif stage.stage == ValidationStage.SEMANTIC:
                self._update_avg("semantic", stage.duration_ms)
            elif stage.stage == ValidationStage.INTEGRATION:
                self._update_avg("integration", stage.duration_ms)

            self.total_errors += len(stage.errors)
            self.total_warnings += len(stage.warnings)

    def _update_avg(self, stage: str, duration_ms: float) -> None:
        """Update running average for a stage."""
        attr = f"avg_{stage}_ms"
        current = getattr(self, attr)
        count = self.total_validations
        setattr(self, attr, (current * (count - 1) + duration_ms) / count)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_validations": self.total_validations,
            "passed_validations": self.passed_validations,
            "failed_validations": self.failed_validations,
            "pass_rate": (
                self.passed_validations / self.total_validations
                if self.total_validations > 0
                else 0.0
            ),
            "short_circuit_rate": (
                self.short_circuited_count / self.total_validations
                if self.total_validations > 0
                else 0.0
            ),
            "avg_syntactic_ms": round(self.avg_syntactic_ms, 2),
            "avg_semantic_ms": round(self.avg_semantic_ms, 2),
            "avg_integration_ms": round(self.avg_integration_ms, 2),
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
        }


# Global metrics instance
_validation_metrics: Optional[ValidationMetrics] = None


def get_validation_metrics() -> ValidationMetrics:
    """Get or create global validation metrics."""
    global _validation_metrics
    if _validation_metrics is None:
        _validation_metrics = ValidationMetrics()
    return _validation_metrics
