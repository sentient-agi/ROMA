#!/usr/bin/env python3
"""
FastAPI server for SentientResearchAgent using LightweightSentientAgent.

This provides a REST API interface to the research agent functionality.
Perfect for production deployments, microservices, and integration.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import asyncio
import time
from pathlib import Path
import sys
import uvicorn
from contextlib import asynccontextmanager

# Add the src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from sentientresearchagent.framework_entry import LightweightSentientAgent
from sentientresearchagent.core.system_manager import SystemManagerV2 as ConcreteSystemManager
from sentientresearchagent.config import load_config

# Global state
system_manager = None
agent_cache = {}

# Request/Response Models
class ResearchRequest(BaseModel):
    goal: str = Field(..., description="Research question or goal", min_length=1, max_length=1000)
    profile: str = Field(default="general_agent", description="Agent profile to use")
    max_steps: int = Field(default=25, ge=5, le=100, description="Maximum execution steps")
    max_concurrent_nodes: Optional[int] = Field(default=None, ge=1, le=20, description="Override concurrent nodes")
    skip_atomization: Optional[bool] = Field(default=None, description="Override atomization setting")
    save_state: bool = Field(default=False, description="Whether to save execution state")

class ResearchResponse(BaseModel):
    execution_id: str
    goal: str
    result: Optional[str]
    status: str
    execution_time: float
    steps_completed: Optional[int]
    node_count: int
    profile_used: str
    lightweight: bool = True

class HealthResponse(BaseModel):
    status: str
    version: str
    available_profiles: List[str]
    configuration: Dict[str, Any]

class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None

# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global system_manager
    
    print("🚀 Starting SentientResearchAgent FastAPI server...")
    
    # Load configuration and initialize system manager
    try:
        config = load_config(config_file="sentient.yaml")
        system_manager = ConcreteSystemManager(config)
        print(f"✅ System initialized - Skip atomization: {config.execution.skip_atomization}")
        print(f"✅ Max concurrent nodes: {config.execution.max_concurrent_nodes}")
    except Exception as e:
        print(f"❌ Failed to initialize system: {e}")
        raise
    
    yield
    
    # Cleanup
    print("🛑 Shutting down SentientResearchAgent server...")
    if system_manager and hasattr(system_manager, 'cleanup'):
        await system_manager.cleanup()

# Create FastAPI app
app = FastAPI(
    title="SentientResearchAgent API",
    description="Lightweight research agent API for sophisticated analysis and information gathering",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper function to get or create agent
async def get_agent(profile: str) -> LightweightSentientAgent:
    """Get or create a lightweight agent for the specified profile."""
    if profile not in agent_cache:
        try:
            agent = LightweightSentientAgent.create_with_profile(
                profile_name=profile,
                system_manager=system_manager
            )
            agent_cache[profile] = agent
        except Exception as e:
            raise HTTPException(
                status_code=400, 
                detail=f"Failed to create agent with profile '{profile}': {str(e)}"
            )
    
    return agent_cache[profile]

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with system information."""

    if system_manager is None or not getattr(system_manager, "config", None):
        return HealthResponse(
            status="initializing",
            version="1.0.0",
            available_profiles=[],
            configuration={}
        )

    available_profiles = [
        "general_agent",
        "crypto_analytics_agent",
        "deep_research_agent"
    ]
    
    config_info = {
        "skip_atomization": system_manager.config.execution.skip_atomization,
        "max_concurrent_nodes": system_manager.config.execution.max_concurrent_nodes,
        "hitl_enabled": system_manager.config.execution.enable_hitl,
        "cache_enabled": system_manager.config.cache.enabled
    }
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        available_profiles=available_profiles,
        configuration=config_info
    )

@app.post("/research", response_model=ResearchResponse)
async def research_endpoint(request: ResearchRequest):
    """Execute a research query using the lightweight agent."""
    
    start_time = time.time()
    
    try:
        # Get the appropriate agent
        agent = await get_agent(request.profile)
        
        # Prepare execution options
        options = {}
        if request.max_concurrent_nodes is not None:
            options['max_concurrent_nodes'] = request.max_concurrent_nodes
        if request.skip_atomization is not None:
            options['skip_atomization'] = request.skip_atomization
        
        # Execute the research query
        result = await agent.execute(
            goal=request.goal,
            max_steps=request.max_steps,
            save_state=request.save_state,
            **options
        )
        
        # Return structured response
        return ResearchResponse(
            execution_id=result.get('execution_id', 'unknown'),
            goal=request.goal,
            result=result.get('final_result'),
            status=result.get('status', 'completed'),
            execution_time=result.get('execution_time', time.time() - start_time),
            steps_completed=result.get('execution_stats', {}).get('steps_completed'),
            node_count=result.get('node_count', 0),
            profile_used=request.profile
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Research execution failed: {str(e)}"
        )

@app.post("/research/async")
async def research_async_endpoint(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start a research query in the background and return immediately."""
    
    execution_id = f"async_{int(time.time())}"
    
    # This is a placeholder - you could implement with a task queue like Celery
    # For now, it just returns the execution ID
    
    return {
        "execution_id": execution_id,
        "status": "started",
        "message": "Research started in background. Use /research/{execution_id} to check status.",
        "goal": request.goal,
        "profile": request.profile
    }

@app.get("/profiles")
async def list_profiles():
    """List available agent profiles."""
    
    profiles = {
        "general_agent": {
            "name": "General Agent",
            "description": "General-purpose research and analysis agent",
            "capabilities": ["search", "analysis", "synthesis", "reporting"]
        },
        "crypto_analytics_agent": {
            "name": "Crypto Analytics Agent", 
            "description": "Specialized agent for cryptocurrency and blockchain analysis",
            "capabilities": ["market_analysis", "defi_research", "token_analysis", "regulatory_tracking"]
        },
        "deep_research_agent": {
            "name": "Deep Research Agent",
            "description": "Advanced research agent for comprehensive analysis",
            "capabilities": ["academic_research", "policy_analysis", "technical_research", "comparative_studies"]
        }
    }
    
    return {"profiles": profiles}

@app.get("/config")
async def get_configuration():
    """Get current system configuration."""

    if system_manager is None or not getattr(system_manager, "config", None):
        raise HTTPException(status_code=503, detail="System manager not initialized")

    return {
        "execution": {
            "skip_atomization": system_manager.config.execution.skip_atomization,
            "max_concurrent_nodes": system_manager.config.execution.max_concurrent_nodes,
            "max_execution_steps": system_manager.config.execution.max_execution_steps,
            "hitl_enabled": system_manager.config.execution.enable_hitl,
        },
        "cache": {
            "enabled": system_manager.config.cache.enabled,
            "type": system_manager.config.cache.cache_type,
        },
        "llm": {
            "provider": system_manager.config.llm.provider,
            "timeout": system_manager.config.llm.timeout,
        }
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {"error": exc.detail, "status_code": exc.status_code}

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return {"error": "Internal server error", "details": str(exc)}

if __name__ == "__main__":
    print("🚀 Starting SentientResearchAgent FastAPI Server")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("❤️  Health Check: http://localhost:8000/health")
    
    # Run with uvicorn
    uvicorn.run(
        "fastapi_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable for development
        log_level="info"
    )