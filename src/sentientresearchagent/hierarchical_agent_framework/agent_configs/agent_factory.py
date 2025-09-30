"""
Agent Factory

Creates agent instances from YAML configuration with comprehensive Pydantic validation.
Leverages structured Pydantic models for type safety and validation.
"""

import importlib
import os
from typing import Dict, Any, Optional, List, Union, Type
from loguru import logger
from pathlib import Path

try:
    from omegaconf import DictConfig
except ImportError:
    logger.error("OmegaConf not installed. Please install with: pip install omegaconf>=2.3.0")
    raise

try:
    from agno.agent import Agent as AgnoAgent
    from agno.models.litellm import LiteLLM
    from agno.models.openai import OpenAIChat
    # Import agno.tools module for dynamic tool discovery
    import agno.tools
except ImportError as e:
    logger.error(f"Agno dependencies not available: {e}")
    raise

# Try to import WikipediaTools, but don't fail if wikipedia package is missing
try:
    from agno.tools.wikipedia import WikipediaTools
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    logger.warning("WikipediaTools not available (missing wikipedia package)")
    WikipediaTools = None
    WIKIPEDIA_AVAILABLE = False

from ..agents.adapters import (
    PlannerAdapter, ExecutorAdapter, AtomizerAdapter, 
    AggregatorAdapter, PlanModifierAdapter
)
from ..agents.definitions.custom_searchers import OpenAICustomSearchAdapter, GeminiCustomSearchAdapter
from ..agents.definitions.exa_searcher import ExaCustomSearchAdapter
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import (
    PlanOutput, AtomizerOutput, WebSearchResultsOutput, 
    CustomSearcherOutput, PlanModifierInput
)
from ..types import TaskType
from sentientresearchagent.hierarchical_agent_framework.agents.base_adapter import BaseAdapter
from sentientresearchagent.hierarchical_agent_framework.agents.registry import AgentRegistry
from sentientresearchagent.hierarchical_agent_framework.agent_blueprints import AgentBlueprint
from sentientresearchagent.hierarchical_agent_framework.toolkits.data import BinanceToolkit, CoinGeckoToolkit, ArkhamToolkit, DefiLlamaToolkit
from .models import (
    AgentConfig, ModelConfig, ToolConfig, ToolkitConfig, 
    validate_agent_config, validate_toolkit_config
)

try:
    from dotenv import load_dotenv
    # Load .env file at module level to ensure environment variables are available
    load_dotenv()
    logger.debug("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed. Environment variables from .env files will not be loaded automatically.")

# Environment validation is now handled by Pydantic ModelConfig validation


class AgentFactory:
    """Factory for creating agent instances from configuration with structured output support."""
    
    def __init__(self, config_loader):
        """
        Initialize the agent factory.
        
        Args:
            config_loader: AgentConfigLoader instance for resolving prompts
        """
        self.config_loader = config_loader
        self._adapter_classes = {
            "PlannerAdapter": PlannerAdapter,
            "ExecutorAdapter": ExecutorAdapter,
            "AtomizerAdapter": AtomizerAdapter,
            "AggregatorAdapter": AggregatorAdapter,
            "PlanModifierAdapter": PlanModifierAdapter,
            "OpenAICustomSearchAdapter": OpenAICustomSearchAdapter,
            "GeminiCustomSearchAdapter": GeminiCustomSearchAdapter,
            "ExaCustomSearchAdapter": ExaCustomSearchAdapter,
        }
        
        # Enhanced response models mapping
        self._response_models = {
            "PlanOutput": PlanOutput,
            "AtomizerOutput": AtomizerOutput,
            "WebSearchResultsOutput": WebSearchResultsOutput,
            "CustomSearcherOutput": CustomSearcherOutput,
            # Add more as needed
        }
        
        # Custom toolkits (our own implementations)
        self._toolkits = {
            "BinanceToolkit": BinanceToolkit,
            "CoingeckoToolkit": CoinGeckoToolkit,
            "ArkhamToolkit": ArkhamToolkit,
            "DefiLlamaToolkit": DefiLlamaToolkit,
        }

        # Initialize tools mapping for individual tools (not toolkits)
        self._tools = {}
        self._initialize_common_tools()
        
        # Model providers mapping
        self._model_providers = {
            "litellm": LiteLLM,
            "openai": OpenAIChat,
        }
                
        # Log available toolkits for visibility
        custom_toolkits = list(self._toolkits.keys())
        logger.info(f"📦 Available custom toolkits: {custom_toolkits}")
    
    def _initialize_common_tools(self) -> None:
        """Initialize common tools mapping for individual tool access."""
        try:
            # Import common tools from agno.tools
            from agno.tools.python import PythonTools
            from agno.tools.e2b import E2BTools
            from agno.tools.reasoning import ReasoningTools
            
            self._tools.update({
                "PythonTools": PythonTools,
                "E2BTools": E2BTools,
                "ReasoningTools": ReasoningTools,
            })
            
            # Optional tools with graceful degradation
            try:
                from agno.tools.duckduckgo import DuckDuckGoTools
                self._tools["DuckDuckGoTools"] = DuckDuckGoTools
            except ImportError as e:
                logger.warning(f"DuckDuckGoTools not available: {e}")
            
            # Add WikipediaTools if available
            if WIKIPEDIA_AVAILABLE and WikipediaTools:
                self._tools["WikipediaTools"] = WikipediaTools
                
            logger.info(f"Initialized {len(self._tools)} common tools: {list(self._tools.keys())}")
            
        except ImportError as e:
            logger.warning(f"Could not initialize some common tools: {e}")
    
    def resolve_response_model(self, response_model_name: str) -> Optional[Type]:
        """
        Resolve a response model name to the actual Pydantic model class.
        
        Args:
            response_model_name: Name of the response model
            
        Returns:
            Pydantic model class or None
        """
        if not response_model_name:
            return None
            
        if response_model_name in self._response_models:
            return self._response_models[response_model_name]
        
        # Try to import dynamically if not in our mapping
        try:
            # Try importing from agent_io_models
            module = importlib.import_module(
                "sentientresearchagent.hierarchical_agent_framework.context.agent_io_models"
            )
            if hasattr(module, response_model_name):
                model_class = getattr(module, response_model_name)
                self._response_models[response_model_name] = model_class
                return model_class
        except ImportError:
            pass
        
        logger.warning(f"Unknown response model: {response_model_name}")
        return None
    
    def create_model_instance(self, model_config: Union[DictConfig, Dict[str, Any], ModelConfig]) -> Union[LiteLLM, OpenAIChat]:
        """
        Create a model instance from configuration with Pydantic validation.
        
        Args:
            model_config: Model configuration (DictConfig, dict, or ModelConfig)
            
        Returns:
            Model instance
            
        Raises:
            ValueError: If configuration is invalid or required API keys are missing
        """
        # Convert to Pydantic ModelConfig for validation
        if isinstance(model_config, ModelConfig):
            validated_config = model_config
        else:
            # Convert DictConfig or dict to dict
            if hasattr(model_config, '__getitem__'):
                config_dict = dict(model_config)
            else:
                config_dict = model_config
                
            # Validate using Pydantic model (includes environment validation)
            try:
                validated_config = ModelConfig(**config_dict)
                logger.debug(f"✅ Model configuration validated: {validated_config.provider}/{validated_config.model_id}")
            except Exception as e:
                logger.error(f"Model configuration validation failed: {e}")
                raise ValueError(f"Invalid model configuration: {e}") from e
        
        provider = validated_config.provider
        model_id = validated_config.model_id
        lower_model_id = model_id.lower()
        
        if provider not in self._model_providers:
            raise ValueError(f"Unsupported model provider: {provider}. Available: {list(self._model_providers.keys())}")
        
        model_class = self._model_providers[provider]
        
        # Extract model parameters that should be passed to the model constructor
        model_kwargs = {"id": model_id}
        
        # Standard LLM parameters that models support
        supported_llm_params = [
            'temperature', 'max_tokens', 'top_p', 'top_k', 
            'frequency_penalty', 'presence_penalty', 'repetition_penalty',
            'min_p', 'tfs', 'typical_p', 'epsilon_cutoff', 'eta_cutoff'
        ]
        
        # Use validated config instead of raw model_config
        for param in supported_llm_params:
            param_value = getattr(validated_config, param, None)
            if param_value is not None:
                model_kwargs[param] = param_value
                logger.debug(f"Adding model parameter {param}={param_value} to {provider}/{model_id}")
        
        # Track parameters that must be removed for specific providers/models
        unsupported_params_for_model: List[str] = []
        
        try:
            if provider == "litellm":
                import litellm

                # Check if this is an o3 model that needs parameter dropping
                is_o3_model = "o3" in lower_model_id

                # OpenAI GPT-5 models currently reject certain sampling params (e.g., top_p)
                is_openai_gpt5 = "openai/gpt-5" in lower_model_id or lower_model_id.startswith("gpt-5")
                if is_openai_gpt5:
                    unsupported_params_for_model.extend(["top_p", "temperature"])

                # Remove any unsupported parameters before instantiation
                for unsupported_param in unsupported_params_for_model:
                    if unsupported_param in model_kwargs:
                        removed_value = model_kwargs.pop(unsupported_param)
                        logger.debug(
                            f"Removing unsupported parameter {unsupported_param}={removed_value} for {model_id}"
                        )

                if is_o3_model or is_openai_gpt5:
                    # For these models, enable LiteLLM's parameter dropping safety net
                    logger.info(
                        f"🔧 Creating LiteLLM model: {model_id} with drop_params=True to avoid unsupported params"
                    )
                    litellm.drop_params = True
                else:
                    logger.info(f"🔧 Creating LiteLLM model: {model_id}")

                # Create LiteLLM instance - environment variables are already validated
                return model_class(**model_kwargs)
                
            elif provider == "openai":
                logger.info(f"🔧 Creating OpenAI model: {model_id}")
                return model_class(**model_kwargs)
                
            elif provider in ["fireworks", "fireworks_ai"]:
                logger.info(f"🔧 Creating Fireworks AI model: {model_id}")
                return model_class(**model_kwargs)
                
            else:
                # Generic instantiation
                logger.info(f"🔧 Creating {provider} model: {model_id}")
                return model_class(**model_kwargs)
                
        except Exception as e:
            logger.error(f"Failed to create model instance for {provider}/{model_id}: {e}")
            
            # Provide more specific error messages for common issues
            error_msg = str(e).lower()
            if "api key" in error_msg or "authentication" in error_msg or "unauthorized" in error_msg:
                raise ValueError(
                    f"Authentication failed for {provider}/{model_id}. "
                    f"Please verify your API key in .env file is correct and has the necessary permissions. "
                    f"Original error: {e}"
                ) from e
            elif "rate limit" in error_msg:
                raise ValueError(
                    f"Rate limit exceeded for {provider}/{model_id}. "
                    f"Please wait before retrying or check your API quota. "
                    f"Original error: {e}"
                ) from e
            elif "not found" in error_msg or "model" in error_msg:
                raise ValueError(
                    f"Model '{model_id}' not found or not accessible for provider '{provider}'. "
                    f"Please verify the model name is correct. "
                    f"Original error: {e}"
                ) from e
            else:
                raise ValueError(
                    f"Failed to create model instance for {provider}/{model_id}. "
                    f"Original error: {e}"
                ) from e
    
    def create_tools(self, tool_configs: List[Union[str, Dict[str, Any]]]) -> List[Any]:
        """
        Create tool instances from tool configurations.
        
        Args:
            tool_configs: List of tool names (strings) or tool configurations (dicts)
                         Dict format: {"name": "ToolName", "params": {...}}
            
        Returns:
            List of tool instances
        """
        tools = []
        
        # Import web_search function if needed
        web_search = None
        clean_tools_func = None
        # Check if web_search is needed
        for config in tool_configs:
            if isinstance(config, str):
                tool_name = config
            elif hasattr(config, '__getitem__'):
                tool_name = config.get("name") or ""
            else:
                continue
            if tool_name == "web_search":
                try:
                    from ..tools.web_search_tool import web_search, clean_tools
                    clean_tools_func = clean_tools
                    logger.debug("Imported web_search function")
                except ImportError as e:
                    logger.error(f"Failed to import web_search: {e}")
                break
        
        for config in tool_configs:
            # Handle both string (legacy) and dict (new) formats
            if isinstance(config, str):
                tool_name = config
                tool_params = {}
            elif isinstance(config, dict) or hasattr(config, '__getitem__'):
                # Handle both regular dict and OmegaConf DictConfig
                tool_name = config.get("name") or ""
                tool_params = config.get("params", {})
            else:
                logger.warning(f"Invalid tool configuration type: {type(config)}")
                continue
            
            if tool_name in self._tools:
                try:
                    tool_class = self._tools[tool_name]
                    
                    # Special handling for PythonTools to set save_and_run parameter
                    if tool_name == "PythonTools" and "save_and_run" not in tool_params:
                        # Default to False for save_and_run to avoid automatic execution
                        tool_params["save_and_run"] = False
                        logger.debug(f"Setting save_and_run=False for PythonTools (default)")
                    
                    # Create tool instance with parameters
                    if tool_params:
                        tool_instance = tool_class(**tool_params)
                        logger.debug(f"Created tool: {tool_name} with params: {tool_params}")
                    else:
                        tool_instance = tool_class()
                        logger.debug(f"Created tool: {tool_name}")
                    
                    tools.append(tool_instance)
                except Exception as e:
                    logger.error(f"Failed to create tool {tool_name} with params: {tool_params} - {e}")
                    # Continue with other tools
            elif tool_name == "web_search" and web_search is not None:
                # Add the web_search function directly
                tools.append(web_search)
                logger.debug("Added web_search function as tool")
            else:
                logger.warning(f"Unknown tool: {tool_name}")
        
        # Clean tools to remove problematic attributes
        if clean_tools_func:
            tools = clean_tools_func(tools)
            logger.debug("Cleaned tools to remove problematic attributes")
        
        return tools
        
    def create_toolkits(self, toolkit_configs: List[Dict[str, Any]]) -> List[Any]:
        """
        Create toolkit instances and extract specified tools.
        Supports both custom toolkits and agno toolkits with dynamic discovery.
        
        Args:
            toolkit_configs: List of toolkit configurations
            
        Returns:
            List of selected toolkits
            
        Raises:
            ValueError: If toolkit configuration is invalid
        """
        selected_toolkits = []
        
        for config in toolkit_configs:
            # Validate and parse toolkit configuration using Pydantic model
            try:
                validated_toolkit = validate_toolkit_config(config)
                toolkit_name = validated_toolkit.name
                logger.info(f"✅ Toolkit configuration validated: {toolkit_name}")
            except Exception as e:
                logger.error(f"Invalid toolkit configuration: {e}")
                raise ValueError(f"Toolkit validation failed: {e}") from e

            # Try custom toolkits first
            if toolkit_name in self._toolkits:
                try:
                    toolkit_class = self._toolkits[toolkit_name]
                    params = validated_toolkit.params
                    
                    # Enable credential validation only for data toolkits that have API key fields
                    param_class = ToolkitConfig.get_toolkit_params_class(toolkit_name)
                    if param_class and 'validate_credentials' in param_class.model_fields:
                        # Check if this toolkit actually has API key fields that need validation
                        has_api_key_fields = any(
                            field_name in ['api_key', 'api_secret'] 
                            for field_name in param_class.model_fields
                        )
                        
                        if has_api_key_fields:
                            params["validate_credentials"] = True
                            logger.debug(f"Enabled credential validation for {toolkit_name} (has API key fields)")
                            
                            # Re-validate parameters with credential validation enabled
                            # This will trigger API key validation and raise exception if keys are missing
                            try:
                                param_class(**params)  # Validate parameters
                                logger.debug(f"✅ API credentials validated for {toolkit_name}")
                            except Exception as validation_error:
                                # Let this exception propagate up to be caught and logged as warning
                                raise validation_error
                        else:
                            logger.debug(f"Skipping credential validation for {toolkit_name} (no API key fields)")
                    
                    # Apply any parameter transformations
                    params = self._transform_toolkit_params(toolkit_name, params)
                    
                    # Remove validate_credentials from params before passing to toolkit constructor
                    # since the actual toolkit classes don't expect this parameter
                    toolkit_params = {k: v for k, v in params.items() if k != 'validate_credentials'}
                    
                    available_tools = validated_toolkit.available_tools
                    if available_tools:
                        toolkit_params["include_tools"] = available_tools
                    
                    toolkit_instance = toolkit_class(**toolkit_params)
                    logger.info(f"Created custom toolkit '{toolkit_name}' with params: {params}")
                    selected_toolkits.append(toolkit_instance)
                            
                except Exception as e:
                    # Log error but continue - all toolkits are optional
                    logger.warning(f"Custom toolkit '{toolkit_name}' failed to load - skipping: {e}")
                    logger.info(f"💡 Check {toolkit_name} configuration and dependencies")
            else:
                # Try to resolve as agno toolkit
                try:
                    agno_toolkit_instance = self._create_agno_toolkit(toolkit_name, validated_toolkit)
                    if agno_toolkit_instance:
                        selected_toolkits.append(agno_toolkit_instance)
                        logger.info(f"Created agno toolkit '{toolkit_name}'")
                    else:
                        # Toolkit not found - log warning and continue
                        available_custom = list(self._toolkits.keys())
                        logger.warning(f"Toolkit '{toolkit_name}' not available - skipping")
                        logger.info(f"💡 Available custom toolkits: {available_custom}")
                        logger.info(f"💡 Please check default Agno toolkits for using pre-defined tools")
                except Exception as e:
                    # Log error but continue - all toolkits are optional
                    logger.warning(f"Toolkit '{toolkit_name} with params {validated_toolkit.params}' failed to load - skipping: {e}")
                    logger.info(f"💡 If you need {toolkit_name}, check that all dependencies are installed and configured")
                
        return selected_toolkits
    
    # Toolkit validation is now handled by Pydantic ToolkitConfig model
    
    def _transform_toolkit_params(self, toolkit_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform toolkit parameters if needed.
        
        Args:
            toolkit_name: Name of the toolkit
            params: Original parameters
            
        Returns:
            dict: Transformed parameters
        """
        if toolkit_name in self._toolkits:
            # Convert relative data_dir to absolute if needed for data toolkits
            data_dir = params.get("data_dir")
            if data_dir and not os.path.isabs(data_dir):
                # Make relative to project root
                project_root = Path(__file__).resolve().parents[4]  # Go up to project root
                params["data_dir"] = str(project_root / data_dir)
                logger.debug(f"Converted relative data_dir to absolute: {params['data_dir']}")
        
        return params
    
    def _create_agno_toolkit(self, toolkit_name: str, validated_toolkit) -> Optional[Any]:
        """
        Dynamically create an agno toolkit instance.
        
        Args:
            toolkit_name: Name of the agno toolkit (e.g., "E2BTools")
            validated_toolkit: Validated toolkit configuration
            
        Returns:
            Agno toolkit instance or None if not found
        """
        try:
            # Try to import the toolkit from agno.tools
            module_path = f"agno.tools.{toolkit_name.lower().replace('tools', '')}"
            if module_path.endswith('.'):
                module_path = module_path[:-1]
            
            logger.debug(f"Attempting to import agno toolkit from: {module_path}")
            
            try:
                # First try the calculated module path
                module = importlib.import_module(module_path)
                toolkit_class = getattr(module, toolkit_name, None)
            except ImportError:
                # Try common agno.tools locations
                common_locations = [
                    f"agno.tools.{toolkit_name.lower()}",
                    f"agno.tools",
                    f"agno.{toolkit_name.lower()}"
                ]
                
                toolkit_class = None
                for location in common_locations:
                    try:
                        module = importlib.import_module(location)
                        toolkit_class = getattr(module, toolkit_name, None)
                        if toolkit_class:
                            logger.debug(f"Found {toolkit_name} in {location}")
                            break
                    except (ImportError, AttributeError):
                        continue
            
            if not toolkit_class:
                logger.warning(f"Agno toolkit class {toolkit_name} not found in any expected location")
                return None
            
            # Create toolkit instance with parameters
            params = validated_toolkit.params or {}
            
            # For E2B specifically, ensure template is set in sandbox_options
            if toolkit_name == "E2BTools":
                # Handle timeout parameter
                if "timeout" not in params:
                    timeout = int(os.getenv("E2B_TIMEOUT", "300"))
                    params["timeout"] = timeout
                    logger.debug(f"Set E2B timeout to: {timeout}s")
                
                # Handle template via sandbox_options
                if "sandbox_options" not in params:
                    params["sandbox_options"] = {}
                
                if "template" not in params["sandbox_options"]:
                    template_id = os.getenv("E2B_TEMPLATE_ID", "sentient-e2b-s3")
                    params["sandbox_options"]["template"] = template_id
                    logger.debug(f"Set E2B template to: {template_id}")
                
                # # Add AWS credentials and S3 configuration to sandbox environment
                # if "envs" not in params["sandbox_options"]:
                #     params["sandbox_options"]["envs"] = {}
                
                # # Add AWS credentials from environment if available
                # aws_vars = {
                #     "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
                #     "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
                #     "AWS_REGION": os.getenv("AWS_REGION"),
                #     "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME"),
                # }
                
                # # Only add non-None values to avoid cluttering environment
                # for key, value in aws_vars.items():
                #     if value:
                #         params["sandbox_options"]["envs"][key] = value
                #         logger.debug(f"Added AWS environment variable: {key}")
                
                # # Add project ID if available for data toolkit integration
                # project_id = os.getenv("CURRENT_PROJECT_ID")
                # if project_id:
                #     params["sandbox_options"]["envs"]["CURRENT_PROJECT_ID"] = project_id
                #     logger.debug(f"Added CURRENT_PROJECT_ID: {project_id}")
            
            # Create the toolkit instance
            toolkit_instance = toolkit_class(**params)
            logger.debug(f"Created agno toolkit {toolkit_name} with params: {params}")
            
            return toolkit_instance
            
        except Exception as e:
            import traceback
            logger.error(f"Failed to create agno toolkit {toolkit_name} with params {validated_toolkit.params}: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return None
    
    def create_agno_agent(self, agent_config: DictConfig) -> Optional[AgnoAgent]:
        """
        Create an AgnoAgent instance from configuration with proper structured output support.
        
        Args:
            agent_config: Agent configuration from YAML
            
        Returns:
            AgnoAgent instance or None for agents that don't use AgnoAgent
        """
        # Some agents (like custom search adapters) don't use AgnoAgent
        adapter_class_name = agent_config.get("adapter_class", "")
        if adapter_class_name in ["OpenAICustomSearchAdapter", "GeminiCustomSearchAdapter", "ExaCustomSearchAdapter"]:
            logger.debug(f"Agent {agent_config.name} doesn't use AgnoAgent (custom search adapter)")
            return None
        
        if "model" not in agent_config or "prompt_source" not in agent_config:
            logger.debug(f"Agent {agent_config.name} doesn't use AgnoAgent (no model/prompt_source)")
            return None
        
        try:
            # Create model instance
            model = self.create_model_instance(agent_config.model)
            logger.debug(f"Created model for {agent_config.name}: {agent_config.model.provider}/{agent_config.model.model_id}")
            
            # Resolve system prompt
            system_message = self.config_loader.resolve_prompt(agent_config.prompt_source)
            logger.debug(f"Resolved prompt for {agent_config.name} from {agent_config.prompt_source}")
            
            # Get response model if specified
            response_model = None
            if "response_model" in agent_config:
                response_model_name = agent_config.response_model
                response_model = self.resolve_response_model(response_model_name)
                if response_model:
                    logger.debug(f"Using response model for {agent_config.name}: {response_model_name}")
                else:
                    logger.warning(f"Could not resolve response model {response_model_name} for {agent_config.name}")
            
            # Create tools if specified
            tools = []
            if "tools" in agent_config and agent_config.tools:
                tools.extend(self.create_tools(agent_config.tools))

            if "toolkits" in agent_config and agent_config.toolkits:
                tools.extend(self.create_toolkits(agent_config.toolkits))
            
            if tools:
                logger.debug(f"Created {len(tools)} tools/toolkit functions for {agent_config.name}")
            
            # Prepare AgnoAgent kwargs
            agno_kwargs = {
                "model": model,
                "system_message": system_message,
                "name": f"{agent_config.name}_Agno",
            }
            
            # Add response model if specified
            if response_model:
                agno_kwargs["response_model"] = response_model
            
            # Add tools if available
            if tools:
                agno_kwargs["tools"] = tools
            
            # NOTE: LLM settings like temperature should be handled during model creation,
            # not passed to AgnoAgent constructor which doesn't accept them.
            # Removed problematic code that added LLM settings to agno_kwargs.
            
            # Handle additional AgnoAgent parameters from config
            if "agno_params" in agent_config and agent_config.agno_params is not None:
                additional_params = dict(agent_config.agno_params)
                agno_kwargs.update(additional_params)
                logger.debug(f"Added additional AgnoAgent params for {agent_config.name}: {list(additional_params.keys())}")
            
            # Log the arguments before creating the agent to verify
            logger.debug(f"Creating AgnoAgent for {agent_config.name} with kwargs: {agno_kwargs}")

            # Create AgnoAgent
            agno_agent = AgnoAgent(**agno_kwargs)
            
            logger.info(f"✅ Created AgnoAgent for {agent_config.name}")
            return agno_agent
            
        except Exception as e:
            logger.error(f"❌ Failed to create AgnoAgent for {agent_config.name}: {e}")
            raise
    
    def create_adapter(self, agent_config: DictConfig, agno_agent: Optional[AgnoAgent] = None) -> Any:
        """
        Create an adapter instance from configuration.
        
        Args:
            agent_config: Agent configuration from YAML
            agno_agent: Optional AgnoAgent instance
            
        Returns:
            Adapter instance
        """
        adapter_class_name = agent_config.adapter_class
        
        if adapter_class_name not in self._adapter_classes:
            raise ValueError(f"Unknown adapter class: {adapter_class_name}")
        
        adapter_class = self._adapter_classes[adapter_class_name]
        
        try:
            # Special handling for different adapter types
            if adapter_class_name in ["OpenAICustomSearchAdapter", "GeminiCustomSearchAdapter", "ExaCustomSearchAdapter"]:
                # These adapters don't use AgnoAgent and have special initialization
                adapter_kwargs = {}
                
                # Check if there are custom parameters for this adapter
                if "adapter_params" in agent_config and agent_config.adapter_params is not None:
                    adapter_kwargs.update(dict(agent_config.adapter_params))
                
                # Override model_id if specified in config
                if "model" in agent_config and agent_config.model is not None and "model_id" in agent_config.model:
                    adapter_kwargs["model_id"] = agent_config.model.model_id
                
                return adapter_class(**adapter_kwargs)
                
            else:
                # Most adapters require an AgnoAgent instance
                if agno_agent is None:
                    raise ValueError(f"Adapter {adapter_class_name} requires an AgnoAgent instance")
                
                adapter_kwargs = {
                    "agno_agent_instance": agno_agent,
                    "agent_name": agent_config.name
                }
                
                # Add any additional adapter parameters from config
                if "adapter_params" in agent_config and agent_config.adapter_params is not None:
                    additional_params = dict(agent_config.adapter_params)
                    adapter_kwargs.update(additional_params)
                    logger.debug(f"Added additional adapter params for {agent_config.name}: {list(additional_params.keys())}")
                
                return adapter_class(**adapter_kwargs)
                
        except Exception as e:
            logger.error(f"❌ Failed to create adapter {adapter_class_name} for {agent_config.name}: {e}")
            raise
    
    def create_agent(self, agent_config: Union[DictConfig, Dict[str, Any], AgentConfig]) -> Dict[str, Any]:
        """
        Create a complete agent (AgnoAgent + Adapter) from configuration with Pydantic validation.
        
        Args:
            agent_config: Agent configuration (DictConfig, dict, or AgentConfig)
            
        Returns:
            Dictionary containing agent components and metadata
        """
        # Convert to Pydantic AgentConfig for validation
        if isinstance(agent_config, AgentConfig):
            validated_config = agent_config
        else:
            # Convert DictConfig or dict to dict
            if hasattr(agent_config, '__getitem__'):
                config_dict = dict(agent_config)
            else:
                config_dict = agent_config
                
            # Validate using Pydantic model
            try:
                validated_config = validate_agent_config(config_dict)
                logger.debug(f"✅ Agent configuration validated: {validated_config.name}")
            except Exception as e:
                logger.error(f"Agent configuration validation failed: {e}")
                raise ValueError(f"Invalid agent configuration: {e}") from e
        
        logger.info(f"🔧 Creating agent: {validated_config.name} (type: {validated_config.type})")
        
        try:
            # Create AgnoAgent if needed (pass original config for now - will refactor methods later)
            agno_agent = self.create_agno_agent(agent_config if not isinstance(agent_config, AgentConfig) else agent_config)
            
            # Create adapter
            adapter = self.create_adapter(agent_config if not isinstance(agent_config, AgentConfig) else agent_config, agno_agent)
            
            # CRITICAL FIX: Verify adapter is BaseAdapter
            if not isinstance(adapter, BaseAdapter):
                logger.error(f"❌ Created adapter for {validated_config.name} is not a BaseAdapter!")
                logger.error(f"   Type: {type(adapter)}")
                logger.error(f"   Expected: {BaseAdapter}")
                raise TypeError(f"Adapter {type(adapter)} is not a BaseAdapter")
            
            logger.info(f"✅ Created valid BaseAdapter for {validated_config.name}: {type(adapter).__name__}")
            
            # Prepare registration information
            registration_info = {
                "action_keys": [],
                "named_keys": []
            }
            
            if "registration" in agent_config:
                reg_config = agent_config.registration
                
                if "action_keys" in reg_config:
                    # Convert string task_types to TaskType enums
                    action_keys = []
                    for key in reg_config.action_keys:
                        action_verb = key.action_verb
                        task_type_value = key.get("task_type")
                        
                        # Convert string task_type to TaskType enum
                        if task_type_value is not None and isinstance(task_type_value, str):
                            try:
                                task_type_enum = TaskType[task_type_value.upper()]
                                action_keys.append((action_verb, task_type_enum))
                                logger.debug(f"Converted task_type '{task_type_value}' to enum {task_type_enum} for {agent_config.name}")
                            except KeyError:
                                logger.error(f"Invalid task_type '{task_type_value}' for agent {agent_config.name}. Valid values: {list(TaskType.__members__.keys())}")
                                raise ValueError(f"Invalid task_type: {task_type_value}")
                        else:
                            # task_type is None or already an enum
                            action_keys.append((action_verb, task_type_value))
                    
                    registration_info["action_keys"] = action_keys
                
                if "named_keys" in reg_config:
                    registration_info["named_keys"] = list(reg_config.named_keys)
            
            # Collect metadata about the agent
            # Get actual runtime tools from AgnoAgent if available
            runtime_tools = []
            if agno_agent and hasattr(agno_agent, 'tools') and agno_agent.tools:
                runtime_tools = [{"name": getattr(tool, '__name__', str(type(tool).__name__)), "params": {}} for tool in agno_agent.tools]
            
            metadata = {
                "has_structured_output": "response_model" in agent_config,
                "response_model": agent_config.get("response_model"),
                "has_tools": bool(runtime_tools) or ("tools" in agent_config and bool(agent_config.tools)),
                "tools": runtime_tools if runtime_tools else list(agent_config.get("tools", [])),
                "model_info": dict(agent_config.model) if agent_config.get("model") else None,
                "prompt_source": agent_config.get("prompt_source"),
            }
            
            agent_info = {
                "name": agent_config.name,
                "type": agent_config.type,
                "description": agent_config.get("description", ""),
                "adapter": adapter,
                "agno_agent": agno_agent,
                "registration": registration_info,
                "enabled": agent_config.get("enabled", True),
                "metadata": metadata,
                "config": agent_config
            }
            
            logger.info(f"✅ Successfully created agent: {agent_config.name}")
            if metadata["has_structured_output"]:
                logger.info(f"   📋 Structured output: {metadata['response_model']}")
            if metadata["has_tools"]:
                logger.info(f"   🔧 Tools: {metadata['tools']}")
            
            return agent_info
            
        except Exception as e:
            logger.error(f"❌ Failed to create agent {agent_config.name}: {e}")
            raise
    
    def create_all_agents(self, config: DictConfig) -> Dict[str, Dict[str, Any]]:
        """
        Create all agents from configuration.
        
        Args:
            config: Full configuration containing all agents
            
        Returns:
            Dictionary mapping agent names to agent info
        """
        agents = {}
        created_count = 0
        skipped_count = 0
        failed_count = 0
        
        logger.info(f"🚀 Creating {len(config.agents)} agents from configuration...")
        
        for agent_config in config.agents:
            try:
                # Skip disabled agents
                if not agent_config.get("enabled", True):
                    logger.info(f"⏭️  Skipping disabled agent: {agent_config.name}")
                    skipped_count += 1
                    continue
                
                # Create the agent
                agent_info = self.create_agent(agent_config)
                agents[agent_config.name] = agent_info
                created_count += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to create agent {agent_config.name}: {e}")
                failed_count += 1
                # Continue with other agents rather than failing completely
                continue
        
        logger.info(f"📊 Agent creation summary:")
        logger.info(f"   ✅ Created: {created_count}")
        logger.info(f"   ⏭️  Skipped: {skipped_count}")
        logger.info(f"   ❌ Failed: {failed_count}")
        
        return agents

    def create_agents_for_profile(self, profile_config: 'DictConfig') -> Dict[str, Dict[str, Any]]:
        """
        Create agents specifically for a profile configuration.
        
        Args:
            profile_config: Profile configuration from YAML
            
        Returns:
            Dictionary of created agents
        """
        created_agents = {}
        
        # If the profile has its own agents section, create those
        if "agents" in profile_config and profile_config.agents:
            logger.info(f"Creating {len(profile_config.agents)} profile-specific agents...")
            
            for agent_config in profile_config.agents:
                if agent_config.get("enabled", True):
                    try:
                        agent_info = self.create_agent(agent_config)
                        created_agents[agent_config.name] = agent_info
                        logger.info(f"✅ Created profile agent: {agent_config.name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to create profile agent {agent_config.name}: {e}")
        
        return created_agents

    def validate_blueprint_agents(self, blueprint: 'AgentBlueprint', agent_registry: AgentRegistry) -> Dict[str, Any]:
        """
        Validate that all agents referenced in a blueprint exist in the given registry instance.
        
        Args:
            blueprint: AgentBlueprint to validate.
            agent_registry: The AgentRegistry instance to check against.
            
        Returns:
            Validation results.
        """
        validation = {
            "valid": True,
            "missing_agents": [],
            "issues": [], # Added for consistency
            "available_agents": list(agent_registry.get_all_named_agents().keys()),
            "blueprint_agents": []
        }
        
        # Get all named agents from the instance
        named_agents = agent_registry.get_all_named_agents()

        # Check planners
        for task_type, planner_name in blueprint.planner_adapter_names.items():
            validation["blueprint_agents"].append(f"Planner({task_type.value}): {planner_name}")
            if planner_name not in named_agents:
                validation["missing_agents"].append(f"Planner: {planner_name}")
                validation["valid"] = False
        
        # Check executors
        for task_type, executor_name in blueprint.executor_adapter_names.items():
            validation["blueprint_agents"].append(f"Executor({task_type.value}): {executor_name}")
            if executor_name not in named_agents:
                validation["missing_agents"].append(f"Executor: {executor_name}")
                validation["valid"] = False
        
        # Check other agents
        other_agents = [
            ("Root Planner", blueprint.root_planner_adapter_name),
            ("Aggregator", blueprint.aggregator_adapter_name),
            ("Atomizer", blueprint.atomizer_adapter_name),
            ("PlanModifier", blueprint.plan_modifier_adapter_name),
            ("Default Planner", blueprint.default_planner_adapter_name),
            ("Default Executor", blueprint.default_executor_adapter_name),
        ]
        
        for agent_type, agent_name in other_agents:
            if agent_name:
                validation["blueprint_agents"].append(f"{agent_type}: {agent_name}")
                if agent_name not in named_agents:
                    validation["missing_agents"].append(f"{agent_type}: {agent_name}")
                    validation["valid"] = False
        
        if validation["missing_agents"]:
            validation["issues"].extend([
                f"Agent '{name}' referenced in blueprint '{blueprint.name}' is not registered."
                for name in validation["missing_agents"]
            ])

        return validation


def create_agents_from_config(config: DictConfig, config_loader) -> Dict[str, Dict[str, Any]]:
    """
    Convenience function to create all agents from configuration.
    
    Args:
        config: Configuration containing agent definitions
        config_loader: AgentConfigLoader instance
        
    Returns:
        Dictionary of created agents
    """
    factory = AgentFactory(config_loader)
    return factory.create_all_agents(config) 
