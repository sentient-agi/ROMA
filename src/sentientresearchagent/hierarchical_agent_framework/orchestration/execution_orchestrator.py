"""
ExecutionOrchestrator - High-level orchestration of task execution.

This replaces the monolithic ExecutionEngine with a cleaner, more focused design.
Responsibilities:
- Orchestrate the overall execution flow
- Coordinate between different services
- Manage the execution lifecycle
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
from loguru import logger
from pathlib import Path
import asyncio

from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskStatus, TaskType, NodeType
from sentientresearchagent.exceptions import SentientError
from .batched_state_manager import BatchedStateManager

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph
    from sentientresearchagent.hierarchical_agent_framework.graph.state_manager import StateManager
    from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
    from sentientresearchagent.hierarchical_agent_framework.node.node_processor import NodeProcessor
    from sentientresearchagent.config import SentientConfig
    from .task_scheduler import TaskScheduler
    from .deadlock_detector import DeadlockDetector
    from .recovery_manager import RecoveryManager
    from ..persistence.checkpoint_manager import CheckpointManager


class ExecutionOrchestrator:
    """
    High-level orchestrator for task execution.
    
    This class coordinates between different services to execute a task graph.
    It delegates specific responsibilities to specialized components.
    """
    
    def __init__(
        self,
        task_graph: "TaskGraph",
        state_manager: "StateManager",
        knowledge_store: "KnowledgeStore",
        node_processor: "NodeProcessor",
        config: "SentientConfig",
        task_scheduler: Optional["TaskScheduler"] = None,
        deadlock_detector: Optional["DeadlockDetector"] = None,
        recovery_manager: Optional["RecoveryManager"] = None,
        checkpoint_manager: Optional["CheckpointManager"] = None,
    ):
        """
        Initialize the ExecutionOrchestrator.
        
        Args:
            task_graph: The task graph to execute
            state_manager: Manages state transitions
            knowledge_store: Stores execution knowledge
            node_processor: Processes individual nodes
            config: System configuration
            task_scheduler: Schedules tasks for execution (will create if not provided)
            deadlock_detector: Detects deadlocks (will create if not provided)
            recovery_manager: Manages error recovery (will create if not provided)
            checkpoint_manager: Manages checkpoints (optional)
        """
        self.task_graph = task_graph
        self.state_manager = state_manager
        self.knowledge_store = knowledge_store
        self.node_processor = node_processor
        self.config = config
        
        # Create default components if not provided
        if not task_scheduler:
            from .task_scheduler import TaskScheduler
            self.task_scheduler = TaskScheduler(task_graph, state_manager)
        else:
            self.task_scheduler = task_scheduler
            
        if not deadlock_detector:
            from .deadlock_detector import DeadlockDetector
            self.deadlock_detector = DeadlockDetector(task_graph, state_manager, config=config)
        else:
            self.deadlock_detector = deadlock_detector
            
        if not recovery_manager:
            from .recovery_manager import RecoveryManager
            self.recovery_manager = RecoveryManager(config)
        else:
            self.recovery_manager = recovery_manager
            
        self.checkpoint_manager = checkpoint_manager
        
        # Execution state
        self._execution_id: Optional[str] = None
        self._is_running = False
        self._execution_stats = {
            "steps_executed": 0,
            "nodes_processed": 0,
            "errors_recovered": 0,
            "checkpoints_created": 0
        }
        
        # Dynamic concurrency management
        self._current_concurrency = config.execution.max_concurrent_nodes
        self._rate_limit_errors = 0
        self._last_rate_limit_time = None
        self._processing_times = []  # Track recent processing times
        self._concurrency_lock = asyncio.Lock()
        
        # Initialize batched state manager
        self.batched_state_manager = BatchedStateManager(
            knowledge_store=knowledge_store,
            task_graph=task_graph,
            batch_size=getattr(config.execution, 'state_batch_size', 50),
            batch_timeout_ms=getattr(config.execution, 'state_batch_timeout_ms', 100),
            enable_compression=getattr(config.execution, 'enable_state_compression', True)
        )
        
        # Initialize NodeUpdateManager based on execution strategy
        from sentientresearchagent.hierarchical_agent_framework.services import NodeUpdateManager
        self.update_manager = NodeUpdateManager.from_config(
            config.execution,
            knowledge_store=knowledge_store,
            websocket_handler=None  # Will be set by system manager if available
        )
        
        logger.info(f"ExecutionOrchestrator initialized with execution_strategy={config.execution.execution_strategy}")
    
    async def execute(
        self, 
        root_goal: str,
        max_steps: Optional[int] = None,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a task graph starting from a root goal.
        
        Args:
            root_goal: The main goal to achieve
            max_steps: Maximum execution steps (uses config default if not specified)
            execution_id: Optional execution ID for tracking
            
        Returns:
            Execution result dictionary
        """
        if self._is_running:
            raise SentientError("Execution already in progress")
            
        self._is_running = True
        self._execution_id = execution_id or self._generate_execution_id()
        
        logger.info(f"Starting execution {self._execution_id}: {root_goal}")
        
        try:
            # Initialize the root task
            root_node = await self._initialize_root_task(root_goal)
            if not root_node:
                return {"error": "Failed to initialize root task"}
            
            # Run the execution loop
            max_steps = max_steps or self.config.execution.max_execution_steps
            result = await self._execution_loop(max_steps)
            
            # Finalize execution
            final_result = await self._finalize_execution(result)
            
            # Ensure all state updates are flushed
            await self.batched_state_manager.flush_all()
            
            # Flush deferred updates for LightweightAgent
            if self.config.execution.execution_strategy == "deferred":
                logger.info("Flushing deferred updates...")
                await self.update_manager.flush_deferred_updates()
            
            logger.info(f"Execution {self._execution_id} completed")
            return final_result
            
        except Exception as e:
            logger.error(f"Execution {self._execution_id} failed: {e}")
            return {
                "error": str(e),
                "execution_id": self._execution_id,
                "stats": self._execution_stats
            }
        finally:
            # Ensure deferred updates are flushed even on error
            if hasattr(self, 'update_manager') and self.config.execution.execution_strategy == "deferred":
                try:
                    await self.update_manager.flush_deferred_updates()
                except Exception as flush_error:
                    logger.error(f"Error flushing deferred updates: {flush_error}")
            
            self._is_running = False
    
    async def _initialize_root_task(self, root_goal: str) -> Optional[TaskNode]:
        """Initialize the root task node."""
        try:
            # Create root node
            root_node = TaskNode(
                goal=root_goal,
                task_type=TaskType.WRITE,  # Default, can be customized
                node_type=NodeType.PLAN,   # Root typically starts with planning
                layer=0,
                task_id="root",
                overall_objective=root_goal
            )
            
            # Add to task graph
            root_graph_id = "root_graph"
            self.task_graph.add_graph(root_graph_id, is_root=True)
            self.task_graph.add_node_to_graph(root_graph_id, root_node)
            self.task_graph.overall_project_goal = root_goal
            
            # Log to knowledge store
            self.knowledge_store.add_or_update_record_from_node(root_node)
            
            # Transition root node to READY
            root_node.update_status(TaskStatus.READY, validate_transition=True)
            
            logger.info(f"Initialized root task: {root_node.task_id}")
            return root_node
            
        except Exception as e:
            logger.error(f"Failed to initialize root task: {e}")
            return None
    
    async def _execution_loop(self, max_steps: int) -> Dict[str, Any]:
        """
        Main execution loop with improved slot-filling mechanism.
        
        Args:
            max_steps: Maximum number of steps to execute
            
        Returns:
            Execution result
        """
        import time
        start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("🚀 EXECUTION FLOW STARTED")
        logger.info(f"⏱️ EXECUTION TIMEOUT: {self.config.execution.node_execution_timeout_seconds} seconds")
        logger.info("=" * 80)
        
        # Queue to track completed nodes
        completed_queue = asyncio.Queue()
        active_tasks = {}  # Track active processing tasks
        
        # Start the immediate-fill processor if enabled
        immediate_fill_task = None
        use_immediate_fill = getattr(self.config.execution, 'enable_immediate_slot_fill', True)
        
        if use_immediate_fill:
            max_concurrent = self._get_dynamic_concurrency()
            immediate_fill_task = asyncio.create_task(self._process_nodes_immediate_fill(max_concurrent))
            logger.info("🚀 IMMEDIATE SLOT FILL: Enabled - nodes will start as soon as slots become available")
        else:
            logger.info("📦 BATCH PROCESSING: Using traditional batch-based node processing")
        
        try:
            step = 0
            last_activity_time = time.time()
            iterations_without_work = 0  # Track consecutive iterations with no work
            
            while step < max_steps:
                # Check timeout
                elapsed_time = time.time() - start_time
                if elapsed_time > self.config.execution.node_execution_timeout_seconds:
                    logger.error(f"Execution timeout after {elapsed_time:.2f}s")
                    return {"error": f"Execution timeout after {elapsed_time:.2f}s"}
                
                # Track if we did any meaningful work this iteration
                did_work = False
                
                # Log status periodically, not every iteration
                if step % 10 == 0 or step == 0:
                    all_nodes = self.task_graph.get_all_nodes()
                    status_summary = {}
                    node_details = []
                    for node in all_nodes:
                        status_name = node.status.name
                        status_summary[status_name] = status_summary.get(status_name, 0) + 1
                        if node.status in [TaskStatus.READY, TaskStatus.PENDING]:
                            node_details.append(f"{node.task_id}:{node.status.name}")
                    
                    logger.info(f"\n📍 Step {step + 1}/{max_steps} | Time: {elapsed_time:.1f}s | Nodes: {status_summary}")
                    if node_details and step % 50 == 0:  # Log details less frequently
                        logger.debug(f"Non-executing nodes: {', '.join(node_details)}")
                
                # Update node readiness (transitions PENDING to READY when dependencies satisfied)
                transitioned = await self.task_scheduler.update_node_readiness()
                if transitioned > 0:
                    did_work = True
                    logger.info(f"✅ PENDING → READY: {transitioned} nodes transitioned")
                    # Batch update knowledge store for all newly ready nodes
                    ready_nodes_to_update = []
                    for node in self.task_graph.get_all_nodes():
                        if node.status == TaskStatus.READY:
                            ready_nodes_to_update.append(node)
                    
                    # Use batched update
                    for node in ready_nodes_to_update:
                        await self.batched_state_manager.update_node_state(node)
                
                # Check for nodes ready to aggregate (PLAN_DONE -> AGGREGATING)
                # Keep checking until no more transitions are possible (handles async subtask completion)
                aggregated_total = 0
                max_aggregate_iterations = 5
                
                # Track stuck nodes to prevent infinite loops
                if not hasattr(self, '_stuck_aggregation_nodes'):
                    self._stuck_aggregation_nodes = {}
                
                for agg_iter in range(max_aggregate_iterations):
                    aggregated_this_iter = 0
                    all_nodes = self.task_graph.get_all_nodes()
                    plan_done_nodes = [n for n in all_nodes if n.status == TaskStatus.PLAN_DONE]
                    
                    if not plan_done_nodes:
                        break
                        
                    for node in plan_done_nodes:
                        # Track how long this node has been stuck in PLAN_DONE
                        node_key = node.task_id
                        current_time = time.time()
                        
                        if node_key not in self._stuck_aggregation_nodes:
                            self._stuck_aggregation_nodes[node_key] = current_time
                        
                        stuck_duration = current_time - self._stuck_aggregation_nodes[node_key]
                        
                        # If stuck for more than 5 minutes, force transition or log detailed debug info
                        if stuck_duration > 300:  # 5 minutes
                            logger.error(f"🚨 INFINITE LOOP DETECTED: Node {node.task_id} stuck in PLAN_DONE for {stuck_duration:.1f}s")
                            # Force check with detailed logging
                            can_agg = self.state_manager.can_aggregate(node)
                            if not can_agg:
                                logger.error(f"🚨 Node {node.task_id} permanently blocked from aggregation - considering forced completion")
                                continue
                        
                        if self.state_manager.can_aggregate(node):
                            # Remove from stuck tracking since it can now progress
                            if node_key in self._stuck_aggregation_nodes:
                                del self._stuck_aggregation_nodes[node_key]
                                
                            # Transition to AGGREGATING  
                            try:
                                node.update_status(TaskStatus.AGGREGATING, validate_transition=True)
                                await self.batched_state_manager.update_node_state(node)
                                aggregated_this_iter += 1
                                logger.info(f"✅ PLAN_DONE → AGGREGATING: {node.task_id} (all subtasks complete)")
                            except Exception as e:
                                logger.warning(f"Failed to transition {node.task_id} to AGGREGATING: {e}")
                    
                    aggregated_total += aggregated_this_iter
                    
                    # If no transitions this iteration, stop checking
                    if aggregated_this_iter == 0:
                        break
                        
                    # Small delay to allow async operations to complete
                    await asyncio.sleep(0.05)
                
                if aggregated_total > 0:
                    did_work = True
                    logger.info(f"📊 Aggregation: {aggregated_total} nodes ready to aggregate results")
                
                if use_immediate_fill:
                    # Immediate-fill mode: processor handles node execution
                    # Main loop focuses on state management and monitoring
                    
                    # Check if the immediate-fill task is still running
                    if immediate_fill_task and immediate_fill_task.done():
                        # Check if it completed normally or with error
                        try:
                            await immediate_fill_task
                            logger.info("✅ Immediate-fill processor completed successfully")
                            break
                        except Exception as e:
                            logger.error(f"❌ Immediate-fill processor failed: {e}")
                            return {"error": f"Immediate-fill processor failed: {e}"}
                else:
                    # Traditional batch processing mode
                    all_nodes = self.task_graph.get_all_nodes()
                    running_nodes = [n for n in all_nodes if n.status == TaskStatus.RUNNING]
                    max_concurrent = self._get_dynamic_concurrency()
                    available_slots = max_concurrent - len(running_nodes)
                    
                    logger.debug(f"🔄 CONCURRENCY: {len(running_nodes)} running, {available_slots} slots available")
                    
                    # Get ready nodes and process them
                    if available_slots > 0:
                        ready_nodes = await self.task_scheduler.get_ready_nodes(max_nodes=available_slots)
                        if ready_nodes:
                            logger.info(f"📦 BATCH PROCESSING: {len(ready_nodes)} nodes")
                            processed_count = await self._process_nodes(ready_nodes)
                            self._execution_stats["nodes_processed"] += processed_count
                            
                            # Clear dependency cache
                            if processed_count > 0:
                                did_work = True
                                self.task_scheduler.clear_dependency_cache()
                    
                    # Check if execution is complete
                    if await self._is_execution_complete():
                        logger.info("✅ EXECUTION COMPLETE")
                        break
                    
                    # Small delay for batch mode
                    await asyncio.sleep(0.2)
            
                # Check for immediate aggregation triggers
                immediate_aggregation_count = await self._check_immediate_aggregation_triggers()
                if immediate_aggregation_count > 0:
                    did_work = True
                    logger.info(f"🚀 IMMEDIATE AGGREGATION: {immediate_aggregation_count} parents checked due to child completion")
                
                # Check for deadlock periodically (based on iterations, not steps)
                # This ensures deadlock detection runs even when no work is being done
                # IMPROVED: More frequent checks with escalating detection
                if iterations_without_work > 0:
                    # First check at 50 iterations (5 seconds) - quick detection
                    if iterations_without_work == 50:
                        logger.info("🔍 DEADLOCK CHECK (early): Running initial deadlock scan after 5s inactivity")
                        deadlock_info = await self.deadlock_detector.detect_deadlock()
                        if deadlock_info["is_deadlocked"]:
                            logger.warning(f"⚠️ Early deadlock detected: {deadlock_info['pattern']} - {deadlock_info['reason']}")
                            recovery_result = await self._attempt_deadlock_recovery(deadlock_info)
                            if recovery_result["recovered"]:
                                logger.info(f"✅ Early recovery successful: {recovery_result['action']}")
                                did_work = True

                    # Regular checks every 50 iterations after the first check
                    elif iterations_without_work % 50 == 0:  # Check every 50 iterations (5 seconds)
                        logger.info(f"🔍 DEADLOCK CHECK: Running deadlock detection ({time_since_activity:.1f}s inactivity)")
                        deadlock_info = await self.deadlock_detector.detect_deadlock()
                        if deadlock_info["is_deadlocked"]:
                            logger.warning(f"🚨 DEADLOCK DETECTED: {deadlock_info['pattern']} - {deadlock_info['reason']}")
                            recovery_result = await self._attempt_deadlock_recovery(deadlock_info)
                            if not recovery_result["recovered"]:
                                logger.error(f"❌ Deadlock recovery failed after {time_since_activity:.1f}s: {deadlock_info['reason']}")
                                # Don't give up immediately - let it try a few more times
                                if iterations_without_work > 200:  # After 20 seconds of failed recovery
                                    if immediate_fill_task:
                                        immediate_fill_task.cancel()
                                    return {"error": f"Deadlock: {deadlock_info['reason']} (recovery failed after {time_since_activity:.1f}s)"}
                            else:
                                logger.info(f"✅ Recovered from deadlock: {recovery_result['action']}")
                                did_work = True  # Recovery counts as work
                                iterations_without_work = 0  # Reset counter after successful recovery

                # Also check periodically during normal operation
                elif step % 50 == 0 and step > 0:
                    deadlock_info = await self.deadlock_detector.detect_deadlock()
                    if deadlock_info["is_deadlocked"]:
                        logger.warning(f"🚨 DEADLOCK during normal operation: {deadlock_info['pattern']}")
                        recovery_result = await self._attempt_deadlock_recovery(deadlock_info)
                        if not recovery_result["recovered"]:
                            logger.error(f"❌ Deadlock recovery failed: {deadlock_info['reason']}")
                            if immediate_fill_task:
                                immediate_fill_task.cancel()
                            return {"error": f"Deadlock: {deadlock_info['reason']}"}
                        else:
                            logger.info(f"✅ Recovered from deadlock: {recovery_result['action']}")
                            did_work = True
                
                # In immediate-fill mode, wait longer since the processor handles execution
                if use_immediate_fill:
                    # Wait for either completion or significant time to pass
                    await asyncio.sleep(1.0)  # Check status every second
                else:
                    # Traditional mode - shorter delay
                    await asyncio.sleep(0.1)
                
                # Create checkpoint if needed
                if self.checkpoint_manager and self.checkpoint_manager.should_checkpoint():
                    await self._create_checkpoint(step)
                
                # Only increment step if we did meaningful work
                if did_work:
                    step += 1
                    self._execution_stats["steps_executed"] = step
                    last_activity_time = time.time()
                    iterations_without_work = 0  # Reset counter
                    logger.debug(f"✅ Step {step}: Work completed")
                else:
                    # No work done - track consecutive iterations without work
                    iterations_without_work += 1
                    
                    # Check if we're stuck
                    time_since_activity = time.time() - last_activity_time
                    
                    # Log warnings at appropriate intervals (IMPROVED: faster escalation)
                    if iterations_without_work == 100:  # 10 seconds of waiting
                        logger.info(f"⏳ Waiting for nodes to complete... ({time_since_activity:.1f}s since last activity)")
                    elif iterations_without_work == 200:  # 20 seconds (reduced from 30)
                        logger.warning(f"⚠️ Long wait detected: {time_since_activity:.1f}s since last activity")
                    elif iterations_without_work > 300:  # 30 seconds (reduced from 60)
                        # Check if we have any running nodes
                        all_nodes = self.task_graph.get_all_nodes()
                        running_nodes = [n for n in all_nodes if n.status == TaskStatus.RUNNING]
                        if running_nodes:
                            logger.info(f"🔄 Still waiting for {len(running_nodes)} running nodes to complete")
                            # Reset the counter to avoid spam
                            iterations_without_work = 100
                        else:
                            logger.error(f"❌ No activity for {time_since_activity:.1f}s with no running nodes - system may be stuck")
                            break
        
            # Check if we hit max steps
            if step >= max_steps:
                if immediate_fill_task:
                    immediate_fill_task.cancel()
                active_nodes = await self.task_scheduler.get_active_nodes()
                if active_nodes:
                    logger.warning(f"Reached max steps ({max_steps}) with {len(active_nodes)} active nodes")
                    # Provide more details about the active nodes
                    for node in active_nodes[:5]:  # Show up to 5 nodes
                        logger.warning(f"  - {node.task_id}: {node.status.name} - {node.goal[:50]}...")
                    return {"error": f"Reached max steps ({max_steps}) with {len(active_nodes)} active nodes remaining"}
            
            # Check if execution completed successfully
            if await self._is_execution_complete():
                logger.info(f"✅ Execution completed successfully after {step} steps")
                return {"success": True}
            
            # If we exited due to no activity
            logger.warning(f"Execution loop exited after {step} steps")
            return {"success": True}
            
        finally:
            # Ensure the immediate-fill task is cancelled if still running
            if immediate_fill_task and not immediate_fill_task.done():
                immediate_fill_task.cancel()
                try:
                    await immediate_fill_task
                except asyncio.CancelledError:
                    logger.info("Immediate-fill processor cancelled")
    
    async def _process_nodes_immediate_fill(self, max_concurrent: int) -> None:
        """
        Process nodes with immediate slot filling - as soon as one finishes, another starts.
        This runs continuously in the background during execution.
        
        Args:
            max_concurrent: Maximum number of concurrent nodes
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        active_tasks = set()
        processed_count = 0
        
        async def process_node_with_tracking(node: TaskNode) -> None:
            """Process a node and track its completion."""
            try:
                async with semaphore:
                    logger.info(f"🟢 SLOT ACQUIRED: Starting node {node.task_id} immediately")
                    start_time = asyncio.get_event_loop().time()
                    
                    success = await self._process_single_node(node)
                    
                    duration = asyncio.get_event_loop().time() - start_time
                    if success:
                        logger.info(f"✅ SLOT FREED: Node {node.task_id} completed in {duration:.2f}s - slot now available")
                        self._execution_stats["nodes_processed"] += 1
                    else:
                        logger.warning(f"❌ SLOT FREED: Node {node.task_id} failed after {duration:.2f}s - slot now available")
                    
                    return success
            except Exception as e:
                logger.error(f"❌ SLOT FREED: Node {node.task_id} errored: {e} - slot now available")
                return False
        
        while True:
            # Try to fill any available slots immediately
            available_slots = max_concurrent - len(active_tasks)
            
            if available_slots > 0:
                # Get nodes to fill available slots
                ready_nodes = await self.task_scheduler.get_ready_nodes(max_nodes=available_slots)
                
                if ready_nodes:
                    logger.info(f"🔥 IMMEDIATE FILL: Found {len(ready_nodes)} nodes to fill {available_slots} available slots")
                    
                    # Start processing immediately without waiting
                    for node in ready_nodes:
                        task = asyncio.create_task(process_node_with_tracking(node))
                        active_tasks.add(task)
                        processed_count += 1
                    
                    # Clear dependency cache since graph may have changed
                    self.task_scheduler.clear_dependency_cache()
                
                elif await self._is_execution_complete() and len(active_tasks) == 0:
                    # No more work and no active tasks
                    logger.info(f"✅ Immediate fill processor completed. Total nodes processed: {processed_count}")
                    break
            
            # Wait for any task to complete (this frees up a slot)
            if active_tasks:
                done, pending = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                active_tasks = pending
                
                # Log slot availability
                if done:
                    logger.info(f"🔄 SLOTS UPDATE: {len(done)} task(s) completed, {len(pending)} still running, {max_concurrent - len(pending)} slots now available")
            else:
                # No active tasks, wait a bit before checking for new work
                await asyncio.sleep(0.1)
    
    async def _process_nodes(self, nodes: list[TaskNode]) -> int:
        """
        Process a batch of nodes with true parallel execution.
        
        Args:
            nodes: Nodes to process
            
        Returns:
            Number of nodes successfully processed
        """
        processed = 0
        
        # Get parallel processing configuration - use dynamic concurrency
        max_parallel = getattr(self.config.execution, 'max_parallel_nodes', self._get_dynamic_concurrency())
        
        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def process_with_semaphore(node: TaskNode) -> bool:
            """Process a node with semaphore control."""
            async with semaphore:
                return await self._process_single_node(node)
        
        # Sort nodes by priority (layer, then creation time)
        sorted_nodes = sorted(nodes, key=lambda n: (n.layer, n.timestamp_created))
        
        # Create all tasks immediately for true parallel execution
        tasks = []
        for node in sorted_nodes:
            # Create task without awaiting - allows immediate parallel execution
            task = asyncio.create_task(process_with_semaphore(node))
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful processings and log failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Node {sorted_nodes[i].task_id} processing failed: {result}")
            else:
                processed += 1
        
        # Log processing stats
        if processed < len(nodes):
            logger.warning(f"Processed {processed}/{len(nodes)} nodes successfully")
        else:
            logger.info(f"Successfully processed all {processed} nodes in parallel")
        
        return processed
    
    async def _check_immediate_aggregation_triggers(self) -> int:
        """
        Check for immediate aggregation triggers from recently completed child nodes.
        This provides faster response than waiting for the next cycle iteration.
        
        Returns:
            Number of parent nodes checked for immediate aggregation
        """
        checked_parents = 0
        
        # Get all nodes and check for aggregation triggers
        all_nodes = self.task_graph.get_all_nodes()
        
        for node in all_nodes:
            # Check if this node has an aggregation trigger in its aux_data
            if (hasattr(node, 'aux_data') and node.aux_data and 
                'trigger_parent_aggregation_check' in node.aux_data):
                
                trigger_info = node.aux_data['trigger_parent_aggregation_check']
                parent_id = trigger_info.get('parent_id')
                child_id = trigger_info.get('child_id')
                
                if parent_id:
                    parent_node = self.task_graph.get_node(parent_id)
                    if parent_node and parent_node.status == TaskStatus.PLAN_DONE:
                        logger.info(f"🔍 IMMEDIATE CHECK: Child {child_id} completed, checking if parent {parent_id} can aggregate")
                        
                        # Check if parent can now aggregate
                        if self.state_manager.can_aggregate(parent_node):
                            try:
                                parent_node.update_status(TaskStatus.AGGREGATING, validate_transition=True)
                                self.knowledge_store.add_or_update_record_from_node(parent_node)
                                logger.info(f"✅ IMMEDIATE AGGREGATION: Parent {parent_id} transitioned to AGGREGATING due to child {child_id} completion")
                                checked_parents += 1
                            except Exception as e:
                                logger.warning(f"Failed immediate aggregation transition for {parent_id}: {e}")
                        else:
                            logger.debug(f"Parent {parent_id} not ready to aggregate yet (other children still running)")
                    
                    # Clear the trigger to avoid duplicate processing
                    del node.aux_data['trigger_parent_aggregation_check']
        
        return checked_parents
    
    async def _process_single_node(self, node: TaskNode) -> bool:
        """
        Process a single node with error recovery and performance tracking.
        
        Args:
            node: Node to process
            
        Returns:
            True if successful, False otherwise
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Process the node with update manager
            await self.node_processor.process_node(
                node, 
                self.task_graph, 
                self.knowledge_store,
                self.update_manager
            )
            
            # Track successful processing time
            processing_time = asyncio.get_event_loop().time() - start_time
            self._processing_times.append(processing_time)
            
            logger.debug(f"Node {node.task_id} processed in {processing_time:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Error processing node {node.task_id}: {e}")
            
            # Check for rate limit errors and adjust concurrency
            if "rate limit" in str(e).lower():
                await self._adjust_concurrency(e)
            
            # Attempt recovery
            recovery_strategy = self.recovery_manager.get_strategy_for_error(e)
            if recovery_strategy:
                recovery_result = await recovery_strategy.recover(node, e)
                if recovery_result.recovered:
                    self._execution_stats["errors_recovered"] += 1
                    logger.info(f"Recovered from error in node {node.task_id}: {recovery_result.action}")
                    
                    # Track recovery time
                    processing_time = asyncio.get_event_loop().time() - start_time
                    self._processing_times.append(processing_time)
                    return True
            
            # Recovery failed - mark node as failed
            node.fail_with_error(e, {"recovery_attempted": True})
            await self.batched_state_manager.update_node_state(node, immediate=True)  # Immediate for failures
            return False
    
    async def _is_execution_complete(self) -> bool:
        """Check if the execution is complete."""
        active_nodes = await self.task_scheduler.get_active_nodes()
        
        # Also check for PLAN_DONE nodes that might transition to AGGREGATING
        all_nodes = self.task_graph.get_all_nodes()
        plan_done_nodes = [n for n in all_nodes if n.status == TaskStatus.PLAN_DONE]
        
        # If there are PLAN_DONE nodes, check if any could potentially aggregate
        for node in plan_done_nodes:
            if self.state_manager.can_aggregate(node):
                # This node can still progress
                return False
                
        return len(active_nodes) == 0 and len(plan_done_nodes) == 0
    
    async def _attempt_deadlock_recovery(self, deadlock_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to recover from a deadlock.
        
        Args:
            deadlock_info: Information about the deadlock
            
        Returns:
            Recovery result with 'recovered' and 'action' keys
        """
        recovery_strategy = self.recovery_manager.get_deadlock_recovery_strategy()
        if recovery_strategy:
            result = await recovery_strategy.recover_from_deadlock(
                deadlock_info,
                self.task_graph,
                self.state_manager
            )
            if result["recovered"]:
                self._execution_stats["errors_recovered"] += 1
            return result
        
        return {"recovered": False, "action": "No recovery strategy available"}
    
    async def _create_checkpoint(self, step: int) -> None:
        """Create an execution checkpoint."""
        if not self.checkpoint_manager:
            return
            
        try:
            metadata = {
                "execution_id": self._execution_id,
                "step": step,
                "stats": self._execution_stats.copy()
            }
            
            self.checkpoint_manager.create_checkpoint(
                self.task_graph,
                self.knowledge_store,
                metadata
            )
            
            self._execution_stats["checkpoints_created"] += 1
            logger.info(f"Created checkpoint at step {step}")
            
        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
    
    async def _finalize_execution(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Finalize the execution and prepare the result.
        
        Args:
            execution_result: Raw execution result
            
        Returns:
            Final execution result
        """
        # Get root node result
        root_node = self.task_graph.get_node("root")
        
        if not root_node:
            return {
                "error": "Root node not found",
                "execution_id": self._execution_id,
                "stats": self._execution_stats
            }
        
        # Prepare final result
        final_result = {
            "execution_id": self._execution_id,
            "status": "success" if execution_result.get("success") else "failed",
            "stats": self._execution_stats
        }
        
        if root_node.status == TaskStatus.DONE:
            final_result["result"] = root_node.result
            final_result["summary"] = root_node.output_summary
        elif root_node.status == TaskStatus.AGGREGATING:
            # For nodes that finished aggregation but didn't transition to DONE
            if root_node.result:
                final_result["result"] = root_node.result
                final_result["summary"] = root_node.output_summary or "Aggregation completed"
            else:
                final_result["error"] = "Node in AGGREGATING state but has no result"
        elif root_node.status == TaskStatus.FAILED:
            final_result["error"] = root_node.error or "Task failed"
        else:
            final_result["error"] = f"Unexpected final status: {root_node.status}"
        
        # Add any error from execution
        if "error" in execution_result:
            final_result["execution_error"] = execution_result["error"]
        
        return final_result
    
    def _generate_execution_id(self) -> str:
        """Generate a unique execution ID."""
        import uuid
        return f"exec_{uuid.uuid4().hex[:8]}"
    
    async def resume_from_checkpoint(
        self, 
        checkpoint_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Resume execution from a checkpoint.
        
        Args:
            checkpoint_path: Path to checkpoint file (uses latest if not specified)
            
        Returns:
            Execution result
        """
        if not self.checkpoint_manager:
            return {"error": "Checkpoint manager not configured"}
        
        # Load checkpoint
        checkpoint_data = self.checkpoint_manager.load_checkpoint(checkpoint_path)
        if not checkpoint_data:
            return {"error": "Failed to load checkpoint"}
        
        task_graph, knowledge_store, metadata = checkpoint_data
        
        # Update state
        self.task_graph = task_graph
        self.knowledge_store = knowledge_store
        self._execution_id = metadata.get("execution_id", self._generate_execution_id())
        self._execution_stats = metadata.get("stats", self._execution_stats)
        
        logger.info(f"Resumed from checkpoint at step {metadata.get('step', 'unknown')}")
        
        # Continue execution
        return await self._execution_loop(self.config.execution.max_execution_steps)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get current execution statistics."""
        stats = self._execution_stats.copy()
        stats["current_concurrency"] = self._current_concurrency
        stats["rate_limit_errors"] = self._rate_limit_errors
        return stats
    
    async def _adjust_concurrency(self, error: Optional[Exception] = None) -> None:
        """
        Dynamically adjust concurrency based on system performance and errors.
        
        Args:
            error: Optional error that triggered adjustment
        """
        async with self._concurrency_lock:
            max_concurrency = self.config.execution.max_concurrent_nodes
            min_concurrency = max(1, max_concurrency // 4)
            
            if error and "rate limit" in str(error).lower():
                # Rate limit error - reduce concurrency
                self._rate_limit_errors += 1
                self._last_rate_limit_time = asyncio.get_event_loop().time()
                
                # Exponential backoff for concurrency
                new_concurrency = max(min_concurrency, self._current_concurrency // 2)
                if new_concurrency < self._current_concurrency:
                    logger.warning(f"Rate limit detected - reducing concurrency from {self._current_concurrency} to {new_concurrency}")
                    self._current_concurrency = new_concurrency
            
            elif self._last_rate_limit_time:
                # Check if we can increase concurrency again
                time_since_rate_limit = asyncio.get_event_loop().time() - self._last_rate_limit_time
                if time_since_rate_limit > 60:  # 1 minute cooldown
                    # Gradually increase concurrency
                    new_concurrency = min(max_concurrency, self._current_concurrency + 1)
                    if new_concurrency > self._current_concurrency:
                        logger.info(f"No recent rate limits - increasing concurrency from {self._current_concurrency} to {new_concurrency}")
                        self._current_concurrency = new_concurrency
                        
            # Adjust based on processing times
            if len(self._processing_times) >= 10:
                avg_time = sum(self._processing_times) / len(self._processing_times)
                
                # If processing is very fast, we might be able to handle more
                if avg_time < 1.0 and self._rate_limit_errors == 0:
                    new_concurrency = min(max_concurrency, self._current_concurrency + 1)
                    if new_concurrency > self._current_concurrency:
                        logger.info(f"Fast processing detected - increasing concurrency to {new_concurrency}")
                        self._current_concurrency = new_concurrency
                
                # Keep only recent times
                self._processing_times = self._processing_times[-20:]
    
    def _get_dynamic_concurrency(self) -> int:
        """Get current dynamic concurrency limit."""
        return self._current_concurrency


