"""CLI interface for ROMA-DSPy."""

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree

from roma_dspy.tui import run_viz

# Optional dependency for API client commands
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

app = typer.Typer(
    name="roma-dspy",
    help="ROMA-DSPy: Hierarchical task decomposition with DSPy",
    add_completion=False
)
console = Console()
console_err = Console(stderr=True)


@app.command()
def solve(
    task: str = typer.Argument(..., help="Task to solve"),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file (defaults to config/defaults/config.yaml)"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Config profile to use (e.g., high_quality, lightweight)"
    ),
    output_format: str = typer.Option(
        "text",
        "--output",
        "-o",
        help="Output format: text, json, or markdown"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output"
    ),
    max_depth: Optional[int] = typer.Option(
        None,
        "--max-depth",
        "-d",
        help="Maximum decomposition depth"
    ),
):
    """Solve a task using hierarchical decomposition.

    Examples:
        roma-dspy solve "What is the capital of France?"
        roma-dspy solve "Plan a 3-day trip to Barcelona" --verbose
        roma-dspy solve "Calculate fibonacci(10)" --output json
        roma-dspy solve "Build a web scraper" --config my_config.yaml
    """
    try:
        # Import here to avoid slow startup
        from dataclasses import replace
        from roma_dspy.config.manager import ConfigManager
        from roma_dspy.core.engine.solve import RecursiveSolver
        from roma_dspy.logging_config import configure_from_config

        # Load configuration
        config_mgr = ConfigManager()
        config = config_mgr.load_config(
            config_path=config_path,
            profile=profile
        )

        # Enhance config with profile metadata for execution tracking
        # This ensures the profile is correctly stored in the database
        profile_name = config_mgr.loaded_profile_name or profile or "default"

        # Get existing metadata or create new dict
        metadata = config.metadata if config.metadata is not None else {}
        metadata["profile_name"] = profile_name

        # Create new config instance with updated metadata (dataclasses are immutable patterns)
        config = replace(config, metadata=metadata)

        # Initialize logging from configuration
        if config.logging:
            # Override log level if verbose flag is set
            if verbose:
                config.logging.level = "DEBUG"
            configure_from_config(config.logging)

        # Override max_depth if provided
        if max_depth is not None:
            config.runtime.max_depth = max_depth

        # Override verbose if provided
        if verbose:
            config.runtime.verbose = True
            config.runtime.enable_logging = True

        if verbose:
            console.print(f"[bold blue]Task:[/bold blue] {task}")
            console.print(f"[bold blue]Max Depth:[/bold blue] {config.runtime.max_depth}")
            console.print(f"[bold blue]Config:[/bold blue] {config.project} v{config.version}")
            console.print()

        # Create solver
        solver = RecursiveSolver(config=config)

        # Async wrapper with signal handling
        async def solve_with_signal_handling():
            """Wrap solver with graceful signal handling for Ctrl+C."""
            from roma_dspy.types import ExecutionStatus
            from roma_dspy.types.checkpoint_types import CheckpointTrigger
            from loguru import logger

            # Track execution state
            current_task = None
            current_dag = None
            execution_cancelled = False

            async def cleanup_on_signal():
                """Clean up execution on SIGINT/SIGTERM."""
                nonlocal execution_cancelled
                if execution_cancelled:
                    return  # Already handling cancellation

                execution_cancelled = True
                console.print("\n[yellow]Interrupt received, cleaning up...[/yellow]")

                try:
                    # Try to save final checkpoint if checkpoint manager is available
                    if solver.checkpoint_manager and current_dag:
                        try:
                            await solver.checkpoint_manager.create_checkpoint(
                                checkpoint_id=None,
                                dag=current_dag,
                                trigger=CheckpointTrigger.ON_FAILURE,  # Signal interrupt as failure
                                current_depth=0,
                                max_depth=solver.max_depth
                            )
                            console.print("[dim]Created checkpoint for interrupted execution[/dim]")
                        except Exception as e:
                            logger.warning(f"Failed to create interrupt checkpoint: {e}")

                    # Update execution status to cancelled if postgres storage is available
                    if solver.postgres_storage and current_dag:
                        try:
                            await solver.postgres_storage.update_execution(
                                execution_id=current_dag.execution_id,
                                status=ExecutionStatus.CANCELLED.value
                            )
                            console.print(f"[dim]Execution {current_dag.execution_id[:12]}... marked as cancelled[/dim]")
                        except Exception as e:
                            logger.warning(f"Failed to update execution status: {e}")

                except Exception as e:
                    logger.error(f"Cleanup failed: {e}")
                finally:
                    console.print("[yellow]Execution interrupted by user[/yellow]")

            # Set up signal handlers
            def signal_handler(signum, frame):
                """Handle SIGINT/SIGTERM by scheduling async cleanup."""
                # Create a task to handle cleanup
                asyncio.create_task(cleanup_on_signal())
                # Raise KeyboardInterrupt to stop the event loop
                raise KeyboardInterrupt()

            # Register signal handlers
            old_sigint = signal.signal(signal.SIGINT, signal_handler)
            old_sigterm = signal.signal(signal.SIGTERM, signal_handler)

            try:
                # Start the solve operation
                result = await solver.async_solve(task, depth=0)

                # Capture DAG for cleanup if needed
                current_dag = solver.last_dag

                return result

            except KeyboardInterrupt:
                # Wait for cleanup to complete
                await cleanup_on_signal()
                raise
            finally:
                # Restore original signal handlers
                signal.signal(signal.SIGINT, old_sigint)
                signal.signal(signal.SIGTERM, old_sigterm)

        # Show progress
        with console.status("[bold green]Solving task...") as status:
            # Run async solve with signal handling
            result = asyncio.run(solve_with_signal_handling())

        # Extract actual result content from TaskNode
        result_content = result.result if hasattr(result, 'result') and result.result else str(result)

        # Format output
        if output_format == "json":
            output_data = {
                "task": task,
                "result": result_content,
                "status": result.status.value if hasattr(result, 'status') else "completed",
                "execution_id": result.execution_id if hasattr(result, 'execution_id') else None
            }
            console.print_json(json.dumps(output_data, indent=2))

        elif output_format == "markdown":
            md_output = f"""# Task Result

## Task
{task}

## Result
{result_content}

## Status
{result.status.value if hasattr(result, 'status') else 'completed'}
"""
            console.print(Syntax(md_output, "markdown", theme="monokai"))

        else:  # text
            console.print()
            console.print(Panel(
                result_content,
                title="[bold green]Result",
                border_style="green"
            ))

            if verbose and hasattr(result, 'execution_id'):
                console.print(f"\n[dim]Execution ID: {result.execution_id}[/dim]")

    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback
            console_err.print(traceback.format_exc())
        raise typer.Exit(code=1)


@app.command()
def config(
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file"
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Config profile to use"
    ),
    output_format: str = typer.Option(
        "tree",
        "--output",
        "-o",
        help="Output format: tree, json, or yaml"
    ),
):
    """Display current configuration.

    Examples:
        roma-dspy config
        roma-dspy config --profile high_quality
        roma-dspy config --output json
    """
    try:
        from roma_dspy.config.manager import ConfigManager

        # Load configuration
        config_mgr = ConfigManager()
        config = config_mgr.load_config(
            config_path=config_path,
            profile=profile
        )

        if output_format == "json":
            console.print_json(config.model_dump_json(indent=2))

        elif output_format == "yaml":
            import yaml
            yaml_str = yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False)
            console.print(Syntax(yaml_str, "yaml", theme="monokai"))

        else:  # tree
            tree = Tree(f"[bold]{config.project}[/bold] v{config.version}")

            # Runtime config
            runtime_tree = tree.add("[cyan]Runtime")
            runtime_tree.add(f"Max Depth: {config.runtime.max_depth}")
            runtime_tree.add(f"Verbose: {config.runtime.verbose}")
            runtime_tree.add(f"Cache Dir: {config.runtime.cache_dir}")

            # Agents config
            agents_tree = tree.add("[cyan]Agents")
            for agent_name, agent_cfg in [
                ("Planner", config.agents.planner),
                ("Atomizer", config.agents.atomizer),
                ("Executor", config.agents.executor),
                ("Aggregator", config.agents.aggregator),
                ("Verifier", config.agents.verifier)
            ]:
                agent_node = agents_tree.add(f"{agent_name}")
                if agent_cfg.lm_config:
                    agent_node.add(f"Model: {agent_cfg.lm_config.model}")
                    agent_node.add(f"Temperature: {agent_cfg.lm_config.temperature}")

            # Resilience config
            resilience_tree = tree.add("[cyan]Resilience")
            resilience_tree.add(f"Retry: {config.resilience.retry.enabled}")
            resilience_tree.add(f"Circuit Breaker: {config.resilience.circuit_breaker.enabled}")
            resilience_tree.add(f"Checkpoints: {config.resilience.checkpoint.enabled}")

            # Storage config
            if config.storage:
                storage_tree = tree.add("[cyan]Storage")
                storage_tree.add(f"Base Path: {config.storage.base_path}")
                if config.storage.postgres:
                    storage_tree.add(f"Postgres: {config.storage.postgres.enabled}")

            # Observability config
            if config.observability and config.observability.mlflow:
                obs_tree = tree.add("[cyan]Observability")
                obs_tree.add(f"MLflow: {config.observability.mlflow.enabled}")
                if config.observability.mlflow.enabled:
                    obs_tree.add(f"Tracking URI: {config.observability.mlflow.tracking_uri}")

            console.print(tree)

    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show ROMA-DSPy version."""
    try:
        from roma_dspy.config.manager import ConfigManager
        config_mgr = ConfigManager()
        config = config_mgr.load_config()
        console.print(f"[bold]ROMA-DSPy[/bold] v{config.version}")
    except Exception:
        console.print("[bold]ROMA-DSPy[/bold] (version unknown)")


# ============================================================================
# Server Management Commands
# ============================================================================

server_app = typer.Typer(help="Manage ROMA-DSPy API server")
app.add_typer(server_app, name="server")


@server_app.command("start")
def server_start(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind to"
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind to"
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        "-r",
        help="Enable auto-reload for development"
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        help="Number of worker processes"
    ),
):
    """Start the API server.

    Examples:
        roma-dspy server start --reload
        roma-dspy server start --workers 4 --port 8000
    """
    try:
        import uvicorn

        console.print(f"[bold green]Starting ROMA-DSPy API server on {host}:{port}[/bold green]")

        if reload and workers > 1:
            console.print("[yellow]Warning: --reload and --workers > 1 are mutually exclusive. Using reload mode.[/yellow]")
            workers = 1

        uvicorn.run(
            "roma_dspy.api.main:app",
            host=host,
            port=port,
            reload=reload,
            workers=workers,
            log_level="info",
        )
    except ImportError:
        console_err.print("[bold red]Error:[/bold red] uvicorn not installed. Install with: pip install 'roma-dspy[api]'")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error starting server:[/bold red] {e}")
        raise typer.Exit(code=1)


@server_app.command("health")
def server_health(
    url: str = typer.Option(
        "http://localhost:8000",
        "--url",
        "-u",
        help="API server URL"
    )
):
    """Check API server health.

    Examples:
        roma-dspy server health
        roma-dspy server health --url http://localhost:8000
    """
    try:

        response = httpx.get(f"{url}/health", timeout=5.0)
        response.raise_for_status()

        health_data = response.json()

        console.print(f"✅ Server is [bold green]{health_data['status']}[/bold green]")
        console.print(f"   Version: {health_data['version']}")
        console.print(f"   Uptime: {health_data['uptime_seconds']:.1f}s")
        console.print(f"   Active Executions: {health_data['active_executions']}")
        console.print(f"   Storage Connected: {health_data['storage_connected']}")
        console.print(f"   Cache Size: {health_data['cache_size']}")

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed. Install with: pip install 'roma-dspy[api]'")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] Cannot connect to server at {url}")
        console_err.print(f"   {e}")
        raise typer.Exit(code=1)


# ============================================================================
# Execution Management Commands
# ============================================================================

exec_app = typer.Typer(help="Manage task executions")
app.add_typer(exec_app, name="exec")


@exec_app.command("create")
def exec_create(
    task: str = typer.Argument(..., help="Task goal to execute"),
    max_depth: int = typer.Option(2, "--max-depth", "-d", help="Maximum decomposition depth"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Config profile"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Create a new execution via API.

    Examples:
        roma-dspy exec create "Research ML papers"
        roma-dspy exec create "Plan a trip" --max-depth 3 --profile high_quality
    """
    try:

        payload = {
            "goal": task,
            "max_depth": max_depth,
            "config_profile": profile,
        }

        with console.status(f"[bold green]Creating execution..."):
            response = httpx.post(f"{url}/api/v1/executions", json=payload, timeout=10.0)
            response.raise_for_status()

        exec_data = response.json()
        console.print(f"✅ Execution created: [bold]{exec_data['execution_id']}[/bold]")
        console.print(f"   Status: {exec_data['status']}")
        console.print(f"   Goal: {exec_data['initial_goal'][:80]}...")

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@exec_app.command("list")
def exec_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    experiment: Optional[str] = typer.Option(None, "--experiment", "-e", help="Filter by experiment name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Filter by profile"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of executions to show"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """List all executions with optional filtering.

    Examples:
        roma-dspy exec list
        roma-dspy exec list --status running
        roma-dspy exec list --experiment "ROMA-Crypto-Agent"
        roma-dspy exec list --profile crypto_agent --status completed
        roma-dspy exec list --limit 50
    """
    try:
        from rich.table import Table

        params = {"limit": limit}
        if status:
            params["status"] = status
        if experiment:
            params["experiment_name"] = experiment
        if profile:
            params["profile"] = profile

        response = httpx.get(f"{url}/api/v1/executions", params=params, timeout=10.0)
        response.raise_for_status()

        data = response.json()

        if not data["executions"]:
            console.print("[yellow]No executions found[/yellow]")
            return

        # Build title with active filters
        title_parts = [f"Executions (Total: {data['total']})"]
        if experiment:
            title_parts.append(f"Experiment: {experiment}")
        if profile:
            title_parts.append(f"Profile: {profile}")
        if status:
            title_parts.append(f"Status: {status}")
        title = " | ".join(title_parts)

        table = Table(title=title)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Experiment", style="blue", overflow="ellipsis", max_width=25)
        table.add_column("Status", style="magenta")
        table.add_column("Goal", style="white")
        table.add_column("Tasks", justify="right", style="green")
        table.add_column("Created", style="dim")

        for exec in data["executions"]:
            goal = exec["initial_goal"][:40] + "..." if len(exec["initial_goal"]) > 40 else exec["initial_goal"]
            tasks = f"{exec['completed_tasks']}/{exec['total_tasks']}"
            created = exec["created_at"][:19].replace("T", " ")
            experiment_short = exec["experiment_name"][:25] + "..." if len(exec["experiment_name"]) > 25 else exec["experiment_name"]

            table.add_row(
                exec["execution_id"][:12],
                experiment_short,
                exec["status"],
                goal,
                tasks,
                created
            )

        console.print(table)

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@exec_app.command("get")
def exec_get(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Get detailed execution information.

    Examples:
        roma-dspy exec get abc123
    """
    try:

        response = httpx.get(f"{url}/api/v1/executions/{execution_id}", timeout=10.0)
        response.raise_for_status()

        exec_data = response.json()

        console.print(Panel(
            f"""[bold]Execution ID:[/bold] {exec_data['execution_id']}
[bold]Status:[/bold] {exec_data['status']}
[bold]Goal:[/bold] {exec_data['initial_goal']}
[bold]Max Depth:[/bold] {exec_data['max_depth']}
[bold]Progress:[/bold] {exec_data['completed_tasks']}/{exec_data['total_tasks']} tasks ({exec_data['failed_tasks']} failed)
[bold]Created:[/bold] {exec_data['created_at']}
[bold]Updated:[/bold] {exec_data['updated_at']}""",
            title="[bold green]Execution Details",
            border_style="green"
        ))

        if exec_data.get("statistics"):
            stats = exec_data["statistics"]
            console.print(f"\n[bold]DAG Statistics:[/bold]")
            console.print(f"  Total Tasks: {stats['total_tasks']}")
            console.print(f"  Complete: {stats['is_complete']}")
            console.print(f"  Subgraphs: {stats['num_subgraphs']}")

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@exec_app.command("status")
def exec_status(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch status updates"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Get execution status (optimized for polling).

    Examples:
        roma-dspy exec status abc123
        roma-dspy exec status abc123 --watch
    """
    try:
        import time

        def show_status():
            response = httpx.get(f"{url}/api/v1/executions/{execution_id}/status", timeout=10.0)
            response.raise_for_status()

            status_data = response.json()

            progress_pct = status_data["progress"] * 100

            console.print(f"[bold]Status:[/bold] {status_data['status']}")
            console.print(f"[bold]Progress:[/bold] {progress_pct:.1f}% ({status_data['completed_tasks']}/{status_data['total_tasks']} tasks)")
            console.print(f"[bold]Last Updated:[/bold] {status_data['last_updated']}")

            return status_data

        if watch:
            console.print(f"[dim]Watching execution {execution_id} (Ctrl+C to stop)[/dim]\n")
            try:
                while True:
                    status_data = show_status()
                    if status_data["status"] in ["completed", "failed", "cancelled"]:
                        console.print(f"\n[bold green]Execution {status_data['status']}![/bold green]")
                        break
                    time.sleep(5)
                    console.print()  # Blank line between updates
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopped watching[/yellow]")
        else:
            show_status()

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@exec_app.command("cancel")
def exec_cancel(
    execution_id: str = typer.Argument(..., help="Execution ID to cancel"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Cancel a running execution.

    Examples:
        roma-dspy exec cancel abc123
    """
    try:

        response = httpx.post(f"{url}/api/v1/executions/{execution_id}/cancel", timeout=10.0)
        response.raise_for_status()

        exec_data = response.json()
        console.print(f"✅ Execution cancelled: [bold]{exec_data['execution_id']}[/bold]")
        console.print(f"   Status: {exec_data['status']}")

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@exec_app.command("export")
def exec_export(
    execution_id: str = typer.Argument(..., help="Execution ID to export"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output filepath (default: auto-generated)"),
    level: str = typer.Option("full", "--level", "-l", help="Export level: full, compact, or minimal"),
    exclude_io: bool = typer.Option(False, "--exclude-io", help="Exclude trace I/O data"),
    redact: bool = typer.Option(False, "--redact", "-r", help="Redact sensitive strings (API keys, tokens)"),
    compress: bool = typer.Option(True, "--compress/--no-compress", "-c", help="Auto-compress if > 10MB (default: True)"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Export execution to shareable file.

    Exports complete execution data to JSON file with optional compression,
    privacy redaction, and checksum verification.

    Export levels:
      - full: All data including trace I/O (~100%)
      - compact: No trace I/O (~20-30%)
      - minimal: Task tree + metrics only (~5%)

    Examples:
        roma-dspy exec export abc123
        roma-dspy exec export abc123 --output my_export.json
        roma-dspy exec export abc123 --level compact --redact
        roma-dspy exec export abc123 --exclude-io --no-compress
    """
    try:
        from roma_dspy.tui.core.client import ApiClient
        from roma_dspy.tui.types.export import ExportLevel
        from roma_dspy.tui.utils.export import ExportService
        from roma_dspy.tui.transformer import DataTransformer

        # Validate level
        level_map = {
            "full": ExportLevel.FULL,
            "compact": ExportLevel.COMPACT,
            "minimal": ExportLevel.MINIMAL,
        }
        if level not in level_map:
            console_err.print(f"[bold red]Error:[/bold red] Invalid level '{level}'. Use: full, compact, or minimal")
            raise typer.Exit(code=1)

        level_enum = level_map[level]

        # Generate output filepath if not provided
        if output is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = Path(f"roma_export_{execution_id[:8]}_{timestamp}.json")

        with console.status(f"[bold green]Fetching execution {execution_id}..."):
            # Fetch execution data from API
            client = ApiClient(base_url=url)

            # Fetch execution
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                exec_data = loop.run_until_complete(client.get_execution(execution_id))
            finally:
                loop.close()

            if not exec_data:
                console_err.print(f"[bold red]Error:[/bold red] Execution {execution_id} not found")
                raise typer.Exit(code=1)

            # Transform to ExecutionViewModel
            transformer = DataTransformer()
            execution = transformer.transform_execution(exec_data)

        console.print(f"✅ Fetched execution with {len(execution.tasks)} tasks")

        with console.status(f"[bold green]Exporting to {output.name}..."):
            # Export with full options
            result = ExportService.export_execution_full(
                execution=execution,
                filepath=output,
                level=level_enum,
                exclude_io=exclude_io,
                redact_sensitive=redact,
                api_url=url,
            )

        # Show result
        size_kb = result.size_bytes / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"

        console.print(f"\n✅ [bold green]Export successful![/bold green]")
        console.print(f"   File: {result.filepath}")
        console.print(f"   Level: {result.level.value}")
        console.print(f"   Size: {size_str}")
        console.print(f"   Compressed: {result.compressed}")
        console.print(f"   Tasks: {result.task_count}")
        console.print(f"   Traces: {result.trace_count}")
        if result.io_excluded:
            console.print(f"   I/O Excluded: Yes")
        if result.redacted:
            console.print(f"   Sensitive Data Redacted: Yes")
        console.print(f"   Checksum: {result.checksum[:32]}...")

        console.print(f"\n[dim]Load with: roma-dspy viz-interactive --file {result.filepath}[/dim]")

    except ImportError as e:
        console_err.print(f"[bold red]Error:[/bold red] Missing dependency: {e}")
        console_err.print("[dim]Make sure TUI dependencies are installed[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Export failed:[/bold red] {e}")
        raise typer.Exit(code=1)


# ============================================================================
# Checkpoint Management Commands
# ============================================================================

checkpoint_app = typer.Typer(help="Manage checkpoints")
app.add_typer(checkpoint_app, name="checkpoint")


@checkpoint_app.command("list")
def checkpoint_list(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of checkpoints to show"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """List checkpoints for an execution.

    Examples:
        roma-dspy checkpoint list abc123
        roma-dspy checkpoint list abc123 --limit 10
    """
    try:
        from rich.table import Table

        response = httpx.get(
            f"{url}/api/v1/executions/{execution_id}/checkpoints",
            params={"limit": limit},
            timeout=10.0
        )
        response.raise_for_status()

        data = response.json()

        if not data["checkpoints"]:
            console.print("[yellow]No checkpoints found[/yellow]")
            return

        table = Table(title=f"Checkpoints for {execution_id} (Total: {data['total']})")
        table.add_column("Checkpoint ID", style="cyan", no_wrap=True)
        table.add_column("Trigger", style="magenta")
        table.add_column("State", style="green")
        table.add_column("Created", style="dim")
        table.add_column("Size", justify="right", style="yellow")

        for cp in data["checkpoints"]:
            cp_id = cp["checkpoint_id"][:16] + "..."
            created = cp["created_at"][:19].replace("T", " ")
            size = f"{cp['file_size_bytes'] // 1024}KB" if cp.get("file_size_bytes") else "N/A"

            table.add_row(
                cp_id,
                cp["trigger"],
                cp["state"],
                created,
                size
            )

        console.print(table)

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@checkpoint_app.command("get")
def checkpoint_get(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Get checkpoint details.

    Examples:
        roma-dspy checkpoint get checkpoint_xyz
    """
    try:

        response = httpx.get(f"{url}/api/v1/checkpoints/{checkpoint_id}", timeout=10.0)
        response.raise_for_status()

        cp_data = response.json()

        console.print(Panel(
            f"""[bold]Checkpoint ID:[/bold] {cp_data['checkpoint_id']}
[bold]Execution ID:[/bold] {cp_data['execution_id']}
[bold]Trigger:[/bold] {cp_data['trigger']}
[bold]State:[/bold] {cp_data['state']}
[bold]Created:[/bold] {cp_data['created_at']}
[bold]File Path:[/bold] {cp_data['file_path'] or 'N/A'}
[bold]File Size:[/bold] {cp_data['file_size_bytes'] // 1024 if cp_data.get('file_size_bytes') else 0}KB
[bold]Compressed:[/bold] {cp_data['compressed']}""",
            title="[bold green]Checkpoint Details",
            border_style="green"
        ))

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@checkpoint_app.command("restore")
def checkpoint_restore(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID to restore"),
):
    """Restore execution from checkpoint (local operation).

    This uses RecursiveSolver directly to restore from checkpoint.

    Examples:
        roma-dspy checkpoint restore checkpoint_xyz
    """
    try:
        from roma_dspy.core.engine.solve import RecursiveSolver
        from roma_dspy.config.manager import ConfigManager

        console.print(f"[bold green]Restoring from checkpoint {checkpoint_id}...[/bold green]")

        # Load configuration
        config_mgr = ConfigManager()
        config = config_mgr.load_config()

        # Create solver
        solver = RecursiveSolver(config=config, enable_checkpoints=True)

        # Restore from checkpoint
        with console.status("[bold green]Restoring checkpoint..."):
            success = asyncio.run(solver.restore_from_unified_checkpoint(checkpoint_id))

        if success:
            console.print(f"✅ Successfully restored from checkpoint {checkpoint_id}")
            console.print("   Use 'roma-dspy solve' to continue execution")
        else:
            console_err.print(f"❌ Failed to restore from checkpoint {checkpoint_id}")
            raise typer.Exit(code=1)

    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@checkpoint_app.command("delete")
def checkpoint_delete(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID to delete"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a checkpoint.

    Examples:
        roma-dspy checkpoint delete checkpoint_xyz
        roma-dspy checkpoint delete checkpoint_xyz --yes
    """
    try:

        if not confirm:
            confirm = typer.confirm(f"Are you sure you want to delete checkpoint {checkpoint_id}?")
            if not confirm:
                console.print("[yellow]Cancelled[/yellow]")
                return

        response = httpx.delete(f"{url}/api/v1/checkpoints/{checkpoint_id}", timeout=10.0)
        response.raise_for_status()

        console.print(f"✅ Checkpoint deleted: [bold]{checkpoint_id}[/bold]")

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


# ============================================================================
# Visualization Commands
# ============================================================================

@app.command("viz-interactive")
def viz_interactive(
    execution_id: Optional[str] = typer.Argument(None, help="Execution ID to explore (omit for browser mode)"),
    api_url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
    live: bool = typer.Option(False, "--live", "-l", help="Enable live mode with automatic polling"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Polling interval in seconds (default: 2.0)"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Load from exported file instead of API"),
    experiment: Optional[str] = typer.Option(None, "--experiment", "-e", help="Filter by experiment name (browser mode only)"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Filter by profile (browser mode only)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (browser mode only)"),
):
    """
    Launch interactive TUI visualizer for executions.

    Modes:
    - Detail mode: View a specific execution (provide execution_id)
    - Browser mode: Browse all executions grouped by experiment (no execution_id)
    - File mode: Load from exported file (provide --file)

    Examples:
        # Detail mode (specific execution):
        roma-dspy viz-interactive abc123              # Static view
        roma-dspy viz-interactive abc123 --live       # Live mode (auto-refresh every 2s)

        # Browser mode (all executions):
        roma-dspy viz-interactive                     # Browse all experiments
        roma-dspy viz-interactive --experiment "ROMA-Crypto-Agent"  # Filter by experiment
        roma-dspy viz-interactive --profile crypto_agent            # Filter by profile
        roma-dspy viz-interactive --status running                  # Filter by status

        # File mode (offline):
        roma-dspy viz-interactive --file export.json           # Load from file
        roma-dspy viz-interactive --file export.json.gz        # Auto-decompresses gzipped files
    """
    try:
        # Validate mutually exclusive options
        if execution_id and file:
            console_err.print("[bold red]Error:[/bold red] Cannot specify both execution_id and --file")
            console_err.print("[dim]Use either 'roma-dspy viz-interactive EXECUTION_ID' or 'roma-dspy viz-interactive --file PATH'[/dim]")
            raise typer.Exit(code=1)

        # Validate filter usage (only in browser mode)
        if execution_id and (experiment or profile or status):
            console_err.print("[yellow]Warning:[/yellow] Filters (--experiment, --profile, --status) are ignored in detail mode")

        # Validate file mode restrictions
        if file:
            if not file.exists():
                console_err.print(f"[bold red]Error:[/bold red] File not found: {file}")
                raise typer.Exit(code=1)

            if live:
                console_err.print("[yellow]Warning:[/yellow] --live mode not available in file mode (ignored)")
                live = False

            if experiment or profile or status:
                console_err.print("[yellow]Warning:[/yellow] Filters are not available in file mode (ignored)")

            console.print(f"[dim]Loading execution from file: {file}[/dim]")

        # Browser mode message
        if not execution_id and not file:
            console.print("[dim]Launching browser mode - browse all executions grouped by experiment[/dim]")
            if experiment:
                console.print(f"[dim]Filtering by experiment: {experiment}[/dim]")
            if profile:
                console.print(f"[dim]Filtering by profile: {profile}[/dim]")
            if status:
                console.print(f"[dim]Filtering by status: {status}[/dim]")

        run_viz(
            execution_id=execution_id,
            base_url=api_url,
            live=live,
            poll_interval=poll_interval,
            file_path=file,
            experiment_filter=experiment,
            profile_filter=profile,
            status_filter=status,
        )
    except Exception as e:  # pragma: no cover - CLI runtime
        console_err.print(f"[bold red]Failed to launch TUI:[/bold red] {e}")
        raise typer.Exit(code=1)


# ============================================================================
# Metrics Commands
# ============================================================================

@app.command("metrics")
def metrics(
    execution_id: str = typer.Argument(..., help="Execution ID"),
    show_breakdown: bool = typer.Option(False, "--breakdown", "-b", help="Show task breakdown"),
    url: str = typer.Option("http://localhost:8000", "--url", "-u", help="API server URL"),
):
    """Get execution metrics and costs.

    Examples:
        roma-dspy metrics abc123
        roma-dspy metrics abc123 --breakdown
    """
    try:
        from rich.table import Table

        response = httpx.get(f"{url}/api/v1/executions/{execution_id}/metrics", timeout=10.0)
        response.raise_for_status()

        metrics_data = response.json()

        # Display summary
        console.print(Panel(
            f"""[bold]Total LM Calls:[/bold] {metrics_data['total_lm_calls']}
[bold]Total Tokens:[/bold] {metrics_data['total_tokens']:,}
[bold]Total Cost:[/bold] ${metrics_data['total_cost_usd']:.4f}
[bold]Average Latency:[/bold] {metrics_data['average_latency_ms']:.1f}ms""",
            title="[bold green]Execution Metrics",
            border_style="green"
        ))

        # Show breakdown if requested
        if show_breakdown and metrics_data.get("task_breakdown"):
            console.print("\n[bold]Task Breakdown:[/bold]")

            table = Table()
            table.add_column("Task ID", style="cyan")
            table.add_column("Module", style="magenta")
            table.add_column("Model", style="yellow")
            table.add_column("Calls", justify="right", style="green")
            table.add_column("Tokens", justify="right", style="blue")
            table.add_column("Cost", justify="right", style="red")

            for task_id, task_data in metrics_data["task_breakdown"].items():
                table.add_row(
                    task_id[:16],
                    task_data["module"],
                    task_data["model"],
                    str(task_data["calls"]),
                    f"{task_data['tokens']:,}",
                    f"${task_data['cost_usd']:.4f}"
                )

            console.print(table)

    except ImportError:
        console_err.print("[bold red]Error:[/bold red] httpx not installed")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


# ============================================================================
# Export Validation Command
# ============================================================================

@app.command("validate-export")
def validate_export(
    filepath: Path = typer.Argument(..., help="Path to exported file to validate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed validation info"),
):
    """Validate an exported execution file.

    Checks:
    - JSON schema compliance (v1.0.0)
    - Reference integrity (task IDs, trace IDs)
    - Checksum verification
    - File format detection (.json vs .json.gz)
    - Metric consistency

    Examples:
        roma-dspy validate-export export.json
        roma-dspy validate-export export.json.gz --verbose
    """
    try:
        from roma_dspy.tui.utils.import_service import ImportService

        if not filepath.exists():
            console_err.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
            raise typer.Exit(code=1)

        console.print(f"[dim]Validating: {filepath}[/dim]\n")

        # Create import service
        import_service = ImportService()

        # Validate file
        with console.status("[bold green]Validating export file..."):
            validation = import_service.validate_export_file(filepath)

        # Display results
        if validation.valid:
            console.print(f"✅ [bold green]Validation PASSED[/bold green]\n")

            # Show basic info
            console.print(f"[bold]Schema Version:[/bold] {validation.schema_version}")
            console.print(f"[bold]Execution ID:[/bold] {validation.execution_id}")

            if validation.checksum_valid:
                console.print(f"[bold]Checksum:[/bold] ✓ Valid")
            else:
                console.print(f"[bold]Checksum:[/bold] ⚠️  Mismatch (file may be corrupted)")

            # Show warnings if any
            if validation.warnings:
                console.print(f"\n[yellow]Warnings ({len(validation.warnings)}):[/yellow]")
                for warning in validation.warnings[:5]:
                    console.print(f"  ⚠️  {warning}")
                if len(validation.warnings) > 5:
                    console.print(f"  [dim]... and {len(validation.warnings) - 5} more[/dim]")

            # Verbose mode: show additional info
            if verbose:
                try:
                    import json
                    from roma_dspy.tui.utils.file_loader import FileLoader

                    data = FileLoader.load_json(filepath)

                    console.print(f"\n[bold]File Details:[/bold]")
                    console.print(f"  Format: {'Compressed (gzip)' if FileLoader.is_compressed(filepath) else 'Plain JSON'}")
                    console.print(f"  Size: {filepath.stat().st_size / 1024:.1f} KB")
                    console.print(f"  Export Level: {data.get('export_level', 'unknown')}")
                    console.print(f"  ROMA Version: {data.get('roma_version', 'unknown')}")
                    console.print(f"  Exported At: {data.get('exported_at', 'unknown')}")

                    # Show execution summary
                    exec_data = data.get('execution', {})
                    console.print(f"\n[bold]Execution Summary:[/bold]")
                    console.print(f"  Root Goal: {exec_data.get('root_goal', 'N/A')[:80]}")
                    console.print(f"  Status: {exec_data.get('status', 'unknown')}")
                    console.print(f"  Tasks: {len(exec_data.get('tasks', {}))}")

                    # Show metadata
                    metadata = data.get('metadata', {})
                    if metadata:
                        console.print(f"\n[bold]Metadata:[/bold]")
                        console.print(f"  Privacy: io_excluded={metadata.get('privacy', {}).get('io_excluded', False)}, redacted={metadata.get('privacy', {}).get('sensitive_redacted', False)}")
                        console.print(f"  Compression: {metadata.get('compression', {}).get('method', 'none')}")

                except Exception as e:
                    console.print(f"\n[yellow]Warning:[/yellow] Could not load file details: {e}")

        else:
            console.print(f"❌ [bold red]Validation FAILED[/bold red]\n")

            console.print(f"[bold red]Errors ({len(validation.errors)}):[/bold red]")
            for error in validation.errors[:10]:
                console.print(f"  ✗ {error}")
            if len(validation.errors) > 10:
                console.print(f"  [dim]... and {len(validation.errors) - 10} more[/dim]")

            if validation.warnings:
                console.print(f"\n[yellow]Warnings ({len(validation.warnings)}):[/yellow]")
                for warning in validation.warnings[:5]:
                    console.print(f"  ⚠️  {warning}")

            raise typer.Exit(code=1)

    except ImportError as e:
        console_err.print(f"[bold red]Error:[/bold red] Missing dependency: {e}")
        console_err.print("[dim]Make sure TUI dependencies are installed[/dim]")
        raise typer.Exit(code=1)
    except json.JSONDecodeError as e:
        console_err.print(f"[bold red]Error:[/bold red] Invalid JSON file")
        console_err.print(f"  {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console_err.print(f"[bold red]Validation error:[/bold red] {e}")
        if verbose:
            import traceback
            console_err.print(traceback.format_exc())
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
