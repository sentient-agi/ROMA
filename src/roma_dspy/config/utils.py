"""Utility functions for configuration management."""

from typing import Dict, Any, Union
from omegaconf import DictConfig, OmegaConf
from pathlib import Path

from roma_dspy.config.schemas.root import ROMAConfig


def merge_configs(*configs: DictConfig) -> DictConfig:
    """
    Merge multiple configurations.

    Args:
        *configs: Configuration objects to merge

    Returns:
        Merged configuration
    """
    result = OmegaConf.create({})
    for config in configs:
        result = OmegaConf.merge(result, config)
    return result


def interpolate_config(config: DictConfig, context: Dict[str, Any]) -> DictConfig:
    """
    Interpolate configuration with context variables.

    Args:
        config: Configuration to interpolate
        context: Context variables for interpolation

    Returns:
        Configuration with interpolations resolved
    """
    # Add context to config for interpolation
    config_with_context = OmegaConf.merge(
        config, OmegaConf.create({"_context": context})
    )
    OmegaConf.resolve(config_with_context)
    return config_with_context


def _convert_to_serializable(obj: Any) -> Any:
    """
    Recursively convert Pydantic models and dataclasses to serializable dicts.
    
    This handles nested structures that OmegaConf.structured() cannot process.
    """
    from dataclasses import is_dataclass, asdict
    from pydantic import BaseModel
    
    if isinstance(obj, BaseModel):
        # Pydantic BaseModel - use model_dump
        return {k: _convert_to_serializable(v) for k, v in obj.model_dump().items()}
    elif is_dataclass(obj) and not isinstance(obj, type):
        # Pydantic dataclass or stdlib dataclass instance
        try:
            # Try to get fields and convert recursively
            result = {}
            for field_name in obj.__dataclass_fields__:
                value = getattr(obj, field_name)
                result[field_name] = _convert_to_serializable(value)
            return result
        except Exception:
            # Fallback to asdict if available
            return asdict(obj)
    elif isinstance(obj, dict):
        return {k: _convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_serializable(item) for item in obj]
    elif isinstance(obj, Path):
        return str(obj)
    else:
        return obj


def config_to_dict(
    config: Union[ROMAConfig, DictConfig], resolve: bool = True
) -> Dict[str, Any]:
    """
    Convert configuration to plain dictionary.

    Args:
        config: Configuration to convert
        resolve: Whether to resolve interpolations

    Returns:
        Plain dictionary representation
    """
    if isinstance(config, DictConfig):
        return OmegaConf.to_container(config, resolve=resolve)
    
    # For ROMAConfig and other Pydantic/dataclass objects,
    # recursively convert to dict to handle nested Pydantic models
    return _convert_to_serializable(config)


def validate_config_file(config_path: Path) -> bool:
    """
    Validate that a configuration file can be loaded.

    Args:
        config_path: Path to configuration file

    Returns:
        True if valid, False otherwise
    """
    try:
        OmegaConf.load(config_path)
        return True
    except Exception:
        return False


def get_config_diff(
    config1: Union[ROMAConfig, DictConfig], config2: Union[ROMAConfig, DictConfig]
) -> Dict[str, Any]:
    """
    Get differences between two configurations.

    Args:
        config1: First configuration
        config2: Second configuration

    Returns:
        Dictionary showing differences
    """
    dict1 = config_to_dict(config1)
    dict2 = config_to_dict(config2)

    return _dict_diff(dict1, dict2)


def _dict_diff(
    dict1: Dict[str, Any], dict2: Dict[str, Any], path: str = ""
) -> Dict[str, Any]:
    """
    Recursively find differences between two dictionaries.

    Args:
        dict1: First dictionary
        dict2: Second dictionary
        path: Current path in the nested structure

    Returns:
        Dictionary of differences
    """
    diff = {}

    # Check all keys in dict1
    for key in dict1:
        current_path = f"{path}.{key}" if path else key

        if key not in dict2:
            diff[current_path] = {"removed": dict1[key]}
        elif isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
            nested_diff = _dict_diff(dict1[key], dict2[key], current_path)
            diff.update(nested_diff)
        elif dict1[key] != dict2[key]:
            diff[current_path] = {"from": dict1[key], "to": dict2[key]}

    # Check for new keys in dict2
    for key in dict2:
        if key not in dict1:
            current_path = f"{path}.{key}" if path else key
            diff[current_path] = {"added": dict2[key]}

    return diff
