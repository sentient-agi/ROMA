from loguru import logger
from typing import TYPE_CHECKING
from sentientresearchagent.hierarchical_agent_framework.node.task_node import TaskNode, TaskType, NodeType
from sentientresearchagent.hierarchical_agent_framework.context.knowledge_store import KnowledgeStore
from sentientresearchagent.hierarchical_agent_framework.context.agent_io_models import PlanOutput

if TYPE_CHECKING:
    from sentientresearchagent.hierarchical_agent_framework.graph.task_graph import TaskGraph

class SubNodeCreator:
    """
    Responsible for creating sub-TaskNodes based on a plan and adding them
    to the TaskGraph and KnowledgeStore.
    """
    def __init__(self, task_graph: "TaskGraph", knowledge_store: KnowledgeStore):
        self.task_graph = task_graph
        self.knowledge_store = knowledge_store

    def create_sub_nodes(self, parent_node: TaskNode, plan_output: PlanOutput):
        """
        Creates TaskNode instances from a plan list, adds them to the graph,
        sets up dependencies based on `depends_on_indices`, and updates the parent_node.
        """
        if not parent_node.sub_graph_id:
            parent_node.sub_graph_id = f"subgraph_{parent_node.task_id}"

            # If a stale graph somehow exists (e.g., after partial recovery), remove it first
            if self.task_graph.get_graph(parent_node.sub_graph_id):
                logger.warning(
                    f"    SubNodeCreator: Found existing graph '{parent_node.sub_graph_id}' before creation. Removing stale graph to avoid ID collisions."
                )
                self.task_graph.remove_graph_and_nodes(parent_node.sub_graph_id, self.knowledge_store)

            self.task_graph.add_graph(parent_node.sub_graph_id)
            logger.info(f"    SubNodeCreator: Created new subgraph '{parent_node.sub_graph_id}' for parent '{parent_node.task_id}'")
            # CRITICAL: Update parent node in knowledge store after setting sub_graph_id
            self.knowledge_store.add_or_update_record_from_node(parent_node)
            logger.debug(f"    SubNodeCreator: Updated parent node in knowledge store with sub_graph_id")
        
        sub_graph_id = parent_node.sub_graph_id
        parent_node.planned_sub_task_ids.clear()

        created_sub_nodes: list[TaskNode] = []

        for i, sub_task_def in enumerate(plan_output.sub_tasks):
            sub_node_id = f"{parent_node.task_id}.{i+1}" # Simple sequential ID based on order in plan

            try:
                task_type_enum = TaskType[sub_task_def.task_type.upper()]
                # Use default node_type if not provided by planner (since planners no longer output node_type)
                node_type_enum = NodeType[sub_task_def.node_type.upper()] if sub_task_def.node_type else NodeType.PLAN
            except KeyError as e:
                error_msg = f"Invalid task_type or node_type string ('{sub_task_def.task_type}'/'{getattr(sub_task_def, 'node_type', 'PLAN')}') in plan for parent {parent_node.task_id}: {e}"
                logger.error(f"    SubNodeCreator Error: {error_msg}")
                continue # Skip this sub-task if types are invalid

            sub_node = TaskNode(
                goal=sub_task_def.goal,
                task_type=task_type_enum,
                node_type=node_type_enum,
                task_id=sub_node_id,
                layer=parent_node.layer + 1,
                parent_node_id=parent_node.task_id,
                overall_objective=parent_node.overall_objective
                # agent_name can also be part of sub_task_def if planner assigns specific agents
            )
            created_sub_nodes.append(sub_node)
            self.task_graph.add_node_to_graph(sub_graph_id, sub_node)
            self.knowledge_store.add_or_update_record_from_node(sub_node)
            parent_node.planned_sub_task_ids.append(sub_node.task_id)
            logger.success(f"      SubNodeCreator: Added sub-node: {sub_node.task_id} ('{sub_node.goal[:30]}...') to graph {sub_graph_id}")

        # Add dependencies based on the 'depends_on_indices' field
        for i, sub_node in enumerate(created_sub_nodes):
            sub_task_def = plan_output.sub_tasks[i] # Get the corresponding sub_task_def
            if hasattr(sub_task_def, 'depends_on_indices') and sub_task_def.depends_on_indices:
                # CRITICAL FIX: Store depends_on_indices in the TaskNode's aux_data
                sub_node.aux_data['depends_on_indices'] = sub_task_def.depends_on_indices
                logger.info(f"      SubNodeCreator: Stored depends_on_indices {sub_task_def.depends_on_indices} in aux_data for node {sub_node.task_id}")
                
                for dep_index in sub_task_def.depends_on_indices:
                    if 0 <= dep_index < len(created_sub_nodes) and dep_index != i: # Ensure valid index and not self-dependent
                        dependency_node = created_sub_nodes[dep_index]
                        self.task_graph.add_edge(sub_graph_id, dependency_node.task_id, sub_node.task_id)
                        logger.info(f"      SubNodeCreator: Added dependency edge: {dependency_node.task_id} -> {sub_node.task_id} in graph {sub_graph_id}")
                    else:
                        logger.warning(f"    SubNodeCreator: Invalid dependency index {dep_index} for sub-task {sub_node.task_id} (index {i}). Skipping this dependency.")
            else:
                # CRITICAL FIX: Store empty depends_on_indices for nodes with no dependencies
                sub_node.aux_data['depends_on_indices'] = []
                logger.debug(f"      SubNodeCreator: No dependencies for node {sub_node.task_id}, stored empty depends_on_indices")
            
            # CRITICAL FIX: Update knowledge store to ensure dependency information is immediately available
            self.knowledge_store.add_or_update_record_from_node(sub_node)
            logger.debug(f"      SubNodeCreator: Updated knowledge store with dependency info for node {sub_node.task_id}")
            
            # If depends_on_indices is empty or not present, the node has no explicit dependencies on its siblings in this plan.
            # It will become READY once its parent (the PLAN node) is PLAN_DONE.

        logger.info(f"    SubNodeCreator: Created {len(created_sub_nodes)} sub-nodes for parent {parent_node.task_id} with specified dependencies.")
        
        # CRITICAL: Update parent node in knowledge store after modifying planned_sub_task_ids
        self.knowledge_store.add_or_update_record_from_node(parent_node)
        logger.debug(f"    SubNodeCreator: Updated parent node in knowledge store with planned_sub_task_ids")
        
        return created_sub_nodes
