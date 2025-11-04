"""E2B code execution toolkit for secure sandboxed code execution."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from roma_dspy.tools.base.base import BaseToolkit


class E2BToolkit(BaseToolkit):
    """
    E2B code execution toolkit providing secure sandboxed code execution.

    Based on Agno E2BTools implementation with DSPy integration and intelligent
    sandbox lifecycle management. Uses E2B AsyncSandbox for native async support,
    preventing event loop blocking during concurrent agent execution.

    Key features:
    - Native async/await support via E2B AsyncSandbox
    - Automatic health checks before every operation
    - Transparent sandbox reinitialization on timeout
    - 24-hour hard limit handling with preemptive restart
    - Async-safe operation with asyncio.Lock for parallel agent execution
    - Comprehensive code execution and file management
    - Zero event loop blocking during sandbox operations

    Configuration:
        api_key: E2B API key (or set E2B_API_KEY environment variable)
        timeout: Sandbox timeout in seconds (default: 300 = 5 min)
        max_lifetime_hours: Max sandbox lifetime before restart (default: 23.5)
        template: E2B template to use (default: "base")
        auto_reinitialize: Auto-recreate sandbox on death (default: True)

    Note:
        All tool methods are async and must be awaited. Use async context manager
        (async with) for proper resource cleanup, or call aclose() explicitly.
    """

    def _setup_dependencies(self) -> None:
        """Setup E2B toolkit dependencies."""
        try:
            from e2b_code_interpreter import AsyncSandbox
            self._Sandbox = AsyncSandbox
        except ImportError:
            raise ImportError(
                "e2b-code-interpreter library is required for E2BToolkit. "
                "Install it with: pip install -e \".[e2b]\""
            )

        # Get API key from config or environment
        self.api_key = self.config.get('api_key') or os.getenv('E2B_API_KEY')
        if not self.api_key:
            raise ValueError(
                "E2B_API_KEY is required. Set it as environment variable or "
                "pass 'api_key' in toolkit_config."
            )

    def _initialize_tools(self) -> None:
        """Initialize E2B toolkit configuration."""
        # Configuration with defaults
        self.timeout = self.config.get('timeout', 300)  # 5 minutes in seconds
        self.max_lifetime_hours = self.config.get('max_lifetime_hours', 23.5)  # Before 24h limit

        # Template: use config, then E2B_TEMPLATE_ID env var, then default custom template
        self.template = (
            self.config.get('template') or
            os.getenv('E2B_TEMPLATE_ID') or
            'roma-dspy-sandbox'
        )

        self.auto_reinitialize = self.config.get('auto_reinitialize', True)

        # Validate configuration
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")
        if self.max_lifetime_hours > 24:
            raise ValueError(
                f"max_lifetime_hours cannot exceed 24h E2B limit, got {self.max_lifetime_hours}"
            )
        if self.max_lifetime_hours < (self.timeout / 3600):
            raise ValueError(
                f"max_lifetime_hours ({self.max_lifetime_hours}h) must be >= timeout "
                f"({self.timeout}s = {self.timeout/3600:.2f}h)"
            )

        # State tracking
        self._sandbox: Optional[object] = None  # Actual type: AsyncSandbox
        self._sandbox_id: Optional[str] = None
        self._created_at: float = 0
        self._lock = asyncio.Lock()  # Async-safe lock for concurrent operations

        self.log_debug(f"E2B toolkit initialized with timeout={self.timeout}s")

    async def _ensure_sandbox_alive(self) -> object:
        """
        Ensure sandbox is alive and healthy, reinitialize if needed.

        This method is async-safe and performs minimal locking. The health check
        and sandbox creation are locked, but execution happens outside the lock
        to allow parallel operations.

        Returns:
            Active AsyncSandbox instance

        Raises:
            RuntimeError: If sandbox creation fails and auto_reinitialize is False
        """
        async with self._lock:  # Critical section: check + create only
            # No sandbox yet
            if self._sandbox is None:
                return await self._create_sandbox()

            # Check if sandbox is still running
            try:
                if not await self._sandbox.is_running():
                    self.log_warning("Sandbox died, reinitializing...")
                    if self.auto_reinitialize:
                        return await self._create_sandbox()
                    else:
                        raise RuntimeError("Sandbox died and auto_reinitialize is disabled")

                # Check if approaching 24h hard limit
                elapsed = time.time() - self._created_at
                if elapsed > (self.max_lifetime_hours * 3600):
                    self.log_warning(
                        f"Sandbox approaching 24h limit ({elapsed/3600:.1f}h), "
                        "performing preemptive restart..."
                    )
                    return await self._create_sandbox()

                # Sandbox is healthy, return reference
                sandbox = self._sandbox

            except Exception as e:
                self.log_error(f"Sandbox health check failed: {e}")
                if self.auto_reinitialize:
                    return await self._create_sandbox()
                else:
                    raise RuntimeError(f"Sandbox health check failed: {e}")

        return sandbox  # Return outside lock

    async def _create_sandbox(self) -> object:
        """
        Create a new sandbox instance with environment variables for storage.

        This method should only be called while holding self._lock.

        Returns:
            New AsyncSandbox instance

        Raises:
            ValueError: If required environment variables are missing
        """
        # Cleanup old sandbox if exists
        if self._sandbox is not None:
            try:
                await self._sandbox.kill()
                self.log_debug(f"Killed old sandbox {self._sandbox_id}")
            except Exception as e:
                self.log_warning(f"Error killing old sandbox: {e}")

        # Prepare environment variables for E2B sandbox
        env_vars = {
            "STORAGE_BASE_PATH": os.getenv("STORAGE_BASE_PATH", "/opt/sentient"),
            "ROMA_S3_BUCKET": os.getenv("ROMA_S3_BUCKET"),
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        }

        # Validate required environment variables
        if not env_vars["ROMA_S3_BUCKET"]:
            raise ValueError(
                "ROMA_S3_BUCKET environment variable is required for E2B storage integration. "
                "Set it in .env file or environment."
            )
        if not env_vars["AWS_ACCESS_KEY_ID"] or not env_vars["AWS_SECRET_ACCESS_KEY"]:
            raise ValueError(
                "AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) are required "
                "for E2B S3 mounting. Set them in .env file or environment."
            )

        # Create new sandbox with environment variables (async)
        try:
            self._sandbox = await self._Sandbox.create(
                timeout=self.timeout,
                template=self.template,
                api_key=self.api_key,
                envs=env_vars  # E2B SDK expects 'envs', not 'env_vars'
            )
            self._sandbox_id = self._sandbox.sandbox_id
            self._created_at = time.time()

            self.log_debug(
                f"Created new sandbox {self._sandbox_id} with "
                f"timeout={self.timeout}s, storage={env_vars['STORAGE_BASE_PATH']}, "
                f"bucket={env_vars['ROMA_S3_BUCKET']}"
            )

            return self._sandbox

        except Exception as e:
            self.log_error(f"Failed to create sandbox: {e}")
            raise

    async def aclose(self) -> None:
        """
        Async close and cleanup sandbox resources.

        Use this method or async context manager to ensure proper cleanup.
        """
        if not hasattr(self, '_lock'):
            return  # Not fully initialized

        async with self._lock:
            if self._sandbox is not None:
                try:
                    await self._sandbox.kill()
                    self.log_debug(f"Closed sandbox {self._sandbox_id}")
                except Exception as e:
                    self.log_warning(f"Error closing sandbox: {e}")
                finally:
                    self._sandbox = None
                    self._sandbox_id = None

    def close(self) -> None:
        """
        Sync wrapper for close. Prefer using aclose() in async contexts.

        Use this method or context manager to ensure proper cleanup.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule close for later
                asyncio.create_task(self.aclose())
            else:
                # If no loop running, run aclose() synchronously
                loop.run_until_complete(self.aclose())
        except RuntimeError:
            # No event loop exists, create one
            asyncio.run(self.aclose())

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()
        return False

    def __enter__(self):
        """Sync context manager entry (for backward compatibility)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit (for backward compatibility)."""
        self.close()
        return False

    def __del__(self):
        """Cleanup sandbox on destruction."""
        self.close()

    # ========== Tool Methods ==========

    async def run_python_code(self, code: str) -> str:
        """
        Execute Python code in the E2B sandbox.

        Use this tool to run Python code in a secure isolated environment.
        The sandbox persists across calls, allowing you to build up state.
        Automatically handles sandbox timeouts and reinitializes when needed.

        Args:
            code: Python code to execute

        Returns:
            JSON string with execution results, stdout, stderr, and any errors

        Examples:
            run_python_code("x = 5 + 3\\nprint(x)") - Basic calculation
            run_python_code("import pandas as pd\\ndf = pd.DataFrame({'a': [1,2,3]})") - Use libraries
            run_python_code("print('Hello from sandbox!')") - Print output
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            execution = await sandbox.run_code(code)

            # Format results
            results = []
            if hasattr(execution, 'results') and execution.results:
                for result in execution.results:
                    if hasattr(result, 'text'):
                        results.append(result.text)
                    elif hasattr(result, 'png'):
                        results.append("[PNG image output]")
                    elif hasattr(result, 'html'):
                        results.append("[HTML output]")
                    else:
                        results.append(str(result))

            # Handle error field - convert to string for JSON serialization
            error_value = None
            if hasattr(execution, 'error') and execution.error:
                error_value = str(execution.error)

            response = {
                "success": True,
                "results": results,
                "stdout": execution.logs.stdout if hasattr(execution, 'logs') else [],
                "stderr": execution.logs.stderr if hasattr(execution, 'logs') else [],
                "error": error_value,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Code executed successfully in sandbox {self._sandbox_id}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Code execution failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def run_command(self, command: str, timeout_seconds: int = 60) -> str:
        """
        Execute a shell command in the E2B sandbox.

        Use this tool to run shell commands like installing packages, running scripts,
        or performing system operations in the isolated sandbox environment.

        Args:
            command: Shell command to execute
            timeout_seconds: Command timeout in seconds (default: 60)

        Returns:
            JSON string with command exit code, stdout, and stderr

        Examples:
            run_command("pip install numpy") - Install Python package
            run_command("ls -la /home") - List directory contents
            run_command("echo 'Hello World'") - Simple shell command
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # E2B SDK uses commands.run() for executing shell commands
            result = await sandbox.commands.run(command, timeout=timeout_seconds)

            response = {
                "success": True,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Command executed: {command} (exit={result.exit_code})")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def get_sandbox_status(self) -> str:
        """
        Get current sandbox status and information.

        Use this tool to check sandbox health, uptime, and configuration.
        Useful for debugging and monitoring long-running agent sessions.

        Returns:
            JSON string with sandbox status, ID, uptime, and configuration

        Examples:
            get_sandbox_status() - Check current sandbox state
        """
        async with self._lock:
            if self._sandbox is None:
                return json.dumps({
                    "success": True,
                    "status": "no_sandbox",
                    "message": "No sandbox created yet"
                })

            try:
                is_running = await self._sandbox.is_running()
                uptime = time.time() - self._created_at

                response = {
                    "success": True,
                    "status": "running" if is_running else "stopped",
                    "sandbox_id": self._sandbox_id,
                    "uptime_seconds": round(uptime, 1),
                    "uptime_hours": round(uptime / 3600, 2),
                    "timeout": self.timeout,
                    "max_lifetime_hours": self.max_lifetime_hours,
                    "template": self.template
                }

                return json.dumps(response)

            except Exception as e:
                error_msg = f"Failed to get sandbox status: {str(e)}"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

    async def restart_sandbox(self) -> str:
        """
        Manually restart the sandbox.

        Use this tool to force a fresh sandbox environment, clearing all state.
        Useful when you need to reset the execution environment.

        Returns:
            JSON string with new sandbox information

        Examples:
            restart_sandbox() - Force sandbox restart
        """
        async with self._lock:
            try:
                old_id = self._sandbox_id
                await self._create_sandbox()

                response = {
                    "success": True,
                    "message": "Sandbox restarted",
                    "old_sandbox_id": old_id,
                    "new_sandbox_id": self._sandbox_id
                }

                self.log_debug(f"Sandbox manually restarted: {old_id} -> {self._sandbox_id}")
                return json.dumps(response)

            except Exception as e:
                error_msg = f"Failed to restart sandbox: {str(e)}"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

    async def upload_file(self, local_path: str, remote_path: str) -> str:
        """
        Upload a file from local filesystem to the sandbox.

        Use this tool to transfer files into the sandbox for processing.
        The file will be uploaded to the specified path in the sandbox.

        Args:
            local_path: Path to local file to upload
            remote_path: Destination path in sandbox (e.g., "/home/user/data.csv")

        Returns:
            JSON string with upload status

        Examples:
            upload_file("/tmp/data.csv", "/home/user/data.csv") - Upload CSV file
            upload_file("./script.py", "/home/user/script.py") - Upload Python script
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # Validate local file exists
            local_file = Path(local_path)
            if not local_file.exists():
                error_msg = f"Local file does not exist: {local_path}"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Read and upload file
            with open(local_file, 'rb') as f:
                content = f.read()

            await sandbox.files.write(remote_path, content)

            response = {
                "success": True,
                "message": f"Uploaded {len(content)} bytes",
                "local_path": local_path,
                "remote_path": remote_path,
                "size_bytes": len(content),
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Uploaded file: {local_path} -> {remote_path}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"File upload failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def download_file(self, remote_path: str, local_path: str) -> str:
        """
        Download a file from sandbox to local filesystem.

        Use this tool to retrieve files generated in the sandbox for further processing
        or to save results from sandbox operations.

        Args:
            remote_path: Path to file in sandbox (e.g., "/home/user/output.txt")
            local_path: Destination path on local filesystem

        Returns:
            JSON string with download status

        Examples:
            download_file("/home/user/result.csv", "/tmp/result.csv") - Download results
            download_file("/home/user/plot.png", "./output.png") - Download generated image
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # Read file from sandbox
            content = await sandbox.files.read(remote_path)

            # Ensure content is bytes
            if isinstance(content, str):
                content = content.encode('utf-8')

            # Write to local filesystem
            local_file = Path(local_path)
            local_file.parent.mkdir(parents=True, exist_ok=True)

            with open(local_file, 'wb') as f:
                f.write(content)

            response = {
                "success": True,
                "message": f"Downloaded {len(content)} bytes",
                "remote_path": remote_path,
                "local_path": local_path,
                "size_bytes": len(content),
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Downloaded file: {remote_path} -> {local_path}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"File download failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def list_files(self, directory: str = "/home/user") -> str:
        """
        List files and directories in the sandbox.

        Use this tool to explore the sandbox filesystem and understand what
        files are available for processing.

        Args:
            directory: Directory to list (default: "/home/user")

        Returns:
            JSON string with list of files and directories

        Examples:
            list_files() - List files in home directory
            list_files("/tmp") - List files in /tmp directory
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # List directory using shell command
            result = await sandbox.commands.run(f"ls -la {directory}")

            if result.exit_code != 0:
                error_msg = f"Failed to list directory: {result.stderr}"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            response = {
                "success": True,
                "directory": directory,
                "output": result.stdout,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Listed directory: {directory}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"List files failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def read_file_content(self, path: str) -> str:
        """
        Read the content of a file in the sandbox.

        Use this tool to read text files, scripts, or data files stored in the sandbox.

        Args:
            path: Path to file in sandbox

        Returns:
            JSON string with file content

        Examples:
            read_file_content("/home/user/output.txt") - Read text file
            read_file_content("/home/user/data.json") - Read JSON file
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            content = await sandbox.files.read(path)

            # Handle both str and bytes returns from E2B SDK
            if isinstance(content, bytes):
                # Try to decode as text
                try:
                    text_content = content.decode('utf-8')
                    is_text = True
                except UnicodeDecodeError:
                    text_content = None
                    is_text = False
                size_bytes = len(content)
            elif isinstance(content, str):
                # Already a string
                text_content = content
                is_text = True
                size_bytes = len(content.encode('utf-8'))
            else:
                # Unknown type, convert to string
                text_content = str(content)
                is_text = True
                size_bytes = len(str(content).encode('utf-8'))

            response = {
                "success": True,
                "path": path,
                "content": text_content if is_text else "[Binary file]",
                "size_bytes": size_bytes,
                "is_text": is_text,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Read file: {path} ({size_bytes} bytes)")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Read file failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def write_file_content(self, path: str, content: str) -> str:
        """
        Write content to a file in the sandbox.

        Use this tool to create or update files in the sandbox environment.

        Args:
            path: Path where to write the file in sandbox
            content: Text content to write

        Returns:
            JSON string with write status

        Examples:
            write_file_content("/home/user/config.yaml", "key: value") - Write config
            write_file_content("/home/user/script.py", "print('Hello')") - Write script
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # Convert string to bytes
            content_bytes = content.encode('utf-8')

            # Write to sandbox
            await sandbox.files.write(path, content_bytes)

            response = {
                "success": True,
                "message": f"Wrote {len(content_bytes)} bytes",
                "path": path,
                "size_bytes": len(content_bytes),
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Wrote file: {path} ({len(content_bytes)} bytes)")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Write file failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def create_directory(self, path: str) -> str:
        """
        Create a directory in the sandbox.

        Use this tool to create directory structures for organizing files in the sandbox.

        Args:
            path: Directory path to create in sandbox

        Returns:
            JSON string with creation status

        Examples:
            create_directory("/home/user/data") - Create data directory
            create_directory("/home/user/output/results") - Create nested directories
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # Create directory using shell command
            result = await sandbox.commands.run(f"mkdir -p {path}")

            if result.exit_code != 0:
                error_msg = f"Failed to create directory: {result.stderr}"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            response = {
                "success": True,
                "message": f"Created directory: {path}",
                "path": path,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Created directory: {path}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Create directory failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def install_package(self, package: str) -> str:
        """
        Install a Python package in the sandbox using pip.

        Use this tool to add Python libraries needed for your code execution.
        The package will be installed in the sandbox environment.

        Args:
            package: Package name to install (e.g., "numpy", "pandas==2.0.0")

        Returns:
            JSON string with installation status

        Examples:
            install_package("numpy") - Install latest numpy
            install_package("pandas==2.0.0") - Install specific version
            install_package("scikit-learn") - Install scikit-learn
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # Install package using pip
            result = await sandbox.commands.run(f"pip install {package}", timeout=120)  # 2 minutes timeout

            response = {
                "success": result.exit_code == 0,
                "package": package,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "sandbox_id": self._sandbox_id
            }

            if result.exit_code == 0:
                self.log_debug(f"Installed package: {package}")
            else:
                self.log_error(f"Failed to install package {package}: {result.stderr}")

            return json.dumps(response)

        except Exception as e:
            error_msg = f"Package installation failed: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    async def get_sandbox_url(self, port: int = 8000) -> str:
        """
        Get the URL to access a web application running in the sandbox.

        Use this tool when running web servers in the sandbox to get the public URL
        for accessing the application.

        Args:
            port: Port number where the application is running (default: 8000)

        Returns:
            JSON string with sandbox URL

        Examples:
            get_sandbox_url(8000) - Get URL for app on port 8000
            get_sandbox_url(5000) - Get URL for Flask app on port 5000
        """
        sandbox = await self._ensure_sandbox_alive()

        try:
            # E2B provides URL through sandbox object (get_host is sync)
            url = sandbox.get_host(port)

            response = {
                "success": True,
                "url": url,
                "port": port,
                "sandbox_id": self._sandbox_id
            }

            self.log_debug(f"Retrieved sandbox URL for port {port}: {url}")
            return json.dumps(response)

        except Exception as e:
            error_msg = f"Failed to get sandbox URL: {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})