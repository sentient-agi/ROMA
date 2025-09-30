from abc import ABC, abstractmethod
from typing import Dict, Any, Union, List, TypeVar, Generic, Type, Optional
from loguru import logger # Add this
from agno.agent import Agent as AgnoAgent # Renaming to avoid conflict if we define our own Agent interface
# It's good practice to also import the async version if available and distinct
# from agno.agent import AsyncAgent as AsyncAgnoAgent # Assuming such an import exists for type hinting
import asyncio # Add this import
from datetime import datetime
import inspect
import re
import json
import os
from json_repair import repair_json
from agno.agent import Agent as AgnoAgent

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode # For type hinting
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import (
    ContextItem, PlanOutput, AtomizerOutput, AgentTaskInput, PlannerInput, ExecutionHistoryItem,
    PlanModifierInput # Added PlanModifierInput
)

# FIX: Import NodeType from types module
from sentientresearchagent.hierarchical_agent_framework.types import NodeType

# Import prompt templates
from .prompts import INPUT_PROMPT, AGGREGATOR_PROMPT

from sentientresearchagent.exceptions import (
    AgentExecutionError, AgentTimeoutError, AgentRateLimitError,
    handle_exception, create_error_context
)
# Lazy import to avoid circular import
# from sentientresearchagent.core.error_handler import handle_agent_errors, ErrorRecovery
# Lazy import to avoid circular import
# from sentientresearchagent.core.cache.decorators import cache_agent_response, cache_get, cache_set

from ..tracing.manager import TraceManager

InputType = TypeVar('InputType')
OutputType = TypeVar('OutputType')

class BaseAdapter(ABC):
    """
    Abstract base class for all agent adapters in this framework.
    An adapter is responsible for interfacing between the framework's
    TaskNode/context and a specific agent implementation (e.g., an AgnoAgent).
    """
    def __init__(self, agent_name: str = "BaseAdapter"):
        """
        Initializes the adapter with a name.
        
        Args:
            agent_name: A descriptive name for logging and identification.
        """
        self.agent_name = agent_name

    @abstractmethod
    async def process(self, node: TaskNode, agent_task_input: Any, trace_manager: "TraceManager") -> Any: # Changed to async def
        """
        Processes a TaskNode using the adapted agent.

        Args:
            node: The TaskNode to process.
            agent_task_input: The structured input for the agent (usually AgentTaskInput).
                              Contains current_goal, context_items, etc.

        Returns:
            The result from the agent, which could be a Pydantic model (like PlanOutput),
            a string, or a structure for multi-modal content.
        """
        pass

class LlmApiAdapter(BaseAdapter, Generic[InputType, OutputType]):
    """
    Base adapter for agents implemented using the Agno library.
    This adapter simplifies interaction by leveraging Agno's native
    structured output and tool handling.
    """
    def __init__(self, agno_agent_instance: AgnoAgent, agent_name: str = "LlmApiAdapter"):
        """
        Args:
            agno_agent_instance: The instantiated AgnoAgent.
            agent_name: A descriptive name for logging.
        """
        super().__init__(agent_name)
        if not agno_agent_instance:
            raise ValueError(f"{agent_name} requires a valid AgnoAgent instance.")
        self.agno_agent = agno_agent_instance
        
        # Store the original system message template for multi-project use
        self._original_system_message = getattr(agno_agent_instance, 'system_message', None)

    def _format_context_for_prompt(self, context_items: List[ContextItem]) -> str:
        """
        Formats a list of ContextItem objects into a string for the LLM prompt.
        Focuses on text-based content for now. Multi-modal context would require
        different handling (passing objects to agno_agent.run()).
        """
        if not context_items:
            return "No relevant context was provided."

        context_parts = ["Relevant Context:"]
        for item in context_items:
            content_str = str(item.content) # Basic string conversion
            # Consider adding more sophisticated formatting based on item.content_type_description
            
            context_parts.append(f"--- Context from Task '{item.source_task_id}' (Goal: {item.source_task_goal}) ---")
            context_parts.append(content_str)
            context_parts.append(f"--- End Context from Task '{item.source_task_id}' ---")
        
        return "\n\n".join(context_parts)

    def _get_task_specific_instructions(self, task_type: str) -> str:
        """Get specific instructions based on task type."""
        instructions = {
            "PLAN": "Generate a detailed plan with sub-tasks. Each sub-task should have a clear goal, appropriate task_type, and node_type.",
            "WRITE": "Write comprehensive, well-structured content that addresses the goal. Include relevant examples and citations when appropriate.",
            "SEARCH": "Conduct thorough research using available tools. Provide detailed findings with sources and verification.",
            "THINK": "Perform deep analysis and reasoning. Present logical conclusions with supporting evidence.",
            "AGGREGATE": "Synthesize information from all provided sources into a coherent summary. Highlight key insights and connections."
        }
        return instructions.get(task_type.upper(), "Complete the task according to the specified goal and requirements.")

    def _prepare_agno_run_arguments(self, agent_task_input: InputType) -> str:
        """
        Prepares the user message string for self.agno_agent.arun()
        based on AgentTaskInput or PlannerInput.
        """
        if isinstance(agent_task_input, PlannerInput):
            prompt_parts = [
                f"Overall Objective: {agent_task_input.overall_objective}",
                f"Current Task Goal: {agent_task_input.current_task_goal}"
            ]

            if agent_task_input.parent_task_goal:
                prompt_parts.append(f"Parent Task Goal: {agent_task_input.parent_task_goal}")

            prompt_parts.append(f"Current Planning Depth: {agent_task_input.planning_depth}")

            if agent_task_input.global_constraints_or_preferences:
                constraints_str = "\n  - ".join(agent_task_input.global_constraints_or_preferences)
                prompt_parts.append(f"Global Constraints/Preferences:\n  - {constraints_str}")

            history_context_parts = []
            if agent_task_input.execution_history_and_context:
                h_and_c = agent_task_input.execution_history_and_context
                if h_and_c.prior_sibling_task_outputs:
                    history_context_parts.append("  Prior Sibling Task Outputs:")
                    for item in h_and_c.prior_sibling_task_outputs:
                        history_context_parts.append(f"    - Task: {item.task_goal}, Summary: {item.outcome_summary}")
                if h_and_c.relevant_ancestor_outputs:
                    history_context_parts.append("  Relevant Ancestor Outputs:")
                    for item in h_and_c.relevant_ancestor_outputs:
                        history_context_parts.append(f"    - Task: {item.task_goal}, Summary: {item.outcome_summary}")
                if h_and_c.global_knowledge_base_summary:
                     history_context_parts.append(f"  Global Knowledge Base Summary: {h_and_c.global_knowledge_base_summary}")
            
            if history_context_parts:
                prompt_parts.append("Execution History & Context:")
                prompt_parts.extend(history_context_parts)

            if agent_task_input.replan_request_details:
                replan_parts = ["Re-plan Details (CRITICAL - address this in your new plan):"]
                rd = agent_task_input.replan_request_details
                replan_parts.append(f"  Failed Sub-Goal: {rd.failed_sub_goal}")
                replan_parts.append(f"  Reason for Re-plan: {rd.reason_for_failure_or_replan}")
                if rd.previous_attempt_output_summary:
                    replan_parts.append(f"  Previous Attempt Summary: {rd.previous_attempt_output_summary}")
                if rd.specific_guidance_for_replan:
                    replan_parts.append(f"  Specific Guidance: {rd.specific_guidance_for_replan}")
                prompt_parts.extend(replan_parts)

            prompt_parts.append("\nBased on the 'Current Task Goal' and other provided information, generate a plan to achieve it.")
            
            formatted_user_message_string = "\n\n".join(prompt_parts)
            # logger.debug(f"    Adapter '{self.agent_name}': FINAL PROMPT being sent to Agno Agent:\n{formatted_user_message_string}") # Keep logging minimal here
            return formatted_user_message_string

        elif isinstance(agent_task_input, AgentTaskInput):
            # 🔥 USE THE ENHANCED FORMATTED CONTEXT!
            if hasattr(agent_task_input, 'formatted_full_context') and agent_task_input.formatted_full_context:
                # Use the new enhanced hierarchical context
                logger.info(f"🔥 Using enhanced hierarchical context for {self.agent_name}")
                
                prompt_template_to_use = INPUT_PROMPT
                if "aggregator" in self.agent_name.lower():
                    prompt_template_to_use = AGGREGATOR_PROMPT

                overall_goal_for_template = agent_task_input.overall_project_goal or "Not specified"
                
                main_user_message_content = prompt_template_to_use.format(
                    input_goal=agent_task_input.current_goal,
                    context_str=agent_task_input.formatted_full_context,  # 🔥 USE THE NEW CONTEXT!
                    overall_project_goal=overall_goal_for_template
                )
            else:
                # Fallback to old method if no enhanced context
                logger.info(f"🔥 Falling back to old context method for {self.agent_name}")
                prompt_template_to_use = INPUT_PROMPT
                if "aggregator" in self.agent_name.lower():
                    prompt_template_to_use = AGGREGATOR_PROMPT

                text_context_str = self._format_context_for_prompt(agent_task_input.relevant_context_items)
                overall_goal_for_template = agent_task_input.overall_project_goal or "Not specified"
                
                main_user_message_content = prompt_template_to_use.format(
                    input_goal=agent_task_input.current_goal,
                    context_str=text_context_str,
                    overall_project_goal=overall_goal_for_template
                )
            
            return main_user_message_content
        
        elif isinstance(agent_task_input, PlanModifierInput):
            try:
                original_plan_json_str = agent_task_input.original_plan.model_dump_json(indent=2)
            except Exception as e:
                logger.error(f"Error serializing original_plan to JSON for PlanModifierInput: {e}")
                original_plan_json_str = str(agent_task_input.original_plan.model_dump())

            prompt_content = f"""Overall Objective:
{agent_task_input.overall_objective}

Original Plan JSON:
{original_plan_json_str}

User Modification Instructions:
{agent_task_input.user_modification_instructions}

Based on the 'User Modification Instructions', revise the 'Original Plan JSON' to better achieve the 'Overall Objective'.
Ensure your output is a valid JSON conforming to the PlanOutput schema, containing a list of sub-tasks.
"""
            logger.debug(f"    Adapter '{self.agent_name}': PlanModifierInput prompt prepared.")
            return prompt_content
        
        else:
            raise TypeError(f"Unsupported agent_task_input type: {type(agent_task_input)} for _prepare_agno_run_arguments")

    def _get_model_info(self) -> Dict[str, Any]:
        """Extract model information from the AgnoAgent."""
        model_info = {
            "adapter_name": self.agent_name,
            "model_provider": "unknown",
            "model_name": "unknown",
            "model_id": "unknown"
        }
        
        try:
            if hasattr(self.agno_agent, 'model') and self.agno_agent.model:
                model = self.agno_agent.model
                
                # Try multiple approaches to get model information
                model_id = None
                
                # Method 1: Direct model.id
                if hasattr(model, 'id') and model.id:
                    model_id = model.id
                    
                # Method 2: Model name attribute  
                elif hasattr(model, 'name') and model.name:
                    model_id = model.name
                    
                # Method 3: Check if it's a LiteLLM model with model attribute
                elif hasattr(model, 'model') and model.model:
                    model_id = model.model
                    
                # Method 4: Check for _model attribute (some LiteLLM versions)
                elif hasattr(model, '_model') and model._model:
                    model_id = model._model
                    
                # Method 5: Look in model configuration/args
                elif hasattr(model, '__dict__'):
                    for attr in ['model', '_model', 'model_name', 'engine']:
                        if hasattr(model, attr):
                            val = getattr(model, attr)
                            if val and isinstance(val, str) and val not in ['unknown', '']:
                                model_id = val
                                break
                
                if model_id:
                    model_info["model_id"] = model_id
                    
                    # Parse model ID for provider and name
                    if "/" in model_id:
                        # Format like "openrouter/anthropic/claude-3-sonnet" or "anthropic/claude-3-sonnet"
                        parts = model_id.split("/")
                        if len(parts) >= 2:
                            # If it looks like provider/model or provider/company/model
                            if parts[0] in ['openrouter', 'anthropic', 'openai', 'google', 'cohere', 'mistral']:
                                model_info["model_provider"] = parts[0]
                                model_info["model_name"] = "/".join(parts[1:])
                            else:
                                # Assume first part is provider, rest is model
                                model_info["model_provider"] = parts[0]  
                                model_info["model_name"] = "/".join(parts[1:])
                    else:
                        # No slash - could be direct model name like "gpt-4", "claude-3-sonnet-20241022"
                        model_info["model_name"] = model_id
                        
                        # Infer provider from model name
                        if model_id.startswith(('gpt-', 'text-', 'davinci', 'o1-')):
                            model_info["model_provider"] = "openai"
                        elif model_id.startswith(('claude-', 'claude')):
                            model_info["model_provider"] = "anthropic"
                        elif model_id.startswith(('gemini-', 'palm-')):
                            model_info["model_provider"] = "google"
                        elif model_id.startswith(('command-', 'embed-')):
                            model_info["model_provider"] = "cohere"
                        elif model_id.startswith(('mistral-', 'mixtral-')):
                            model_info["model_provider"] = "mistral"
                        else:
                            model_info["model_provider"] = "unknown"
                            
        except Exception as e:
            logger.debug(f"Could not extract model info from agent {self.agent_name}: {e}")
            
        return model_info

    async def _extract_and_parse_json(self, text: str, response_model: Type[OutputType]) -> Optional[OutputType]:
        """
        Extracts a JSON object from a string and parses it into the response model.
        Uses the comprehensive OutputFixingParser with progressive strategies including LLM-based fixing.
        """
        logger.critical("🚀🚀🚀 RUNNING COMPREHENSIVE OUTPUT FIXING PARSER 🚀🚀🚀")
        logger.debug(f"Attempting to parse JSON from raw text (length: {len(text)}) for model {response_model.__name__}")

        try:
            # Import and use the OutputFixingParser from utils
            from .utils import get_global_output_parser
            
            # Get the global parser instance 
            output_parser = get_global_output_parser(max_previous_attempts_in_context=2)
            
            # Use the comprehensive parser with all strategies including LLM fixing
            result = await output_parser.parse(
                text=text,
                response_model=response_model,
                use_llm_fixing=True,  # Enable LLM-based fixing as last resort
                original_error="Failed to parse LLM output with standard JSON parsing"
            )
            
            if result:
                logger.info(f"✅ OutputFixingParser successfully parsed {response_model.__name__}")
                return result
            else:
                logger.error(f"❌ OutputFixingParser failed to parse {response_model.__name__} from text")
                return None
                
        except Exception as e:
            logger.error(f"OutputFixingParser encountered error: {e}")
            logger.error(f"Falling back to None for {response_model.__name__}")
            return None

    # @handle_agent_errors(agent_name_param="self.agent_name", component="llm_adapter") # Removed to avoid circular import
    # @cache_agent_response(ttl_seconds=3600) # Removed to avoid circular import
    async def process(self, node: TaskNode, agent_task_input: InputType, trace_manager: "TraceManager") -> OutputType:
        """
        Processes a TaskNode using the configured AgnoAgent with caching and improved error handling.
        """
        logger.info(f"  Adapter '{self.agent_name}': Processing node {node.task_id} (Goal: '{node.goal[:50]}...')")

        # Determine the stage name based on adapter type
        stage_name = self._get_stage_name(node)
        
        # Log the stage name for debugging
        logger.debug(f"  Adapter '{self.agent_name}': Using stage name '{stage_name}' for node {node.task_id} (status: {node.status})")
        
        # CRITICAL FIX: Don't create new stage, just update existing one
        # The node handlers should already have created the stage
        trace = trace_manager.get_trace_for_node(node.task_id)
        if not trace:
            logger.warning(f"No trace found for node {node.task_id}, creating one")
            trace = trace_manager.create_trace(node.task_id, node.goal)
        
        # Find existing stage or create if not exists
        existing_stage = trace.get_stage(stage_name)
        if not existing_stage:
            logger.info(f"Creating new {stage_name} stage for node {node.task_id}")
            stage = trace_manager.start_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                agent_name=self.agent_name,
                adapter_name=self.__class__.__name__
            )
        else:
            logger.info(f"Updating existing {stage_name} stage for node {node.task_id}")
            stage = existing_stage

        # Capture model information before processing
        model_info = self._get_model_info()

        # Store model info in node's aux_data
        # Initialize aux_data if None
        if node.aux_data is None:
            node.aux_data = {}

        # Initialize execution_details - setdefault doesn't work if value is None
        if "execution_details" not in node.aux_data or node.aux_data["execution_details"] is None:
            node.aux_data["execution_details"] = {}

        node.aux_data["execution_details"]["model_info"] = model_info
        node.aux_data["execution_details"]["processing_started"] = datetime.now().isoformat()

        # Get base system prompt and dynamically inject project-specific folder context
        # Always use the original template to avoid duplication across projects
        base_system_prompt = self._original_system_message or getattr(self.agno_agent, 'system_message', None) or getattr(self.agno_agent, 'system_prompt', None)
        
        # Apply project-specific folder context injection for executor agents
        system_prompt = self._inject_project_context(base_system_prompt)

        try:
            user_message_string = self._prepare_agno_run_arguments(agent_task_input)
            
            # Store the final formatted input for frontend display and tracing
            node.aux_data["execution_details"]["final_llm_input"] = user_message_string
            
            # Build complete LLM messages array
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            llm_messages.append({"role": "user", "content": user_message_string})
            
            # Store the actual system prompt that will be used (including any injections)
            if llm_messages and llm_messages[0]["role"] == "system":
                node.aux_data["execution_details"]["system_prompt"] = llm_messages[0]["content"]
            
            # CRITICAL FIX: Update trace stage with all LLM interaction data
            # Use the actual system prompt that will be sent (including injections)
            actual_system_prompt = llm_messages[0]["content"] if llm_messages and llm_messages[0]["role"] == "system" else system_prompt
            trace_manager.update_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                agent_name=self.agent_name,
                adapter_name=self.__class__.__name__,
                model_info=model_info,
                system_prompt=actual_system_prompt,
                user_input=user_message_string,
                input_context={
                    "agent_task_input": agent_task_input.model_dump(),
                    "formatted_input_length": len(user_message_string),
                    "task_type": str(node.task_type),
                    "node_type": str(node.node_type),
                    "context_items_count": len(agent_task_input.relevant_context_items),
                    "has_dependency_context": any(item.content_type_description == "explicit_dependency_output" for item in agent_task_input.relevant_context_items)
                },
                processing_parameters={
                    "temperature": getattr(self.agno_agent, 'temperature', None),
                    "max_tokens": getattr(self.agno_agent, 'max_tokens', None),
                    "model": getattr(self.agno_agent, 'model', None)
                },
                llm_input_messages=llm_messages,
                llm_input_length=sum(len(msg["content"]) for msg in llm_messages)
            )
            
        except Exception as e:
            trace_manager.complete_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                error=str(e)
            )
            raise AgentExecutionError(
                agent_name=self.agent_name,
                task_id=node.task_id,
                original_error=e,
                attempt_number=1
            )

        # Execute agent with proper response capture
        async def execute_agent():
            # Get stage name in local scope to avoid closure issues
            local_stage_name = self._get_stage_name(node)
            
            if not hasattr(self.agno_agent, 'arun'):
                raise AgentExecutionError(
                    agent_name=self.agent_name,
                    task_id=node.task_id,
                    original_error=NotImplementedError(f"AgnoAgent for '{self.agent_name}' needs an async 'arun' method."),
                    attempt_number=1
                )

            try:
                # Time the LLM call
                llm_start_time = asyncio.get_event_loop().time()
                logger.info(f"🚀 LLM CALL START: {self.agent_name} for node {node.task_id}")
                
                run_response_obj = await self.agno_agent.arun(user_message_string)
                
                llm_end_time = asyncio.get_event_loop().time()
                llm_duration = llm_end_time - llm_start_time
                logger.info(f"✅ LLM CALL COMPLETE: {self.agent_name} for node {node.task_id} - Duration: {llm_duration:.2f}s")
                
                # Store timing in trace
                if trace_manager:
                    trace_manager.update_stage(
                        node_id=node.task_id,
                        stage_name=local_stage_name,
                        llm_call_duration_seconds=llm_duration,
                        llm_call_start_time=llm_start_time,
                        llm_call_end_time=llm_end_time
                    )
                
                actual_content_data = None
                raw_response = None
                
                if hasattr(run_response_obj, 'content'):
                    content_attr = run_response_obj.content
                    
                    if asyncio.iscoroutine(content_attr):
                        actual_content_data = await content_attr
                    else:
                        actual_content_data = content_attr
                        
                    # Store raw response for tracing - NO TRUNCATION for aggregation or execution
                    if local_stage_name in ['aggregation', 'execution']:
                        # For aggregation and execution, store the COMPLETE response - this is what users need to see
                        raw_response = str(actual_content_data)
                        logger.info(f"🔍 {local_stage_name.upper()}: Storing FULL response ({len(raw_response)} characters) for tracing")
                    else:
                        # For other stages (planning, atomization), limit to prevent memory issues
                        full_response = str(actual_content_data)
                        if len(full_response) > 5000:  # Increased from 2000 to 5000 for better debugging
                            raw_response = full_response[:5000] + f"... [Response truncated from {len(full_response)} characters for memory efficiency]"
                            logger.info(f"🔍 {local_stage_name.upper()}: Truncated response from {len(full_response)} to 5000 characters for tracing")
                        else:
                            raw_response = full_response
                            logger.info(f"🔍 {local_stage_name.upper()}: Storing full response ({len(raw_response)} characters) for tracing")
                else:
                    logger.warning(f"Agno agent '{self.agent_name}' RunResponse object has no 'content' attribute for node {node.task_id}.")
                
                # CRITICAL FIX: Update trace stage with LLM response
                if raw_response:
                    trace_manager.update_stage(
                        node_id=node.task_id,
                        stage_name=local_stage_name,
                        llm_response=raw_response
                    )
                
                # Extract tool execution data from AgnoAgent response
                tool_executions_data = []
                
                try:
                    logger.info(f"🔧 TOOL EXTRACTION: Starting tool extraction for node {node.task_id}")
                    
                    if hasattr(run_response_obj, 'tools') and run_response_obj.tools:
                        tools_list = run_response_obj.tools if hasattr(run_response_obj.tools, '__iter__') else []
                        logger.info(f"🔧 TOOL EXTRACTION: Found {len(tools_list)} tools in response")
                        
                        for tool_execution in tools_list:
                            try:
                                
                                # Extract basic tool data
                                tool_data = {
                                    'tool_call_id': getattr(tool_execution, 'tool_call_id', None),
                                    'tool_name': getattr(tool_execution, 'tool_name', None),
                                    'tool_args': getattr(tool_execution, 'tool_args', None),
                                    'result': getattr(tool_execution, 'result', None),
                                    'created_at': getattr(tool_execution, 'created_at', None),
                                    'tool_call_error': getattr(tool_execution, 'tool_call_error', False)
                                }
                                
                                # Handle metrics - but understand that toolkits don't provide LLM token metrics
                                raw_metrics = getattr(tool_execution, 'metrics', None)
                                if raw_metrics:
                                    try:
                                        converted_metrics = self._convert_metrics_to_dict(raw_metrics)
                                        # Only include metrics if they contain meaningful data
                                        if self._has_meaningful_metrics(converted_metrics):
                                            tool_data['metrics'] = converted_metrics
                                            logger.debug(f"📊 METRICS: Tool {tool_data['tool_name']} has LLM metrics")
                                        else:
                                            # Toolkit calls typically don't have token metrics - this is normal
                                            tool_data['metrics'] = None
                                            logger.debug(f"📊 METRICS: Tool {tool_data['tool_name']} has no token metrics (normal for API calls)")
                                    except Exception as e:
                                        tool_data['metrics'] = None
                                        logger.debug(f"📊 METRICS: Tool {tool_data['tool_name']} metrics conversion failed: {e}")
                                else:
                                    tool_data['metrics'] = None
                                    logger.debug(f"📊 METRICS: Tool {tool_data['tool_name']} has no raw metrics (normal for toolkit calls)")
                                
                                # Enhanced: Extract additional execution context
                                tool_data.update({
                                    'requires_confirmation': getattr(tool_execution, 'requires_confirmation', None),
                                    'confirmed': getattr(tool_execution, 'confirmed', None),
                                    'requires_user_input': getattr(tool_execution, 'requires_user_input', None),
                                    'external_execution_required': getattr(tool_execution, 'external_execution_required', None),
                                    'stop_after_tool_call': getattr(tool_execution, 'stop_after_tool_call', False)
                                })
                                
                                # CRITICAL: Extract timing fields if available (enhanced)
                                timing_fields = [
                                    'execution_duration_ms', 'start_time', 'end_time', 'processing_time',
                                    'response_time', 'execution_time', 'duration_ms', 'time_elapsed',
                                    'call_duration', 'call_time', 'run_time'
                                ]
                                found_timing = {}
                                for field in timing_fields:
                                    value = getattr(tool_execution, field, None)
                                    if value is not None:
                                        tool_data[field] = value
                                        found_timing[field] = value
                                
                                # Don't use LLM duration for individual tools - this is incorrect
                                # Tool calls (especially API calls) should have their own timing or reasonable estimates
                                if 'execution_duration_ms' not in tool_data or tool_data['execution_duration_ms'] is None:
                                    # Set realistic timing estimates based on tool type instead of using full LLM duration
                                    tool_name_lower = tool_data['tool_name'].lower() if tool_data['tool_name'] else ''
                                    
                                    if any(api_pattern in tool_name_lower for api_pattern in [
                                        'get_current_price', 'get_order_book', 'get_klines', 'get_coin_price', 
                                        'get_token_holders', 'get_protocols', 'get_transfers', 'get_coin_info'
                                    ]):
                                        # API calls typically take 1-3 seconds
                                        tool_data['execution_duration_ms'] = 2000
                                        found_timing['execution_duration_ms'] = tool_data['execution_duration_ms']
                                        logger.debug(f"⏱️ TIMING: Estimated API call duration for {tool_data['tool_name']}: 2000ms")
                                    elif 'python' in tool_name_lower or 'code' in tool_name_lower:
                                        # Code execution can vary, estimate 3-5 seconds
                                        tool_data['execution_duration_ms'] = 4000  
                                        found_timing['execution_duration_ms'] = tool_data['execution_duration_ms']
                                        logger.debug(f"⏱️ TIMING: Estimated code execution duration for {tool_data['tool_name']}: 4000ms")
                                    else:
                                        # Other tools - generic estimate
                                        tool_data['execution_duration_ms'] = 1500
                                        found_timing['execution_duration_ms'] = tool_data['execution_duration_ms']
                                        logger.debug(f"⏱️ TIMING: Estimated generic tool duration for {tool_data['tool_name']}: 1500ms")
                                
                                if found_timing:
                                    # Safe debug logging with string length limit
                                    timing_str = str(found_timing)[:200]
                                    logger.info(f"⏱️ TIMING: Tool {tool_data['tool_name']} timing data: {timing_str}")
                                else:
                                    logger.warning(f"⏱️ TIMING: Tool {tool_data['tool_name']} has no timing data")
                                
                                # Process metrics if available (simplified approach)
                                self._process_tool_metrics(tool_data)
                                
                                # Enhanced: Extract toolkit information from tool result and raw tool_execution
                                toolkit_info = self._extract_toolkit_info_from_result(tool_data['result'], tool_data['tool_name'])
                                
                                # BACKUP: If extraction failed (no custom toolkit info found), try backup methods
                                has_custom_toolkit_info = (
                                    toolkit_info.get('toolkit_name') or 
                                    (toolkit_info.get('toolkit_category') and toolkit_info.get('toolkit_category') not in ['general', 'unknown'])
                                )
                                if not has_custom_toolkit_info:
                                    backup_toolkit_info = self._extract_toolkit_info_from_tool_execution(tool_execution, tool_data['tool_name'])
                                    if backup_toolkit_info:
                                        toolkit_info.update(backup_toolkit_info)
                                
                                tool_data.update(toolkit_info)
                                
                                # Enhanced: Result size and truncation information
                                if tool_data['result'] is not None:
                                    if not isinstance(tool_data['result'], str):
                                        tool_data['result'] = str(tool_data['result'])
                                    
                                    result_length = len(tool_data['result'])
                                    tool_data['result_size_bytes'] = result_length
                                    
                                    # Truncate very large results but keep metadata
                                    if result_length > 10000:
                                        tool_data['result_truncated'] = True
                                        tool_data['result_full_size'] = result_length
                                        tool_data['result'] = tool_data['result'][:10000] + f"\n\n[... truncated {result_length - 10000} characters]"
                                    else:
                                        tool_data['result_truncated'] = False
                                
                                # Enhanced: Add timing context if available
                                if tool_data['created_at']:
                                    # Ensure timestamp is in milliseconds
                                    if tool_data['created_at'] < 1e12:  # If in seconds, convert to milliseconds
                                        tool_data['created_at'] = int(tool_data['created_at'] * 1000)
                                    else:
                                        tool_data['created_at'] = int(tool_data['created_at'])
                                
                                # Validate essential fields before adding
                                if tool_data['tool_name']:
                                    tool_executions_data.append(tool_data)
                                else:
                                    logger.warning(f"Skipping tool execution with missing tool_name: {tool_data}")
                                    
                            except Exception as e:
                                logger.error(f"Error processing individual tool execution for node {node.task_id}: {e}")
                                continue
                                
                except Exception as e:
                    logger.error(f"Error extracting tool execution data for node {node.task_id}: {e}")

                # Store tool execution data in node and trace
                if tool_executions_data:
                    node.aux_data["execution_details"]["tool_calls"] = tool_executions_data
                    logger.info(f"🔧 Captured {len(tool_executions_data)} tool calls for node {node.task_id}")
                    
                    # Update trace with tool call data
                    if trace_manager:
                        trace_manager.update_stage(
                            node_id=node.task_id,
                            stage_name=local_stage_name,
                            tool_calls=tool_executions_data,
                            tool_execution_count=len(tool_executions_data)
                        )
                else:
                    logger.warning(f"🔧 TOOL EXTRACTION: No tool calls found in response for node {node.task_id}")
                
                # Handle structured output parsing if needed
                if self.agno_agent.response_model and isinstance(actual_content_data, str):
                    parsed_data = self._extract_and_parse_json(actual_content_data, self.agno_agent.response_model)
                    if parsed_data:
                        actual_content_data = parsed_data

                logger.info(f"Adapter '{self.agent_name}': Successfully processed. Type of actual_content_data: {type(actual_content_data)}")
                return actual_content_data
                
            except Exception as e:
                # Handle specific error types
                if "rate limit" in str(e).lower() or "429" in str(e):
                    raise AgentRateLimitError(agent_name=self.agent_name)
                elif "timeout" in str(e).lower():
                    raise AgentTimeoutError(agent_name=self.agent_name, task_id=node.task_id, timeout_seconds=30.0)
                else:
                    raise AgentExecutionError(agent_name=self.agent_name, task_id=node.task_id, original_error=e, attempt_number=1)

        try:
            # Lazy import to avoid circular import
            from sentientresearchagent.core.error_handler import ErrorRecovery
            result = await ErrorRecovery.retry_with_backoff(
                func=execute_agent,
                max_retries=3,
                base_delay=2.0,
                exceptions=(AgentRateLimitError, AgentTimeoutError, AgentExecutionError)
            )
            
            # Update execution details with completion info
            node.aux_data["execution_details"]["processing_completed"] = datetime.now().isoformat()
            node.aux_data["execution_details"]["success"] = True
            
            # CRITICAL FIX: Complete tracing stage with rich output data - NO TRUNCATION for aggregation or execution
            stage_name = self._get_stage_name(node)
            if stage_name in ['aggregation', 'execution']:
                # For aggregation and execution, store the COMPLETE result - this is what users need
                output_data = str(result) if result else "No output"
                logger.info(f"🔍 {stage_name.upper()}: Storing COMPLETE output data ({len(output_data)} characters) for tracing")
            else:
                # For other stages (planning, atomization), use reasonable summary
                if result:
                    full_output = str(result)
                    if len(full_output) > 2000:  # Reasonable limit for non-execution stages
                        output_data = full_output[:2000] + f"... [Output truncated from {len(full_output)} characters]"
                    else:
                        output_data = full_output
                else:
                    output_data = "No output"
                logger.info(f"🔍 {stage_name.upper()}: Storing output data ({len(output_data)} characters) for tracing")

            trace_manager.complete_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                output_data=output_data
            )
            
            return result
            
        except Exception as e:
            # Update execution details with error info
            node.aux_data["execution_details"]["processing_completed"] = datetime.now().isoformat()
            node.aux_data["execution_details"]["success"] = False
            node.aux_data["execution_details"]["error"] = str(e)
            
            # Complete tracing stage with error
            trace_manager.complete_stage(
                node_id=node.task_id,
                stage_name=stage_name,
                error=str(e)
            )
            
            raise

    def _get_stage_name(self, node: Optional[TaskNode] = None) -> str:
        """
        Determine the stage name based on adapter type AND node status.
        
        Args:
            node: Optional TaskNode to consider for status-based stage determination
        """
        class_name = self.__class__.__name__.lower()
        
        # CRITICAL FIX: Consider node status when determining stage
        if node and hasattr(node, 'status'):
            from sentientresearchagent.hierarchical_agent_framework.types import TaskStatus
            
            # If node is AGGREGATING, it should be aggregation stage regardless of adapter
            if node.status == TaskStatus.AGGREGATING:
                return 'aggregation'
            
            # If node is NOT aggregating but adapter is an aggregator, this is wrong
            if 'aggregator' in class_name and node.status in [TaskStatus.READY, TaskStatus.RUNNING]:
                logger.warning(
                    f"🚨 ADAPTER MISMATCH: Node {node.task_id} (status: {node.status}) "
                    f"is using aggregator adapter '{self.__class__.__name__}' but not in AGGREGATING status!"
                )
                # Force to execution stage to prevent confusion
                return 'execution'
        
        # Default behavior based on adapter type
        if 'planner' in class_name:
            return 'planning'
        elif 'executor' in class_name:
            return 'execution'
        elif 'aggregator' in class_name:
            return 'aggregation'
        elif 'atomizer' in class_name:
            return 'atomization'
        elif 'customsearch' in class_name or 'search' in class_name:
            # EXPLICIT: All search adapters should NEVER do aggregation
            return 'execution'
        else:
            # Default to processing, but log a warning
            logger.warning(f"🚨 Unknown adapter type '{self.__class__.__name__}' - defaulting to 'processing' stage")
            return 'processing'

    def _extract_toolkit_info_from_result(self, result: Any, tool_name: str) -> dict:
        """Extract toolkit information from tool execution result.
        
        Args:
            result: Tool execution result data
            tool_name: Name of the executed tool
            
        Returns:
            dict: Toolkit information including name, category, type, and icon
        """
        toolkit_info = {
            'toolkit_name': None,
            'toolkit_category': 'general',
            'toolkit_type': 'agno',
            'toolkit_icon': '🔧'
        }
        
        # Try to extract from result first
        if result:
            extracted_info = self._parse_toolkit_info_from_result(result)
            if extracted_info:
                toolkit_info.update(extracted_info)
                return toolkit_info
        
        # Fallback to simple tool name patterns
        fallback_info = self._get_fallback_toolkit_info(tool_name)
        toolkit_info.update(fallback_info)
        
        return toolkit_info

    def _parse_toolkit_info_from_result(self, result: Any) -> dict:
        """Parse toolkit information from tool result data.
        
        Args:
            result: Tool execution result
            
        Returns:
            dict: Parsed toolkit info or None if not found
        """
        try:
            import json
            result_data = None
            
            # Handle different result formats
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                except json.JSONDecodeError as e:
                    return None
            elif isinstance(result, dict):
                result_data = result
            else:
                return None
            
            # Extract toolkit information if available
            if isinstance(result_data, dict):
                toolkit_fields = ['toolkit_name', 'toolkit_category', 'toolkit_type', 'toolkit_icon']
                
                if any(field in result_data for field in toolkit_fields):
                    extracted = {
                        'toolkit_name': result_data.get('toolkit_name'),
                        'toolkit_category': result_data.get('toolkit_category', 'custom'),
                        'toolkit_type': result_data.get('toolkit_type', 'custom'),
                        'toolkit_icon': result_data.get('toolkit_icon', '🛠️')
                    }
                    return extracted
                    
        except Exception as e:
            logger.debug(f"Could not parse toolkit info from result: {e}")
            
        return None

    def _get_fallback_toolkit_info(self, tool_name: str) -> dict:
        """Get fallback toolkit information by dynamically inspecting toolkit classes.
        This replaces manual pattern matching with actual toolkit method inspection.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            dict: Fallback toolkit information
        """
        if not tool_name:
            return {
                'toolkit_name': 'Unknown',
                'toolkit_category': 'general',
                'toolkit_type': 'unknown',
                'toolkit_icon': '❓'
            }
        
        # Try to dynamically match tool to toolkit by inspecting actual toolkit classes
        toolkit_match = self._find_toolkit_by_method(tool_name)
        if toolkit_match:
            return toolkit_match
        
        # Fallback to Agno built-in toolkit patterns (these don't have importable classes)
        tool_lower = tool_name.lower()
        
        if tool_lower == 'run_python_code' or 'e2b' in tool_lower:
            return {
                'toolkit_name': 'E2BTools',
                'toolkit_category': 'compute',
                'toolkit_type': 'agno',
                'toolkit_icon': '⚡'
            }
        elif 'python' in tool_lower or 'execute_python' in tool_lower:
            return {
                'toolkit_name': 'PythonTools',
                'toolkit_category': 'compute',
                'toolkit_type': 'agno',
                'toolkit_icon': '🐍'
            }
        elif any(pattern in tool_lower for pattern in ['search', 'google', 'duckduckgo', 'wikipedia']):
            return {
                'toolkit_name': 'SearchTools',
                'toolkit_category': 'search',
                'toolkit_type': 'agno',
                'toolkit_icon': '🔍'
            }
        elif any(pattern in tool_lower for pattern in ['scrape', 'crawl', 'fetch', 'web', 'http']):
            return {
                'toolkit_name': 'WebTools',
                'toolkit_category': 'web',
                'toolkit_type': 'agno',
                'toolkit_icon': '🌐'
            }
        elif any(pattern in tool_lower for pattern in ['file', 'read_file', 'write_file']):
            return {
                'toolkit_name': 'FileTools',
                'toolkit_category': 'local',
                'toolkit_type': 'agno',
                'toolkit_icon': '📁'
            }
        elif any(pattern in tool_lower for pattern in ['reason', 'think', 'analyze']):
            return {
                'toolkit_name': 'ReasoningTools',
                'toolkit_category': 'reasoning',
                'toolkit_type': 'agno', 
                'toolkit_icon': '🧠'
            }
        elif any(pattern in tool_lower for pattern in ['email', 'mail', 'smtp']):
            return {
                'toolkit_name': 'EmailTools',
                'toolkit_category': 'communication',
                'toolkit_type': 'agno',
                'toolkit_icon': '📧'
            }
        
        # Generic fallback
        return {
            'toolkit_name': 'GeneralTools',
            'toolkit_category': 'general',
            'toolkit_type': 'agno',
            'toolkit_icon': '🔧'
        }
    
    def _extract_toolkit_info_from_tool_execution(self, tool_execution: Any, tool_name: str) -> dict:
        """Backup method to extract toolkit info from raw tool_execution object.
        
        Args:
            tool_execution: Raw tool execution object from AgnoAgent
            tool_name: Name of the executed tool
            
        Returns:
            dict: Toolkit information if found, empty dict otherwise
        """
        try:
            # Check if tool_execution has any attributes that might contain the raw response
            raw_response_attrs = ['raw_result', 'original_result', 'full_result', 'response', 'raw_response', 'output']
            
            for attr_name in raw_response_attrs:
                if hasattr(tool_execution, attr_name):
                    raw_attr = getattr(tool_execution, attr_name)
                    if raw_attr:
                        extracted_info = self._parse_toolkit_info_from_result(raw_attr)
                        if extracted_info:
                            return extracted_info
            
            # Standardized result processing: normalize to dict format
            result = getattr(tool_execution, 'result', None)
            if result is not None:
                # Standardize: convert any result format to dictionary
                standardized_result = self._standardize_result_to_dict(result)
                
                if standardized_result:
                    extracted_info = self._parse_toolkit_info_from_result(standardized_result)
                    if extracted_info:
                        return extracted_info
            
            return {}
            
        except Exception as e:
            logger.debug(f"Backup toolkit extraction failed for {tool_name}: {e}")
            return {}
    
    def _standardize_result_to_dict(self, result: Any) -> dict:
        """Standardize any result format to a dictionary for consistent processing.
        
        Args:
            result: Raw result in any format (dict, str, etc.)
            
        Returns:
            dict: Standardized dictionary or empty dict if conversion fails
        """
        try:
            # Already a dictionary - use as-is
            if isinstance(result, dict):
                return result
            
            # String - try multiple parsing approaches
            if isinstance(result, str) and len(result.strip()) > 0:
                stripped = result.strip()
                if (stripped.startswith('{') and stripped.endswith('}')) or \
                   (stripped.startswith('[') and stripped.endswith(']')):
                    
                    # Method 1: Try JSON parsing first
                    try:
                        import json
                        parsed = json.loads(stripped)
                        return parsed if isinstance(parsed, dict) else {}
                    except (json.JSONDecodeError, TypeError):
                        pass
                    
                    # Method 2: Try eval for Python dict strings (with safety)
                    try:
                        # Only eval if it looks like a safe dict string
                        if stripped.startswith('{') and 'import' not in stripped and 'exec' not in stripped:
                            parsed = eval(stripped)
                            return parsed if isinstance(parsed, dict) else {}
                    except (SyntaxError, NameError, TypeError):
                        pass
            
            # Other types - cannot standardize to dict
            return {}
            
        except Exception:
            return {}


    def _find_toolkit_by_method(self, tool_name: str) -> dict:
        """
        Find toolkit information by matching tool method name to available toolkits.
        
        Args:
            tool_name: Name of the tool method
            
        Returns:
            dict: Toolkit information if found, None otherwise
        """
        if not tool_name or not hasattr(self, 'agno_agent'):
            return None
            
        try:
            # Check if agno_agent has tools and inspect them
            if hasattr(self.agno_agent, 'tools') and self.agno_agent.tools:
                for tool in self.agno_agent.tools:
                    # Check if this tool has the method we're looking for
                    if hasattr(tool, tool_name):
                        # Try to get toolkit metadata from the tool class
                        tool_class = type(tool)
                        toolkit_name = getattr(tool_class, '_toolkit_name', None) or getattr(tool, '_toolkit_name', None)
                        toolkit_category = getattr(tool_class, '_toolkit_category', None) or getattr(tool, '_toolkit_category', None)
                        toolkit_icon = getattr(tool_class, '_toolkit_icon', None) or getattr(tool, '_toolkit_icon', None)
                        
                        if toolkit_name:
                            return {
                                'toolkit_name': toolkit_name,
                                'toolkit_category': toolkit_category or 'custom',
                                'toolkit_icon': toolkit_icon or '🔧'
                            }
                        
                        # Fallback: derive from class name
                        class_name = tool_class.__name__
                        if 'Toolkit' in class_name:
                            return {
                                'toolkit_name': class_name,
                                'toolkit_category': 'custom',
                                'toolkit_icon': '🔧'
                            }
                            
        except Exception as e:
            logger.debug(f"Error in _find_toolkit_by_method for {tool_name}: {e}")
            
        return None

    def _convert_metrics_to_dict(self, metrics_obj) -> dict:
        """
        Convert MessageMetrics or any Pydantic object to JSON-serializable dictionary.
        Enhanced to handle Agno-specific metrics structure.
        
        Args:
            metrics_obj: MessageMetrics object or similar Pydantic model
            
        Returns:
            JSON-serializable dictionary with proper token and timing fields
        """
        try:
            logger.debug(f"🔍 METRICS CONVERSION: Processing metrics object of type: {type(metrics_obj)}")
            
            result_dict = {}
            
            # Handle Pydantic BaseModel objects (Agno uses these)
            from pydantic import BaseModel
            if isinstance(metrics_obj, BaseModel):
                # Use model_dump for Pydantic v2 (preferred method)
                if hasattr(metrics_obj, 'model_dump'):
                    try:
                        result_dict = metrics_obj.model_dump()
                        logger.debug(f"🔍 METRICS: Extracted via model_dump(): {list(result_dict.keys())}")
                    except Exception as e:
                        logger.warning(f"model_dump() failed: {e}, trying mode='python'")
                        result_dict = metrics_obj.model_dump(mode='python')
                # Fallback for Pydantic v1 - try model_dump first, then dict as last resort
                elif hasattr(metrics_obj, 'model_dump'):
                    try:
                        result_dict = metrics_obj.model_dump()
                        logger.debug(f"🔍 METRICS: Extracted via fallback model_dump(): {list(result_dict.keys())}")
                    except Exception:
                        # Last resort for very old Pydantic versions
                        result_dict = dict(metrics_obj) if hasattr(metrics_obj, '__iter__') else {}
                        logger.debug(f"🔍 METRICS: Used dict conversion as last resort")
                elif hasattr(metrics_obj, '__dict__'):
                    result_dict = metrics_obj.__dict__.copy()
                    logger.debug(f"🔍 METRICS: Extracted via __dict__: {list(result_dict.keys())}")
                else:
                    # Extract attributes manually
                    result_dict = self._extract_metrics_attributes(metrics_obj)
            
            # Handle dictionaries (already converted)
            elif isinstance(metrics_obj, dict):
                result_dict = metrics_obj.copy()
                logger.debug(f"🔍 METRICS: Already dict: {list(result_dict.keys())}")
            
            # Handle other objects by attribute extraction
            else:
                logger.debug(f"🔍 METRICS: Non-Pydantic object, extracting attributes from {type(metrics_obj)}")
                result_dict = self._extract_metrics_attributes(metrics_obj)
            
            # Enhance the result with normalized field names for consistency
            enhanced_dict = self._normalize_metrics_fields(result_dict)
            
            # Log the final result for debugging
            if enhanced_dict:
                logger.info(f"📊 METRICS EXTRACTED: tokens={enhanced_dict.get('total_tokens', 0)}, "
                           f"input={enhanced_dict.get('input_tokens', 0)}, "
                           f"output={enhanced_dict.get('output_tokens', 0)}, "
                           f"cached={enhanced_dict.get('cached_tokens', 0)}")
            
            return enhanced_dict
                
        except Exception as e:
            logger.error(f"Failed to convert metrics to dict: {e}")
            return {"conversion_error": str(e), "raw_type": str(type(metrics_obj))}

    def _extract_metrics_attributes(self, metrics_obj) -> dict:
        """Extract metrics attributes from any object using reflection."""
        result = {}
        
        # Common metric field names to look for
        metric_fields = [
            'input_tokens', 'output_tokens', 'total_tokens', 'cached_tokens',
            'prompt_tokens', 'completion_tokens', 'cache_write_tokens',
            'reasoning_tokens', 'audio_tokens', 'input_audio_tokens', 'output_audio_tokens',
            'time_to_first_token', 'execution_duration_ms', 'processing_time'
        ]
        
        for field in metric_fields:
            if hasattr(metrics_obj, field):
                value = getattr(metrics_obj, field, None)
                if value is not None:
                    result[field] = value
        
        # Also check __dict__ for any additional fields
        if hasattr(metrics_obj, '__dict__'):
            for key, value in metrics_obj.__dict__.items():
                if 'token' in key.lower() or 'time' in key.lower() or 'duration' in key.lower():
                    result[key] = value
        
        logger.debug(f"🔍 METRICS ATTRIBUTES: Extracted {len(result)} fields: {list(result.keys())}")
        return result
    
    def _has_meaningful_metrics(self, metrics_dict: dict) -> bool:
        """Check if metrics contain meaningful data (non-zero tokens or timing)."""
        if not metrics_dict or not isinstance(metrics_dict, dict):
            return False
        
        # Check for any non-zero token counts
        token_fields = ['input_tokens', 'output_tokens', 'total_tokens', 'cached_tokens']
        has_tokens = any(metrics_dict.get(field, 0) > 0 for field in token_fields)
        
        # Check for timing data
        timing_fields = ['time_to_first_token', 'execution_duration_ms', 'processing_time']
        has_timing = any(metrics_dict.get(field, 0) > 0 for field in timing_fields)
        
        return has_tokens or has_timing

    def _normalize_metrics_fields(self, metrics_dict: dict) -> dict:
        """Normalize metrics field names to ensure consistency."""
        if not metrics_dict:
            return metrics_dict
        
        normalized = metrics_dict.copy()
        
        # Map various field name variations to standard names
        field_mappings = {
            # Token counts
            'prompt_tokens': 'input_tokens',
            'completion_tokens': 'output_tokens',
            
            # Time fields (convert to milliseconds if needed)
            'time_to_first_token': 'time_to_first_token_ms',
            'processing_time': 'execution_duration_ms',
            'duration': 'execution_duration_ms',
        }
        
        for old_key, new_key in field_mappings.items():
            if old_key in normalized and new_key not in normalized:
                normalized[new_key] = normalized[old_key]
        
        # Ensure total_tokens is calculated if not present
        if 'total_tokens' not in normalized:
            input_tokens = normalized.get('input_tokens', 0) or 0
            output_tokens = normalized.get('output_tokens', 0) or 0
            cached_tokens = normalized.get('cached_tokens', 0) or 0
            
            if input_tokens + output_tokens > 0:
                normalized['total_tokens'] = input_tokens + output_tokens + cached_tokens
        
        # Convert time fields to milliseconds if they're in seconds
        time_fields = ['time_to_first_token', 'execution_duration_ms']
        for field in time_fields:
            if field in normalized and normalized[field] is not None:
                value = normalized[field]
                # If value is very small (< 100), assume it's in seconds, convert to ms
                if isinstance(value, (int, float)) and 0 < value < 100:
                    normalized[field] = value * 1000
        
        logger.debug(f"🔍 METRICS NORMALIZED: {len(normalized)} fields ready for frontend")
        return normalized

    def _process_tool_metrics(self, tool_data: dict):
        """
        Process tool metrics with comprehensive approach.
        Extracts timing, token usage, and performance metrics from converted MessageMetrics.
        
        Args:
            tool_data: Tool data dictionary to update with metrics
        """
        try:
            # Process execution duration if available
            duration_ms = None
            for field in ['execution_duration_ms', 'duration_ms', 'processing_time', 'execution_time']:
                if field in tool_data and tool_data[field] is not None:
                    duration_ms = tool_data[field]
                    break
            
            if duration_ms is not None:
                tool_data['execution_duration_ms'] = duration_ms
            
            # CRITICAL: Calculate performance metrics from MessageMetrics data
            metrics_dict = tool_data.get('metrics', {})
            if isinstance(metrics_dict, dict) and metrics_dict:                
                # Calculate tokens per second if we have both tokens and timing
                if duration_ms and duration_ms > 0:
                    output_tokens = metrics_dict.get('output_tokens', 0)
                    if output_tokens > 0:
                        tokens_per_sec = (output_tokens / duration_ms) * 1000
                        tool_data['tokens_per_second'] = round(tokens_per_sec, 2)
                
                # Calculate cache efficiency
                total_tokens = metrics_dict.get('total_tokens', 0)
                cached_tokens = metrics_dict.get('cached_tokens', 0)
                if total_tokens > 0:
                    cache_efficiency = (cached_tokens / total_tokens) * 100
                    tool_data['cache_efficiency_percent'] = round(cache_efficiency, 1)
            
            # Add processing timestamp
            import time
            tool_data['processed_at'] = int(time.time())
            
        except Exception as e:
            logger.debug(f"Failed to process tool metrics: {e}")

    def _inject_project_context(self, base_system_prompt: str) -> str:
        """
        Dynamically inject project-specific folder context into system prompt.
        
        This ensures that executor agents get the current project's folder structure
        even though agents are created globally before any project is active.
        Each project gets fresh folder context without duplication.
        
        Args:
            base_system_prompt: Original system prompt template from agent
            
        Returns:
            System prompt with project folder context injected (if applicable)
        """
        if not base_system_prompt:
            return base_system_prompt
            
        # Only inject for executor agents when a project is active
        # Check if this is an ExecutorAdapter instance rather than checking agent name
        is_executor = self.__class__.__name__ == "ExecutorAdapter" or any(
            cls.__name__ == "ExecutorAdapter" for cls in self.__class__.__mro__
        )
        
        from sentientresearchagent.core.project_context import is_project_context_set
        if is_executor and is_project_context_set():
            try:
                # Import the folder context function
                from ..agents.prompts import get_project_folder_context
                folder_context = get_project_folder_context()
                
                if folder_context:
                    # Always create fresh injected prompt from original template
                    # This prevents accumulation of folder contexts from different projects
                    injected_prompt = base_system_prompt + f"\n\n{folder_context}"
                    
                    # DON'T modify shared agent state to avoid thread safety issues
                    # Instead, the injected prompt will be stored in execution details
                    # and used in the LLM messages array
                    
                    from sentientresearchagent.core.project_context import get_project_context
                    project_id = get_project_context()
                    logger.debug(f"📁 Injected folder context for {self.agent_name} (Project: {project_id})")
                    return injected_prompt
                        
            except ImportError as e:
                logger.warning(f"Could not import folder context function: {e}")
            except Exception as e:
                logger.warning(f"Failed to inject folder context for {self.agent_name}: {e}")
        
        return base_system_prompt

    def close(self):
        """Closes the underlying Agno agent's resources."""
        if hasattr(self.agno_agent, 'close') and callable(self.agno_agent.close):
            logger.info(f"  Adapter '{self.agent_name}': Closing underlying Agno agent.")
            self.agno_agent.close()