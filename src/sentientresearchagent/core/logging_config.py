"""
Enhanced logging configuration for SentientResearchAgent.

This module provides beautiful, readable logging with contextual emojis,
smart filtering, and clean formatting.
"""

from loguru import logger
import sys
from typing import Dict, Optional
from pathlib import Path


# Emoji mapping for different components and events
EMOJI_MAP = {
    # System events
    "start": "🚀",
    "ready": "✅",
    "stop": "🛑",
    "error": "❌",
    "warning": "⚠️",
    "success": "✨",
    "info": "ℹ️",
    
    # Components
    "server": "🌐",
    "agent": "🤖",
    "task": "📋",
    "node": "🔲",
    "graph": "🔗",
    "cache": "💾",
    "project": "📁",
    "config": "⚙️",
    "hitl": "👤",
    "websocket": "🔌",
    
    # Actions
    "create": "➕",
    "update": "🔄",
    "delete": "🗑️",
    "save": "💾",
    "load": "📂",
    "execute": "▶️",
    "plan": "📝",
    "search": "🔍",
    "think": "🤔",
    "complete": "✔️",
    "skip": "⏭️",
}


def get_emoji(text: str) -> str:
    """Get appropriate emoji for the log message."""
    text_lower = text.lower()
    
    # Check for specific keywords
    for keyword, emoji in EMOJI_MAP.items():
        if keyword in text_lower:
            return emoji
    
    # Default emojis based on log level are handled by format_record
    return ""


def format_record(record: Dict) -> str:
    """
    Ultra-clean format - just the message with colors and smart spacing.
    """
    message = record["message"]
    
    # Escape curly braces to prevent format string errors
    message = message.replace("{", "{{").replace("}", "}}")
    
    # Skip debug messages unless they're important
    level = record["level"].name
    if level == "DEBUG":
        # Filter out noisy debug messages
        skip_patterns = [
            "CONFIG DEBUG:",
            "Dynamically loaded",
            "Loaded environment variables",
        ]
        if any(pattern in message for pattern in skip_patterns):
            return ""  # Don't show these at all
        return f"<dim>{message}</dim>"
    
    # Clean up the message - remove timestamps and module prefixes
    import re
    
    # Remove timestamps
    message = re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ \| ', '', message)
    
    # Remove module paths like "sentientresearchagent.server.main:"
    message = re.sub(r'^[\w\.]+:\d+ - ', '', message)
    
    # Smart spacing - group related messages together
    prefix = ""
    
    # Add blank line before major sections
    section_starters = [
        "Starting", "Loading", "Initializing", "Creating",
        "Server", "System", "Agent", "✅", "🚀", "📋",
        "=====", "-----", "Example", "API", "WebSocket"
    ]
    
    if any(message.startswith(starter) for starter in section_starters):
        prefix = "\n"
    
    # Don't add spacing for continuation lines
    if message.startswith(("   ", " -", " *", "|", "    ")):
        prefix = ""
    
    # Format based on level - ALWAYS end with newline for proper separation
    if level in ["ERROR", "CRITICAL"]:
        return f"{prefix}<red>{message}</red>\n"
    elif level == "WARNING":
        return f"{prefix}<yellow>{message}</yellow>\n"
    elif level == "SUCCESS":
        return f"{prefix}<green><bold>{message}</bold></green>\n"
    else:
        # INFO and others
        return f"{prefix}{message}\n"


def get_console_format(style: str = "clean"):
    """Get console format based on style preference."""
    if style == "timestamp":
        # With timestamp
        return "<dim>{time:HH:mm:ss}</dim> | <level>{message}</level>"
    elif style == "detailed":
        # With level and module info
        return "<green>{time:HH:mm:ss}</green> | <level>{level: <5}</level> | <dim>{name}</dim> | <level>{message}</level>"
    else:
        # Clean format (default) - just uses format_record
        return format_record


def setup_logging(config: 'LoggingConfig', console_filter: Optional[callable] = None):
    """
    Set up enhanced logging configuration.
    
    Args:
        config: LoggingConfig instance
        console_filter: Optional filter function for console output
    """
    # Remove existing handlers
    logger.remove()
    
    # Console handler with custom formatting
    if config.enable_console:
        console_format = get_console_format(getattr(config, 'console_style', 'clean'))
        
        logger.add(
            sys.stdout,
            format=console_format,
            level=config.level,
            colorize=False,
            filter=console_filter,
            backtrace=True,
            diagnose=True,
            enqueue=True,  # Thread-safe logging
        )
    
    # File handler with clean format (no colors)
    if config.enable_file:
        log_path = config.get_log_file_path()
        if log_path:
            # Ensure log directory exists
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Simple format for files
            file_format = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name: <40} | "
                "{function: <20} | "
                "{message}"
            )
            
            # Get log file mode from environment variable (default: "a" for append)
            import os
            log_mode = os.getenv('LOG_FILE_MODE', 'a').lower()
            # Validate mode - only allow 'w' (write/truncate) or 'a' (append)
            if log_mode not in ['w', 'a']:
                log_mode = 'a'
            
            logger.add(
                str(log_path),
                format=file_format,
                level=config.level,
                rotation=config.file_rotation,
                retention=config.file_retention,
                compression="zip",  # Compress old logs
                backtrace=True,
                diagnose=False,  # No variable values in production logs
                enqueue=True,
                mode=log_mode,  # Configurable: "w" truncates, "a" appends
            )
    
    # Add custom log levels
    logger.level("PLAN", no=25, color="<blue>")
    logger.level("EXECUTE", no=26, color="<magenta>")
    
    logger.success(f"Logging configured: level={config.level}")


def create_module_filter(module_levels: Dict[str, str]):
    """
    Create a filter function based on module-specific log levels.
    
    Args:
        module_levels: Dict mapping module names to log levels
        
    Returns:
        Filter function for loguru
    """
    def filter_func(record):
        module = record["name"]
        
        # Check each module pattern
        for pattern, level in module_levels.items():
            if module.startswith(pattern):
                # Convert level string to number
                level_no = logger.level(level).no
                return record["level"].no >= level_no
        
        # Default: allow all messages
        return True
    
    return filter_func


# Convenient log functions for clean output
def log_start(message: str):
    """Log a start event."""
    logger.info(f"Starting {message}")


def log_success(message: str):
    """Log a success event."""
    logger.success(message)


def log_plan(message: str):
    """Log a planning event."""
    logger.info(f"Planning: {message}")


def log_execute(message: str):
    """Log an execution event."""
    logger.info(f"Executing: {message}")


def log_node(node_id: str, message: str):
    """Log a node-related event."""
    logger.info(f"[{node_id}] {message}")


def log_agent(agent_name: str, message: str):
    """Log an agent-related event."""
    logger.info(f"[{agent_name}] {message}")


def log_hitl(message: str):
    """Log a human-in-the-loop event."""
    logger.info(f"HITL: {message}")


def log_websocket(event: str, message: str):
    """Log a websocket event."""
    logger.debug(f"WebSocket [{event}]: {message}")


def log_section(title: str, char: str = "="):
    """Log a section header with separator."""
    separator = char * len(title)
    logger.info(f"\n{separator}\n{title}\n{separator}")
