"""File operations toolkit following Agno patterns."""

import json
import os
import glob
from pathlib import Path
from typing import Set

from roma_dspy.tools.base.base import BaseToolkit


class FileToolkit(BaseToolkit):
    """
    File operations toolkit providing file system access to agents.

    Based on Agno FileTools implementation with DSPy integration.
    Provides safe file operations within execution-scoped directories.
    """

    # FileToolkit requires FileStorage for execution isolation
    REQUIRES_FILE_STORAGE: bool = True

    def _setup_dependencies(self) -> None:
        """Setup file toolkit dependencies."""
        # No external dependencies required for basic file operations
        pass

    def _initialize_tools(self) -> None:
        """Initialize file toolkit configuration with strict security validation."""
        # FileStorage is REQUIRED - no fallback
        if not self._file_storage:
            raise ValueError(
                "FileToolkit requires FileStorage to be provided. "
                "FileStorage ensures execution-scoped isolation of file operations."
            )

        # Use the execution-scoped directory from FileStorage
        base_path = self._file_storage.root
        self.log_debug(f"Using execution-scoped directory: {base_path}")

        # Ensure the execution directory exists
        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)
            self.log_debug(f"Created execution directory: {base_path}")

        self.base_directory = str(base_path)
        self.enable_delete = self.config.get('enable_delete', True)
        self.max_file_size = self.config.get('max_file_size', 10 * 1024 * 1024)  # 10MB default

    def _is_tool_available(self, tool_name: str) -> bool:
        """Check if a tool should be available based on configuration."""
        # delete_file is only available if enable_delete is True
        if tool_name == "delete_file" and not self.enable_delete:
            return False
        return True

    def _get_full_path(self, file_path: str) -> Path:
        """Get full path with security validation (supports both relative and absolute paths).

        Accepts:
        - Relative paths: resolved relative to base_directory
        - Absolute paths: validated to be within base_directory

        Security checks:
        - Path traversal prevention (..)
        - Null byte detection
        - Base directory containment validation
        """
        # Additional security checks on the input path
        if not file_path or not file_path.strip():
            raise ValueError("File path cannot be empty")

        # Check for null bytes (security issue)
        if '\x00' in file_path:
            raise ValueError(f"File path contains null byte: '{file_path}'")

        # Check for path traversal attempts
        if '..' in file_path:
            raise ValueError(f"Invalid file path (path traversal detected): '{file_path}'")

        # Resolve base directory once
        base_resolved = Path(self.base_directory).resolve()

        # Handle absolute vs relative paths
        path_obj = Path(file_path)
        if path_obj.is_absolute():
            # Absolute path: validate it's within base directory
            resolved_path = path_obj.resolve()
            try:
                resolved_path.relative_to(base_resolved)
            except ValueError:
                raise ValueError(
                    f"Access denied: '{file_path}' is outside execution scope. "
                    f"Use relative paths or paths within: {base_resolved}"
                )
            # Return the resolved absolute path
            return resolved_path
        else:
            # Relative path: resolve relative to base directory
            full_path = Path(self.base_directory) / file_path
            resolved_path = full_path.resolve()

            # Ensure the resolved path is within base directory (security check)
            try:
                resolved_path.relative_to(base_resolved)
            except ValueError:
                raise ValueError(
                    f"Access denied: '{file_path}' resolves outside execution scope. "
                    f"Allowed directory: {base_resolved}"
                )

            return full_path

    def save_file(self, file_path: str, content: str, overwrite: bool = False) -> str:
        """
        Save content to a file with optional overwrite protection.

        Use this tool to write text content to files. The file will be created relative
        to the configured base directory. By default, existing files are protected from
        accidental overwrite unless explicitly allowed.

        Args:
            file_path: Path to the file to save (relative to base directory)
            content: Text content to write to the file
            overwrite: Whether to overwrite existing file (default: False for safety)

        Returns:
            JSON string with success status and absolute file path

        Examples:
            save_file('report.txt', 'Analysis results...') - Save new file
            save_file('data.json', json_data, overwrite=True) - Overwrite existing file
        """
        try:
            full_path = self._get_full_path(file_path)

            # Check if file exists and overwrite is False
            if full_path.exists() and not overwrite:
                error_msg = f"File '{file_path}' already exists and overwrite=False"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Check content size
            if len(content.encode('utf-8')) > self.max_file_size:
                error_msg = f"Content size exceeds maximum allowed size ({self.max_file_size} bytes)"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Create parent directory if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            full_path.write_text(content, encoding='utf-8')

            success_msg = f"Successfully saved {len(content)} characters to '{file_path}'"
            self.log_debug(success_msg)
            return json.dumps({"success": True, "message": success_msg, "file_path": str(full_path)})

        except Exception as e:
            error_msg = f"Error saving file '{file_path}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def read_file(self, file_path: str) -> str:
        """
        Read content from a file with UTF-8 encoding.

        Use this tool to read text content from files. The file path is relative
        to the configured base directory. Returns the full file content as a string
        within a JSON response structure.

        Args:
            file_path: Path to the file to read (relative to base directory)

        Returns:
            JSON string containing file content, absolute file path, and metadata

        Examples:
            read_file('config.yaml') - Read configuration file
            read_file('data/results.json') - Read file from subdirectory
        """
        try:
            full_path = self._get_full_path(file_path)

            if not full_path.exists():
                error_msg = f"File '{file_path}' does not exist"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            if not full_path.is_file():
                error_msg = f"'{file_path}' is not a file"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Check file size
            if full_path.stat().st_size > self.max_file_size:
                error_msg = f"File '{file_path}' is too large (max: {self.max_file_size} bytes)"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            content = full_path.read_text(encoding='utf-8')

            self.log_debug(f"Successfully read {len(content)} characters from '{file_path}'")
            return json.dumps({
                "success": True,
                "content": content,
                "file_path": str(full_path),
                "size": len(content)
            })

        except Exception as e:
            error_msg = f"Error reading file '{file_path}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def list_files(self, directory: str = ".") -> str:
        """
        List files and directories in the specified directory.

        Use this tool to explore directory contents and understand file structure.
        Returns detailed information about each item including name, type, and size.
        Results are sorted with directories first, then files, alphabetically.

        Args:
            directory: Directory to list (relative to base directory, default: current directory)

        Returns:
            JSON string with list of files and directories with absolute paths and metadata

        Examples:
            list_files() - List files in current directory
            list_files('data') - List files in data subdirectory
        """
        try:
            full_path = self._get_full_path(directory)

            if not full_path.exists():
                error_msg = f"Directory '{directory}' does not exist"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            if not full_path.is_dir():
                error_msg = f"'{directory}' is not a directory"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            items = []
            for item in full_path.iterdir():
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None
                })

            # Sort by type (directories first) then by name
            items.sort(key=lambda x: (x["type"] != "directory", x["name"]))

            self.log_debug(f"Listed {len(items)} items in directory '{directory}'")
            return json.dumps({
                "success": True,
                "directory": directory,
                "items": items,
                "count": len(items)
            })

        except Exception as e:
            error_msg = f"Error listing directory '{directory}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def search_files(self, pattern: str, directory: str = ".") -> str:
        """
        Find files matching a glob pattern within the specified directory.

        Use this tool to locate files based on patterns. Supports standard glob patterns
        including wildcards (*), single character matches (?), and recursive searches (**).
        Only returns actual files, not directories.

        Args:
            pattern: Glob pattern to match (e.g., '*.txt', '**/*.py', 'data_*.json')
            directory: Directory to search within (relative to base directory, default: current)

        Returns:
            JSON string with list of matching files with absolute paths and details

        Examples:
            search_files('*.txt') - Find all .txt files in current directory
            search_files('**/*.py', 'src') - Recursively find all .py files in src directory
            search_files('report_*.pdf') - Find all PDF files starting with 'report_'
        """
        try:
            search_path = self._get_full_path(directory)

            if not search_path.exists() or not search_path.is_dir():
                error_msg = f"Directory '{directory}' does not exist or is not a directory"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            # Use glob to find matching files
            full_pattern = str(search_path / pattern)
            matching_files = glob.glob(full_pattern, recursive=True)

            # Convert to absolute paths and filter only files
            results = []
            for file_path in matching_files:
                path = Path(file_path)
                if path.is_file():
                    results.append({
                        "name": path.name,
                        "path": str(path),
                        "size": path.stat().st_size
                    })

            # Sort by name
            results.sort(key=lambda x: x["name"])

            self.log_debug(f"Found {len(results)} files matching pattern '{pattern}' in '{directory}'")
            return json.dumps({
                "success": True,
                "pattern": pattern,
                "directory": directory,
                "matches": results,
                "count": len(results)
            })

        except Exception as e:
            error_msg = f"Error searching files with pattern '{pattern}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def create_directory(self, directory_path: str) -> str:
        """
        Create a directory and any necessary parent directories.

        Use this tool to create directory structures for organizing files.
        Will create all parent directories in the path if they don't exist.
        Safe to call on existing directories (won't raise an error).

        Args:
            directory_path: Path of directory to create (relative to base directory)

        Returns:
            JSON string with success status and absolute directory path

        Examples:
            create_directory('logs') - Create a logs directory
            create_directory('data/exports/csv') - Create nested directory structure
        """
        try:
            full_path = self._get_full_path(directory_path)

            full_path.mkdir(parents=True, exist_ok=True)

            success_msg = f"Successfully created directory '{directory_path}'"
            self.log_debug(success_msg)
            return json.dumps({
                "success": True,
                "message": success_msg,
                "directory_path": str(full_path)
            })

        except Exception as e:
            error_msg = f"Error creating directory '{directory_path}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})

    def delete_file(self, file_path: str) -> str:
        """
        Delete a file permanently from the file system.

        Use this tool with caution as it permanently removes files. Only available
        if enable_delete is True in the toolkit configuration. Will not delete
        directories - only regular files.

        Args:
            file_path: Path to the file to delete (relative to base directory)

        Returns:
            JSON string with success status and absolute file path

        Examples:
            delete_file('temp.txt') - Delete a temporary file
            delete_file('old_logs/error.log') - Delete file in subdirectory

        Note:
            This operation is irreversible. Ensure the file is no longer needed.
        """
        try:
            full_path = self._get_full_path(file_path)

            if not full_path.exists():
                error_msg = f"File '{file_path}' does not exist"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            if not full_path.is_file():
                error_msg = f"'{file_path}' is not a file"
                self.log_error(error_msg)
                return json.dumps({"success": False, "error": error_msg})

            full_path.unlink()

            success_msg = f"Successfully deleted file '{file_path}'"
            self.log_debug(success_msg)
            return json.dumps({
                "success": True,
                "message": success_msg,
                "file_path": str(full_path)
            })

        except Exception as e:
            error_msg = f"Error deleting file '{file_path}': {str(e)}"
            self.log_error(error_msg)
            return json.dumps({"success": False, "error": error_msg})