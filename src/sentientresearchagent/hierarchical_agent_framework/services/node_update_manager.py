"""
NodeUpdateManager - Manages node state updates with agent-aware optimization.

This service provides different update strategies based on the agent type:
- ProfiledSentientAgent: Real-time updates with optimization
- LightweightSentientAgent: Deferred updates for minimal overhead
"""

import threading
import asyncio
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING
from datetime import datetime
from collections import defaultdict
from loguru import logger
import json

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode
    from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
    from sentientresearchagent.config import ExecutionConfig


class UpdateEntry:
    """Represents a single update entry."""
    def __init__(self, node_id: str, update_type: str, data: Dict[str, Any], timestamp: datetime):
        self.node_id = node_id
        self.update_type = update_type
        self.data = data
        self.timestamp = timestamp


class NodeUpdateManager:
    """
    Manages node updates with different strategies based on agent type.
    
    Strategies:
    - REALTIME: Immediate updates with optimization (ProfiledSentientAgent)
    - DEFERRED: Queue updates until after LLM calls (LightweightSentientAgent)
    - STANDARD: Current behavior without optimization
    """
    
    def __init__(
        self, 
        execution_strategy: str,
        broadcast_mode: str,
        enable_coalescing: bool = True,
        coalescing_window_ms: int = 50,
        knowledge_store: Optional["KnowledgeStore"] = None,
        websocket_handler: Optional[Any] = None,
        project_id: Optional[str] = None,
        broadcast_room: Optional[str] = None
    ):
        """
        Initialize NodeUpdateManager.
        
        Args:
            execution_strategy: "realtime", "deferred", or "standard"
            broadcast_mode: "full", "batch", or "none"
            enable_coalescing: Whether to coalesce rapid updates
            coalescing_window_ms: Window for coalescing updates
            knowledge_store: Knowledge store instance
            websocket_handler: WebSocket handler for broadcasts
        """
        self.execution_strategy = execution_strategy
        self.broadcast_mode = broadcast_mode
        self.enable_coalescing = enable_coalescing
        self.coalescing_window_ms = coalescing_window_ms
        self.knowledge_store = knowledge_store
        self.websocket_handler = websocket_handler
        self.project_id = project_id
        self._broadcast_room_override = broadcast_room
        
        # Thread-local storage for deferred updates
        self._thread_local = threading.local()
        
        # Coalescing state
        self._coalesce_buffer: Dict[str, List[UpdateEntry]] = defaultdict(list)
        self._coalesce_lock = threading.Lock()
        self._coalesce_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._stats = {
            "updates_processed": 0,
            "updates_coalesced": 0,
            "updates_deferred": 0,
            "batches_flushed": 0
        }
        
        logger.info(f"NodeUpdateManager initialized: strategy={execution_strategy}, broadcast={broadcast_mode}")
    
    def set_project_scope(
        self,
        project_id: Optional[str] = None,
        room: Optional[str] = None
    ) -> None:
        """Set or update the broadcast scope for this update manager."""
        if project_id is not None:
            self.project_id = project_id
        if room is not None:
            self._broadcast_room_override = room
    
    def configure_websocket(
        self,
        handler: Any,
        project_id: Optional[str] = None,
        room: Optional[str] = None
    ) -> None:
        """Configure the websocket handler and optional broadcast scope."""
        self.websocket_handler = handler
        self.set_project_scope(project_id=project_id, room=room)
    
    def _get_deferred_queue(self) -> List[UpdateEntry]:
        """Get thread-local deferred queue."""
        if not hasattr(self._thread_local, 'deferred_queue'):
            self._thread_local.deferred_queue = []
        return self._thread_local.deferred_queue
    
    async def update_node_state(
        self, 
        node: "TaskNode", 
        update_type: str, 
        data: Dict[str, Any]
    ) -> None:
        """
        Update node state based on configured strategy.
        
        Args:
            node: Node to update
            update_type: Type of update (e.g., "status", "result", "progress")
            data: Update data
        """
        self._stats["updates_processed"] += 1
        
        # Create update entry
        entry = UpdateEntry(
            node_id=node.task_id,
            update_type=update_type,
            data=data,
            timestamp=datetime.now()
        )
        
        if self.execution_strategy == "deferred":
            # LightweightAgent - defer all updates
            await self._defer_update(entry)
        elif self.execution_strategy == "realtime":
            # ProfiledSentientAgent - immediate but optimized
            await self._optimized_immediate_update(node, entry)
        else:
            # Standard - current behavior
            await self._standard_update(node, entry)
    
    async def _defer_update(self, entry: UpdateEntry) -> None:
        """Defer update for later processing (LightweightAgent)."""
        queue = self._get_deferred_queue()
        queue.append(entry)
        self._stats["updates_deferred"] += 1
        logger.debug(f"Deferred {entry.update_type} update for node {entry.node_id}")
    
    async def _optimized_immediate_update(self, node: "TaskNode", entry: UpdateEntry) -> None:
        """
        Optimized immediate update for ProfiledSentientAgent.
        
        Features:
        - Update coalescing
        - Differential updates
        - Compressed payloads
        """
        if self.enable_coalescing and entry.update_type in ["status", "progress"]:
            # Add to coalesce buffer
            with self._coalesce_lock:
                self._coalesce_buffer[entry.node_id].append(entry)
                
                # Start coalesce timer if not running
                if not self._coalesce_task or self._coalesce_task.done():
                    self._coalesce_task = asyncio.create_task(
                        self._coalesce_timer()
                    )
            
            self._stats["updates_coalesced"] += 1
        else:
            # Immediate update for critical changes
            await self._apply_single_update(node, entry)
    
    async def _standard_update(self, node: "TaskNode", entry: UpdateEntry) -> None:
        """Standard update without optimization."""
        await self._apply_single_update(node, entry)
    
    async def _apply_single_update(self, node: "TaskNode", entry: UpdateEntry) -> None:
        """Apply a single update immediately."""
        # Update knowledge store if available
        if self.knowledge_store and entry.update_type in ["status", "result"]:
            self.knowledge_store.add_or_update_record_from_node(node)
        
        # Broadcast if needed
        if self.broadcast_mode == "full" and self.websocket_handler:
            await self._broadcast_update(node, entry)
    
    async def _coalesce_timer(self) -> None:
        """Timer for coalescing updates."""
        await asyncio.sleep(self.coalescing_window_ms / 1000.0)
        
        # Process coalesced updates
        with self._coalesce_lock:
            if self._coalesce_buffer:
                await self._flush_coalesced_updates()
    
    async def _flush_coalesced_updates(self) -> None:
        """Flush coalesced updates."""
        for node_id, entries in self._coalesce_buffer.items():
            if entries:
                # Combine updates
                combined_entry = self._combine_entries(entries)
                
                # Apply combined update
                # Note: We need the actual node object here
                # This is a limitation we'll address in integration
                if self.websocket_handler and self.broadcast_mode != "none":
                    await self._broadcast_combined_update(node_id, combined_entry)
        
        self._coalesce_buffer.clear()
    
    def _combine_entries(self, entries: List[UpdateEntry]) -> UpdateEntry:
        """Combine multiple update entries into one."""
        if not entries:
            return None
            
        # Take the latest entry as base
        combined = entries[-1]
        
        # Merge data from all entries
        merged_data = {}
        for entry in entries:
            merged_data.update(entry.data)
        
        combined.data = merged_data
        return combined
    
    async def _broadcast_update(self, node: "TaskNode", entry: UpdateEntry) -> None:
        """Broadcast a single update."""
        if self.broadcast_mode == "none":
            return
        
        payload = {
            "type": f"node_{entry.update_type}",
            "node_id": entry.node_id,
            "data": entry.data,
            "timestamp": entry.timestamp.isoformat()
        }
        
        # Differential update - only send what changed
        if entry.update_type == "status":
            payload["data"] = {
                "status": entry.data.get("new_status"),
                "old_status": entry.data.get("old_status")
            }
        
        await self._emit_websocket_event("node_update", payload)
    
    async def _broadcast_combined_update(self, node_id: str, entry: UpdateEntry) -> None:
        """Broadcast a combined update."""
        payload = {
            "type": "node_update_batch",
            "node_id": node_id,
            "updates": entry.data,
            "timestamp": entry.timestamp.isoformat()
        }
        
        await self._emit_websocket_event("node_update_batch", payload)
    
    async def flush_deferred_updates(self) -> None:
        """
        Flush all deferred updates (for LightweightAgent).
        
        This is called after LLM operations complete.
        """
        queue = self._get_deferred_queue()
        if not queue:
            return
            
        logger.info(f"Flushing {len(queue)} deferred updates")
        
        # Group by node for efficient knowledge store updates
        updates_by_node: Dict[str, List[UpdateEntry]] = defaultdict(list)
        for entry in queue:
            updates_by_node[entry.node_id].append(entry)
        
        # Batch update knowledge store
        if self.knowledge_store:
            # Note: We need node objects here
            # This will be resolved in integration
            logger.debug(f"Would batch update {len(updates_by_node)} nodes in knowledge store")
        
        # Clear the queue
        queue.clear()
        self._stats["batches_flushed"] += 1
    
    def get_stats(self) -> Dict[str, int]:
        """Get update manager statistics."""
        return self._stats.copy()
    
    @classmethod
    def from_config(cls, config: "ExecutionConfig", **kwargs) -> "NodeUpdateManager":
        """
        Create NodeUpdateManager from ExecutionConfig.
        
        Args:
            config: Execution configuration
            **kwargs: Additional arguments (knowledge_store, websocket_handler)
        """
        return cls(
            execution_strategy=config.execution_strategy,
            broadcast_mode=config.broadcast_mode,
            enable_coalescing=config.enable_update_coalescing,
            coalescing_window_ms=config.update_coalescing_window_ms,
            **kwargs
        )
    
    def _get_broadcast_room(self) -> Optional[str]:
        """Derive the websocket room name, if any."""
        if self._broadcast_room_override:
            return self._broadcast_room_override
        if self.project_id:
            return f"project_{self.project_id}"
        return None
    
    async def _emit_websocket_event(self, event: str, payload: Any) -> None:
        """Emit a websocket event using the configured handler."""
        handler = self.websocket_handler
        if not handler or self.broadcast_mode == "none":
            return
        
        try:
            if hasattr(handler, "broadcast_to_project") and self.project_id:
                await handler.broadcast_to_project(self.project_id, event, payload)
                return
            
            room = self._get_broadcast_room()
            
            if hasattr(handler, "emit"):
                try:
                    await handler.emit(event, payload, room=room)
                except TypeError:
                    # Fallback in case the emit signature doesn't support room kwarg
                    await handler.emit(event, payload)
                return
            
            if hasattr(handler, "broadcast_to_room"):
                target_room = room or "default"
                await handler.broadcast_to_room(target_room, payload)
                return
            
            # As a last resort, attempt to call handler directly if it's callable
            if callable(handler):
                maybe_coro = handler(event, payload)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
        except Exception as exc:
            logger.warning(f"Failed to emit websocket event '{event}': {exc}")
