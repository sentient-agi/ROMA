"""Configuration manager using OmegaConf for ROMA-DSPy."""

from omegaconf import OmegaConf, DictConfig
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import os

from loguru import logger

from roma_dspy.config.schemas.root import ROMAConfig


class ConfigManager:
    """Manages configuration loading and merging with OmegaConf."""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize ConfigManager.

        Args:
            config_dir: Directory containing configuration files. Defaults to "config".
        """
        self.config_dir = config_dir or Path("config")
        self._cache: Dict[str, DictConfig] = {}
        self._loaded_profile_name: Optional[str] = None

    def load_config(
        self,
        config_path: Optional[Union[Path, str]] = None,
        profile: Optional[str] = None,
        overrides: Optional[List[str]] = None,
        env_prefix: str = "ROMA_"
    ) -> ROMAConfig:
        """
        Load configuration with layered approach.

        Resolution order:
        1. Start with Pydantic defaults
        2. Merge YAML config if provided
        3. Apply profile if specified
        4. Apply CLI/runtime overrides
        5. Apply environment variables
        6. Validate with Pydantic

        Args:
            config_path: Path to YAML configuration file
            profile: Profile name to apply
            overrides: List of configuration overrides (e.g., ["agents.executor.llm.temperature=0.9"])
            env_prefix: Prefix for environment variables (default: "ROMA_")

        Returns:
            Validated ROMAConfig instance

        Raises:
            FileNotFoundError: If config file or profile not found
            ValueError: If configuration validation fails
        """
        logger.debug(
            f"Loading config: path={config_path}, profile={profile}, "
            f"overrides={overrides}, env_prefix={env_prefix}"
        )

        # Step 1: Start from an empty OmegaConf and let Pydantic apply defaults
        # later. This avoids type conflicts when merging YAML into a structured
        # config containing FieldInfo defaults from pydantic dataclasses.
        base_config = OmegaConf.create({})
        logger.debug("Initialized empty base config (defaults applied in validation)")

        # Step 2: Load and merge YAML config if provided
        if config_path:
            # Convert string to Path if needed
            config_path = Path(config_path) if isinstance(config_path, str) else config_path
            yaml_config = self._load_yaml(config_path)
            base_config = OmegaConf.merge(base_config, yaml_config)
            logger.debug(f"Merged YAML config from {config_path}")
        else:
            # If no explicit config provided, attempt to merge defaults
            default_cfg_path = self.config_dir / "defaults" / "config.yaml"
            if default_cfg_path.exists():
                yaml_config = self._load_yaml(default_cfg_path)
                base_config = OmegaConf.merge(base_config, yaml_config)
                logger.debug(f"Merged default config from {default_cfg_path}")

        # Step 3: Apply profile overlay if specified
        if profile:
            profile_config = self._load_profile(profile)
            base_config = OmegaConf.merge(base_config, profile_config)
            self._loaded_profile_name = profile  # Track which profile was loaded
            logger.debug(f"Applied profile: {profile}")

        # Step 4: Apply runtime overrides
        if overrides:
            override_config = OmegaConf.from_dotlist(overrides)
            base_config = OmegaConf.merge(base_config, override_config)
            logger.debug(f"Applied overrides: {overrides}")

        # Step 5: Apply environment variables
        env_config = self._load_env_vars(env_prefix)
        if env_config:
            base_config = OmegaConf.merge(base_config, env_config)
            logger.debug(f"Applied environment variables with prefix {env_prefix}")

        # Step 6: Resolve interpolations
        OmegaConf.resolve(base_config)
        logger.debug("Resolved interpolations")

        # Step 7: Convert to Pydantic for validation
        try:
            config_dict = OmegaConf.to_container(base_config, resolve=True)
            # Apply Pydantic dataclass defaults while validating the merged config
            validated_config = ROMAConfig(**(config_dict or {}))
            logger.info("Configuration loaded and validated successfully")
            return validated_config
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}")

    def _load_yaml(self, path: Path) -> DictConfig:
        """Load YAML configuration file with caching."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        path_str = str(path)
        if path_str in self._cache:
            logger.debug(f"Using cached config for {path}")
            return self._cache[path_str]

        try:
            config = OmegaConf.load(path)
            self._cache[path_str] = config
            logger.debug(f"Loaded and cached config from {path}")
            return config
        except Exception as e:
            raise ValueError(f"Failed to load YAML config from {path}: {e}")

    def _load_profile(self, profile_name: str) -> DictConfig:
        """Load profile configuration."""
        profile_path = self.config_dir / "profiles" / f"{profile_name}.yaml"

        if not profile_path.exists():
            # List available profiles for helpful error message
            profiles_dir = self.config_dir / "profiles"
            if profiles_dir.exists():
                available = [p.stem for p in profiles_dir.glob("*.yaml")]
                raise ValueError(
                    f"Profile '{profile_name}' not found. Available profiles: {available}"
                )
            else:
                raise ValueError(
                    f"Profile '{profile_name}' not found. Profiles directory does not exist: {profiles_dir}"
                )

        return self._load_yaml(profile_path)

    def _load_env_vars(self, prefix: str) -> Optional[DictConfig]:
        """
        Load environment variables with the strict double-underscore schema prefix.

        Only variables starting with f"{prefix}__" are considered configuration overrides.
        This prevents unrelated env vars like ROMA_S3_BUCKET from polluting the
        config root and breaking validation.

        Example mapping:
          ROMA__AGENTS__EXECUTOR__LLM__MODEL=gpt-4o
            -> agents.executor.llm.model=gpt-4o
        """
        env_vars = {}

        strict_prefix = f"{prefix}__"

        for key, value in os.environ.items():
            if key.startswith(strict_prefix):
                # Strip strict prefix and convert double-underscores to dots
                config_key = key[len(strict_prefix):].lower().replace("__", ".")
                env_vars[config_key] = value

        if env_vars:
            logger.debug(
                f"Found config override env vars: {list(env_vars.keys())}"
            )
            return OmegaConf.from_dotlist([f"{k}={v}" for k, v in env_vars.items()])
        return None

    def save_config(self, config: ROMAConfig, path: Path) -> None:
        """
        Save configuration to YAML file.

        Args:
            config: Configuration to save
            path: Output file path
        """
        try:
            # Convert back to OmegaConf for saving
            config_dict = OmegaConf.structured(config)

            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            OmegaConf.save(config_dict, path)
            logger.info(f"Configuration saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save configuration to {path}: {e}")
            raise

    def print_config(self, config: ROMAConfig) -> None:
        """Pretty print configuration."""
        config_dict = OmegaConf.structured(config)
        print(OmegaConf.to_yaml(config_dict))

    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._cache.clear()
        logger.debug("Configuration cache cleared")

    def get_available_profiles(self) -> List[str]:
        """Get list of available profile names."""
        profiles_dir = self.config_dir / "profiles"
        if not profiles_dir.exists():
            return []

        profiles = []
        for profile_file in profiles_dir.glob("*.yaml"):
            profiles.append(profile_file.stem)

        return sorted(profiles)

    @property
    def loaded_profile_name(self) -> Optional[str]:
        """
        Get the name of the most recently loaded profile.

        Returns:
            Profile name if a profile was loaded, None otherwise
        """
        return self._loaded_profile_name
