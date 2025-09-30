"""
Request Validation Utilities

Provides validation functions for API requests.
"""

from typing import Dict, Any, List, Optional, Tuple
from flask import request
from loguru import logger


class RequestValidator:
    """
    Validates incoming requests and provides consistent error handling.
    """
    
    @staticmethod
    def validate_json_required(required_fields: List[str]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate that request contains JSON with required fields.
        
        Args:
            required_fields: List of required field names
            
        Returns:
            Tuple of (is_valid, error_message, data)
        """
        try:
            data = request.get_json()
            if not data:
                return False, "Request must contain JSON data", None
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}", None
            
            return True, None, data
            
        except Exception as e:
            logger.error(f"JSON validation error: {e}")
            return False, "Invalid JSON format", None
    
    @staticmethod
    def validate_project_goal(goal: str) -> Tuple[bool, Optional[str]]:
        """
        Validate project goal string.
        
        Args:
            goal: Project goal to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not goal or not isinstance(goal, str):
            return False, "Goal must be a non-empty string"
        
        if len(goal.strip()) < 3:
            return False, "Goal must be at least 3 characters long"
        
        if len(goal) > 10000:
            return False, "Goal must be 10000 characters or fewer"
        
        return True, None
    
    @staticmethod
    def validate_max_steps(max_steps: Any) -> Tuple[bool, Optional[str], int]:
        """
        Validate max_steps parameter.
        
        Args:
            max_steps: Max steps value to validate
            
        Returns:
            Tuple of (is_valid, error_message, validated_value)
        """
        try:
            steps = int(max_steps)
            if steps < 1:
                return False, "max_steps must be at least 1", 0
            if steps > 10000:
                return False, "max_steps must be less than 10000", 0
            return True, None, steps
        except (ValueError, TypeError):
            return False, "max_steps must be a valid integer", 0
    
    @staticmethod
    def validate_project_config(config_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate project configuration data.
        
        Args:
            config_data: Configuration data to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_sections = ['llm', 'execution', 'cache']
        for section in required_sections:
            if section not in config_data:
                return False, f"Missing required config section: {section}"
        
        # Validate LLM config
        llm_config = config_data['llm']
        if 'provider' not in llm_config or 'model' not in llm_config:
            return False, "LLM config must include provider and model"
        
        # Validate execution config
        exec_config = config_data['execution']
        required_exec_fields = ['max_concurrent_nodes', 'max_execution_steps', 'enable_hitl']
        for field in required_exec_fields:
            if field not in exec_config:
                return False, f"Missing required execution config field: {field}"
        
        return True, None
