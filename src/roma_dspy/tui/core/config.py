"""Configuration management for TUI.

Loads configuration from TOML file with sensible defaults.
Location: ~/.config/roma_tui/config.toml
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from loguru import logger


@dataclass
class ApiConfig:
    """API configuration."""
    base_url: str = "http://localhost:8000"
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class UIConfig:
    """UI configuration."""
    poll_interval: float = 2.0
    max_timeline_bars: int = 50
    show_io_default: bool = False
    auto_refresh: bool = False


@dataclass
class PerformanceConfig:
    """Performance configuration."""
    cache_enabled: bool = True
    cache_size_mb: int = 100
    cache_ttl_seconds: int = 3600
    max_concurrent_renders: int = 3


@dataclass
class KeyBindings:
    """Keyboard shortcuts configuration."""
    quit: List[str] = field(default_factory=lambda: ["q"])
    search: List[str] = field(default_factory=lambda: ["/"])
    export: List[str] = field(default_factory=lambda: ["e"])
    bookmark: List[str] = field(default_factory=lambda: ["b"])
    copy: List[str] = field(default_factory=lambda: ["c"])
    help: List[str] = field(default_factory=lambda: ["?"])
    toggle_io: List[str] = field(default_factory=lambda: ["t"])
    reload: List[str] = field(default_factory=lambda: ["r"])
    toggle_live: List[str] = field(default_factory=lambda: ["l"])


@dataclass
class ExportConfig:
    """Export configuration."""
    default_format: str = "json"
    output_directory: str = "~/roma_exports"


@dataclass
class Config:
    """Main configuration container."""
    api: ApiConfig = field(default_factory=ApiConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    keybindings: KeyBindings = field(default_factory=KeyBindings)
    export: ExportConfig = field(default_factory=ExportConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Load configuration from TOML file or use defaults.

        Args:
            config_path: Path to config file. If None, uses default location.

        Returns:
            Config object
        """
        if config_path is None:
            config_path = cls.get_default_config_path()

        config = cls()

        # If config file doesn't exist, return defaults and create default file
        if not config_path.exists():
            logger.info(f"Config file not found at {config_path}, using defaults")
            cls._create_default_config(config_path)
            return config

        # Load TOML config
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # Fallback for Python < 3.11
            except ImportError:
                logger.warning("toml library not available, using default config")
                return config

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            # Parse sections
            if "api" in data:
                config.api = ApiConfig(**data["api"])
            if "ui" in data:
                config.ui = UIConfig(**data["ui"])
            if "performance" in data:
                config.performance = PerformanceConfig(**data["performance"])
            if "keybindings" in data:
                config.keybindings = KeyBindings(**data["keybindings"])
            if "export" in data:
                config.export = ExportConfig(**data["export"])

            logger.info(f"Loaded config from {config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            logger.info("Using default configuration")
            return cls()

    @staticmethod
    def get_default_config_path() -> Path:
        """Get default configuration file path.

        Returns:
            Path to ~/.config/roma_tui/config.toml
        """
        config_dir = Path.home() / ".config" / "roma_tui"
        return config_dir / "config.toml"

    @staticmethod
    def _create_default_config(config_path: Path) -> None:
        """Create default configuration file.

        Args:
            config_path: Path where to create config file
        """
        config_dir = config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        default_config = """# ROMA-DSPy TUI Configuration
# Location: ~/.config/roma_tui/config.toml

[api]
base_url = "http://localhost:8000"
timeout = 10.0
max_retries = 3
retry_delay = 1.0

[ui]
poll_interval = 2.0
max_timeline_bars = 50
show_io_default = false
auto_refresh = false

[performance]
cache_enabled = true
cache_size_mb = 100
cache_ttl_seconds = 3600
max_concurrent_renders = 3

[keybindings]
quit = ["q"]
search = ["/"]
export = ["e"]
bookmark = ["b"]
copy = ["c"]
help = ["?"]
toggle_io = ["t"]
reload = ["r"]
toggle_live = ["l"]

[export]
default_format = "json"
output_directory = "~/roma_exports"
"""

        try:
            with open(config_path, "w") as f:
                f.write(default_config)
            logger.info(f"Created default config at {config_path}")
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")

    def save(self, config_path: Path | None = None) -> None:
        """Save configuration to TOML file.

        Args:
            config_path: Path to save config. If None, uses default location.
        """
        if config_path is None:
            config_path = self.get_default_config_path()

        config_dir = config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        # Build TOML content
        content = f"""# ROMA-DSPy TUI Configuration

[api]
base_url = "{self.api.base_url}"
timeout = {self.api.timeout}
max_retries = {self.api.max_retries}
retry_delay = {self.api.retry_delay}

[ui]
poll_interval = {self.ui.poll_interval}
max_timeline_bars = {self.ui.max_timeline_bars}
show_io_default = {str(self.ui.show_io_default).lower()}
auto_refresh = {str(self.ui.auto_refresh).lower()}

[performance]
cache_enabled = {str(self.performance.cache_enabled).lower()}
cache_size_mb = {self.performance.cache_size_mb}
cache_ttl_seconds = {self.performance.cache_ttl_seconds}
max_concurrent_renders = {self.performance.max_concurrent_renders}

[keybindings]
quit = {self.keybindings.quit}
search = {self.keybindings.search}
export = {self.keybindings.export}
bookmark = {self.keybindings.bookmark}
copy = {self.keybindings.copy}
help = {self.keybindings.help}
toggle_io = {self.keybindings.toggle_io}
reload = {self.keybindings.reload}
toggle_live = {self.keybindings.toggle_live}

[export]
default_format = "{self.export.default_format}"
output_directory = "{self.export.output_directory}"
"""

        try:
            with open(config_path, "w") as f:
                f.write(content)
            logger.info(f"Saved config to {config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
