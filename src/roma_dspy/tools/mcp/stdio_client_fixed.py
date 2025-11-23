"""Fixed stdio client for MCP that works around anyio TextReceiveStream issues.

The standard MCP stdio_client has a bug where TextReceiveStream completes immediately
when there's no data, causing BrokenResourceError. This version ensures we properly
wait for data by using raw byte streams and manual buffering.
"""

import sys
from contextlib import asynccontextmanager
from io import TextIOWrapper
from typing import TextIO

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.client.stdio import (
    StdioServerParameters,
    _create_platform_compatible_process,
    _get_executable_command,
    _terminate_process_tree,
    get_default_environment,
)
from mcp.shared.message import SessionMessage

import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def stdio_client_fixed(
    server: StdioServerParameters, errlog: TextIO = sys.stderr
):
    """
    Fixed stdio client that properly handles subprocess communication.

    This version ensures stdout reading doesn't complete prematurely by:
    1. Using raw byte streams instead of TextReceiveStream
    2. Manually buffering and decoding
    3. Properly blocking on read operations
    """
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]

    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    try:
        command = _get_executable_command(server.command)

        # Open process with stderr piped for capture
        process = await _create_platform_compatible_process(
            command=command,
            args=server.args,
            env=(
                {**get_default_environment(), **server.env}
                if server.env is not None
                else get_default_environment()
            ),
            errlog=errlog,
            cwd=server.cwd,
        )
    except OSError:
        # Clean up streams if process creation fails
        await read_stream.aclose()
        await write_stream.aclose()
        await read_stream_writer.aclose()
        await write_stream_reader.aclose()
        raise

    async def stdout_reader():
        """Read from subprocess stdout and parse JSON-RPC messages.

        This version uses raw byte streams to avoid TextReceiveStream issues.
        """
        assert process.stdout, "Opened process is missing stdout"

        try:
            async with read_stream_writer:
                buffer = b""

                # Read raw bytes from stdout
                while True:
                    try:
                        # Read chunks of data - this will block until data is available
                        chunk = await process.stdout.receive(4096)

                        if not chunk:  # EOF
                            break

                        buffer += chunk

                        # Try to decode and split into lines
                        try:
                            text = buffer.decode(
                                server.encoding, errors=server.encoding_error_handler
                            )
                            lines = text.split("\n")

                            # Keep last incomplete line in buffer
                            if not text.endswith("\n"):
                                incomplete_line = lines.pop()
                                buffer = incomplete_line.encode(server.encoding)
                            else:
                                buffer = b""

                            # Process complete lines
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue

                                try:
                                    message = types.JSONRPCMessage.model_validate_json(
                                        line
                                    )
                                    session_message = SessionMessage(message)
                                    await read_stream_writer.send(session_message)
                                except Exception as exc:
                                    logger.exception(
                                        "Failed to parse JSONRPC message from server"
                                    )
                                    await read_stream_writer.send(exc)

                        except UnicodeDecodeError:
                            # Keep buffering until we have a complete UTF-8 sequence
                            pass

                    except anyio.ClosedResourceError:
                        break

        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def stdin_writer():
        """Write JSON-RPC messages to subprocess stdin."""
        assert process.stdin, "Opened process is missing stdin"

        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    json = session_message.message.model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                    await process.stdin.send(
                        (json + "\n").encode(
                            encoding=server.encoding,
                            errors=server.encoding_error_handler,
                        )
                    )
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async with (
        anyio.create_task_group() as tg,
        process,
    ):
        tg.start_soon(stdout_reader)
        tg.start_soon(stdin_writer)
        yield read_stream, write_stream

    # Ensure process is fully terminated
    await _terminate_process_tree(process)
