"""
Tracing models for node processing stages.
"""

import uuid
import json
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from loguru import logger


def make_json_safe(obj):
    """Recursively make an object JSON serializable."""
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif hasattr(obj, '__dict__'):
        # For objects like LiteLLM, extract useful info
        if hasattr(obj, 'model'):
            return f"Model: {obj.model}"
        elif 'LiteLLM' in str(type(obj)):
            return f"LiteLLM Model: {getattr(obj, 'model', 'unknown')}"
        else:
            return str(obj)
    else:
        return str(obj)


class ProcessingStage(BaseModel):
    """Represents a single processing stage for a node."""
    stage_name: str  # "atomization", "planning", "execution", "aggregation"
    stage_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    status: Literal["running", "completed", "failed"] = "running"
    
    # Agent/Adapter information
    agent_name: Optional[str] = None
    adapter_name: Optional[str] = None
    model_info: Optional[Dict[str, Any]] = None
    
    # LLM Interaction data
    system_prompt: Optional[str] = None
    user_input: Optional[str] = None
    llm_response: Optional[str] = None
    
    # Tool execution data
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_execution_count: Optional[int] = None
    tool_call_duration_ms: Optional[float] = None
    
    # Context and processing data
    input_context: Optional[Dict[str, Any]] = None
    processing_parameters: Optional[Dict[str, Any]] = None
    output_data: Optional[Any] = None
    
    # Error information
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    class Config:
        # Allow arbitrary field assignment for dynamic updates
        extra = "allow"
        # Validate assignments to ensure data integrity
        validate_assignment = True
    
    def update_fields(self, **kwargs):
        """Safely update multiple fields at once."""
        for key, value in kwargs.items():
            # Special handling for additional_data - merge instead of replace
            if key == 'additional_data' and hasattr(self, 'additional_data') and isinstance(self.additional_data, dict) and isinstance(value, dict):
                # Merge the new additional_data with existing
                existing_data = getattr(self, 'additional_data', {})
                merged_data = {**existing_data, **value}
                setattr(self, key, merged_data)
                logger.debug(f"ProcessingStage.update_fields: Merged additional_data - existing keys: {list(existing_data.keys())}, new keys: {list(value.keys())}, merged keys: {list(merged_data.keys())}")
            else:
                # Use setattr for all other fields
                setattr(self, key, value)
                if not hasattr(self.__class__, key):
                    logger.debug(f"ProcessingStage.update_fields: Set extra field '{key}'")
    
    def complete_stage(self, output_data: Any = None, error: str = None):
        """Mark the stage as completed or failed."""
        self.completed_at = datetime.now()
        if error:
            self.status = "failed"
            self.error_message = error
        else:
            self.status = "completed"
            if output_data is not None:
                self.output_data = output_data
    
    def get_duration_ms(self) -> Optional[int]:
        """Get stage duration in milliseconds."""
        if self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None
    
    def to_dict_safe(self) -> Dict[str, Any]:
        """Convert to dictionary with JSON-safe serialization."""
        # Use Pydantic's model_dump() method to get all fields including extras
        all_fields = self.model_dump()
        
        # Debug log all fields
        logger.debug(f"ProcessingStage.to_dict_safe: model_dump returned fields: {list(all_fields.keys())}")
        
        # Build result with proper serialization
        result = {}
        for key, value in all_fields.items():
            if key in ["started_at", "completed_at"]:
                # Handle datetime fields
                if key == "started_at":
                    result[key] = self.started_at.isoformat()
                elif key == "completed_at":
                    result[key] = self.completed_at.isoformat() if self.completed_at else None
            else:
                # Use make_json_safe for all other fields
                result[key] = make_json_safe(value)
        
        # Add duration_ms which is computed
        result["duration_ms"] = self.get_duration_ms()
        
        # Debug log to check if additional_data is included
        if "additional_data" in result:
            logger.debug(
                "ProcessingStage.to_dict_safe: additional_data keys %s",
                list(result['additional_data'].keys())
                if isinstance(result['additional_data'], dict)
                else 'Not a dict'
            )
        else:
            logger.debug("ProcessingStage.to_dict_safe: No additional_data found in result")
        
        return result


class NodeProcessingTrace(BaseModel):
    """Complete trace of all processing stages for a node."""
    node_id: str
    node_goal: str
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    
    stages: List[ProcessingStage] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_stage(self, stage_name: str, **kwargs) -> ProcessingStage:
        """Add a new processing stage."""
        stage = ProcessingStage(stage_name=stage_name, **kwargs)
        self.stages.append(stage)
        return stage
    
    def get_stage(self, stage_name: str) -> Optional[ProcessingStage]:
        """Get the most recent stage by name."""
        for stage in reversed(self.stages):
            if stage.stage_name == stage_name:
                return stage
        return None
    
    def get_stage_by_id(self, stage_id: str) -> Optional[ProcessingStage]:
        """Get stage by ID."""
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization with safety."""
        return {
            "node_id": self.node_id,
            "node_goal": self.node_goal,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
            "stages": [stage.to_dict_safe() for stage in self.stages],
            "metadata": make_json_safe(self.metadata)
        } 
