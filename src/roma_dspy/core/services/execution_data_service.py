"""Service layer for consolidating execution data from MLflow.

This service implements SOLID principles:
- Single Responsibility: Only consolidates data (no fetching, no formatting)
- Dependency Inversion: Uses MLflowClient for data access
- Separation of Concerns: Pure business logic, no presentation code

Extracted from LLMTraceVisualizer to create proper layering:
  Data Access (MLflowClient) → Business Logic (ExecutionDataService) → Presentation (LLMTraceVisualizer)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from roma_dspy.core.observability.mlflow_client import MLflowClient


class ExecutionDataService:
    """
    Service for consolidating MLflow execution data into structured format.

    This class contains ALL the consolidation logic previously in LLMTraceVisualizer.
    Visualizer should call this service, not implement consolidation itself.
    """

    def __init__(
        self,
        mlflow_tracking_uri: Optional[str] = None,
    ):
        """
        Initialize service with MLflow client.

        Args:
            mlflow_tracking_uri: MLflow tracking server URI
        """
        self.mlflow_client = MLflowClient(
            tracking_uri=mlflow_tracking_uri,
        )

    def get_execution_data(self, execution_id: str) -> Dict[str, Any]:
        """
        Get consolidated execution data for an execution ID.

        This is the main public method. Returns standardized dict structure
        matching the existing API format for backward compatibility.

        Args:
            execution_id: Execution ID to fetch data for

        Returns:
            Dict with keys: execution_id, experiment, tasks, summary, traces, fallback_spans

        Raises:
            ValueError: If no data found or consolidation fails
        """
        logger.info(f"Fetching execution data for execution_id={execution_id}")

        # Step 1: Fetch raw traces from MLflow (data access layer)
        traces = self.mlflow_client.fetch_traces(execution_id)

        if not traces:
            return {
                "execution_id": execution_id,
                "tasks": [],
                "summary": {},
                "traces": [],
                "fallback_spans": [],
            }

        # Step 2: Consolidate spans into task tree (business logic)
        task_model = self._build_task_tree_from_traces(traces)

        # Step 3: Extract trace metadata
        trace_infos = []
        for tr in traces:
            info = getattr(tr, 'info', None)
            trace_infos.append({
                "trace_id": getattr(info, 'trace_id', None),
                "run_id": getattr(info, 'run_id', None),
                "span_count": len(getattr(getattr(tr, 'data', None), 'spans', []) or []),
            })

        logger.info(
            f"Consolidated {task_model['summary'].get('total_tasks', 0)} tasks "
            f"for execution_id={execution_id}"
        )

        return {
            "execution_id": execution_id,
            "tasks": task_model.get("tasks", []),
            "summary": task_model.get("summary", {}),
            "traces": trace_infos,
            "fallback_spans": task_model.get("fallback_spans", []),
        }

    # ============================================================================
    # Private helper methods (extracted from LLMTraceVisualizer)
    # ============================================================================

    def _normalize_attr(self, value: Any) -> Any:
        """Normalize attribute values (handle JSON strings, quoted strings, etc.)."""
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return raw
            try:
                return json.loads(raw)
            except Exception:
                if raw.startswith('"') and raw.endswith('"'):
                    return raw[1:-1]
                return raw
        return value

    def _get_attr(self, span: Any, *names: str) -> Any:
        """Extract attribute from span by trying multiple possible names."""
        attrs = getattr(span, 'attributes', {}) or {}
        if not isinstance(attrs, dict):
            return None
        for name in names:
            if name in attrs:
                return self._normalize_attr(attrs[name])
        return None

    def _extract_token_metrics(self, span: Any) -> Optional[Any]:
        """Extract token usage metrics from span attributes."""

        attrs = span.attributes if hasattr(span, 'attributes') else {}
        attr_dict = attrs if isinstance(attrs, dict) else {}

        token_usage = attr_dict.get('mlflow.chat.tokenUsage') or attr_dict.get('token_usage', {})

        if not token_usage and hasattr(span, 'outputs'):
            outputs = span.outputs if isinstance(span.outputs, dict) else {}
            token_usage = outputs.get('token_usage', {})

        if token_usage:
            cost_value = (
                attr_dict.get('cost_usd')
                or attr_dict.get('cost')
                or token_usage.get('cost_usd')
                or token_usage.get('cost')
                or 0.0
            )
            prompt_tokens = token_usage.get('input_tokens') or token_usage.get('prompt_tokens', 0)
            completion_tokens = token_usage.get('output_tokens') or token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)

            return type('TokenMetrics', (), {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'cost': cost_value,
                'model': attr_dict.get('model') or token_usage.get('model'),
            })()

        return None

    def _extract_span_errors(self, span: Any) -> tuple[Optional[str], Optional[str]]:
        """
        Extract error information from span events.

        Checks span.events for exception events and extracts error message, type, and stacktrace.

        Returns:
            tuple: (full_error_text, exception_type) or (None, None) if no errors
                   full_error_text includes stacktrace if available
        """
        # Check if span has events attribute
        events = getattr(span, 'events', None)
        if not events:
            return None, None

        # Look for exception events
        for event in events:
            event_name = getattr(event, 'name', None)

            if event_name == 'exception':
                # Extract exception details from event attributes
                attrs = getattr(event, 'attributes', {}) or {}
                if not isinstance(attrs, dict):
                    continue

                exception_type = attrs.get('exception.type')
                exception_message = attrs.get('exception.message')
                exception_stacktrace = attrs.get('exception.stacktrace')

                if exception_type or exception_message:
                    # Build full error text with stacktrace if available
                    full_error_parts = []

                    # Add message first
                    if exception_message:
                        full_error_parts.append(str(exception_message))

                    # Add stacktrace if available
                    if exception_stacktrace:
                        full_error_parts.append(str(exception_stacktrace))

                    full_error_text = "\n\n".join(full_error_parts) if full_error_parts else None

                    return full_error_text, exception_type

        return None, None

    def _extract_tool_calls(self, span: Any) -> List[Dict[str, Any]]:
        """Heuristically extract tool call records from an MLflow span."""
        calls: List[Dict[str, Any]] = []
        attrs = getattr(span, 'attributes', {}) or {}
        inputs = getattr(span, 'inputs', {}) or {}
        outputs = getattr(span, 'outputs', {}) or {}

        attr_dict = attrs if isinstance(attrs, dict) else {}
        input_dict = inputs if isinstance(inputs, dict) else {}
        output_dict = outputs if isinstance(outputs, dict) else {}

        def enrich_call(call_dict: Any) -> Dict[str, Any]:
            """Merge span-level metadata into a tool call dictionary."""
            base: Dict[str, Any]
            if isinstance(call_dict, dict):
                base = dict(call_dict)
            else:
                base = {'value': call_dict}

            metadata = base.get('metadata') if isinstance(base.get('metadata'), dict) else {}
            sources: List[Dict[str, Any]] = [base]
            if metadata:
                sources.append(metadata)
            sources.append(attr_dict)

            def pull(*keys: str) -> Any:
                for source in sources:
                    if not isinstance(source, dict):
                        continue
                    for key in keys:
                        if key in source and source[key] not in (None, "", []):
                            return source[key]
                return None

            tool_name = pull('tool', 'tool_name', 'roma.tool_name', 'name', 'type', 'id')
            toolkit_name = pull('toolkit', 'toolkit_class', 'roma.toolkit_name', 'source')
            tool_type = pull('tool_type', 'roma.tool_type')
            call_id = pull('tool_call_id', 'call_id', 'roma.tool_call_id', 'id')
            error_text = pull('error', 'exception')
            status = pull('status', 'state')

            if tool_name:
                base['tool'] = tool_name
                base.setdefault('roma.tool_name', tool_name)
            if toolkit_name:
                base['toolkit'] = toolkit_name
                base.setdefault('roma.toolkit_name', toolkit_name)
            if tool_type:
                base['tool_type'] = tool_type
                base.setdefault('roma.tool_type', tool_type)
            if status and 'status' not in base:
                base['status'] = status
            if call_id and 'call_id' not in base:
                base['call_id'] = call_id
            if error_text and 'error' not in base:
                base['error'] = error_text

            if 'arguments' not in base:
                func = base.get('function')
                if isinstance(func, dict) and func.get('arguments') is not None:
                    base['arguments'] = func['arguments']
                else:
                    args_value = pull('arguments', 'args', 'input', 'parameters', 'params')
                    if args_value is not None:
                        base['arguments'] = args_value

            if 'output' not in base:
                output_value = pull('output', 'result', 'return', 'response')
                if output_value is not None:
                    base['output'] = output_value

            if 'events' not in base:
                events = base.get('event')
                if events is None and output_dict:
                    events = output_dict.get('events')
                if events is None and input_dict:
                    events = input_dict.get('events')
                if events is not None:
                    base['events'] = events

            return base

        # 1) Direct metadata field
        tool_call_list = attr_dict.get('tool_calls')
        if isinstance(tool_call_list, list):
            for c in tool_call_list:
                if isinstance(c, dict):
                    calls.append(enrich_call(c))

        # 2) Structured attributes (single tool)
        single = {}
        for key in ('tool', 'tool_name', 'name', 'roma.tool_name'):
            if key in attr_dict:
                single['tool'] = attr_dict[key]
                break
        for key in ('toolkit', 'tool_class', 'toolkit_class', 'roma.toolkit_name', 'source'):
            if key in attr_dict:
                single['toolkit'] = attr_dict[key]
                break
        for key in ('arguments', 'args', 'input', 'parameters', 'params'):
            if key in attr_dict:
                single['arguments'] = attr_dict[key]
                break
        for key in ('output', 'result', 'return', 'response'):
            if key in attr_dict:
                single['output'] = attr_dict[key]
                break
        for key in ('tool_type', 'roma.tool_type'):
            if key in attr_dict:
                single['tool_type'] = attr_dict[key]
                break
        if 'status' in attr_dict:
            single['status'] = attr_dict['status']
        if 'error' in attr_dict:
            single['error'] = attr_dict['error']
        if single:
            calls.append(enrich_call(single))

        # 3) Outputs or inputs include tool_calls
        for container in (output_dict, input_dict):
            if isinstance(container, dict) and isinstance(container.get('tool_calls'), list):
                for c in container['tool_calls']:
                    if isinstance(c, dict):
                        calls.append(enrich_call(c))

        # 4) OpenAI-style assistant messages with tool_calls
        msgs = []
        if isinstance(input_dict, dict) and isinstance(input_dict.get('messages'), list):
            msgs.extend(input_dict['messages'])
        if isinstance(output_dict, dict) and isinstance(output_dict.get('messages'), list):
            msgs.extend(output_dict['messages'])
        for m in msgs:
            if isinstance(m, dict) and m.get('role') == 'assistant':
                tc = m.get('tool_calls')
                if isinstance(tc, list):
                    for c in tc:
                        if isinstance(c, dict):
                            # OpenAI format may nest function/name/arguments
                            name = (
                                c.get('function', {}).get('name')
                                if isinstance(c.get('function'), dict)
                                else c.get('name')
                            )
                            args = (
                                c.get('function', {}).get('arguments')
                                if isinstance(c.get('function'), dict)
                                else c.get('arguments')
                            )
                            calls.append(enrich_call({'tool': name, 'arguments': args}))

        return calls

    def _build_task_tree_from_traces(self, traces: List[Any]) -> Dict[str, Any]:
        """
        Build structured task + span model from MLflow traces.

        Key understanding:
        - Each trace = one agent execution (atomizer, planner, executor, aggregator, verifier)
        - Multiple traces can have the same task_id (different agents working on same task)
        - Each trace has a root wrapper span with agent_type and task metadata
        - We group by task_id but preserve agent execution details within each task
        """
        logger.debug(f"Processing {len(traces)} traces")

        tasks: Dict[str, Dict[str, Any]] = {}
        all_spans = []

        # Build span map for parent lookup
        for tr in traces:
            spans = getattr(getattr(tr, 'data', None), 'spans', []) or []
            all_spans.extend(spans)
        span_map = {getattr(s, 'span_id', None): s for s in all_spans if getattr(s, 'span_id', None)}

        fallback_spans = []

        # Process each trace (agent execution)
        for trace in traces:
            trace_id = getattr(getattr(trace, 'info', None), 'trace_id', None)
            spans = getattr(getattr(trace, 'data', None), 'spans', []) or []

            if not spans:
                continue

            # Extract trace-level token metrics (DSPy logs these at trace level, not span level)
            trace_info = getattr(trace, 'info', None)
            trace_tags = getattr(trace_info, 'tags', {}) or {}
            trace_tokens = None
            trace_cost = None
            trace_model = None

            # Try to get tokens from trace tags/metrics
            if 'mlflow.loggedMetrics' in trace_tags:
                logged_metrics = trace_tags.get('mlflow.loggedMetrics', '{}')
                try:
                    import json
                    metrics = json.loads(logged_metrics) if isinstance(logged_metrics, str) else logged_metrics
                    trace_tokens = metrics.get('tokens')
                except Exception:
                    pass

            # Also check direct tags
            if trace_tokens is None:
                trace_tokens = trace_tags.get('tokens') or trace_tags.get('total_tokens')
            if trace_cost is None:
                trace_cost = trace_tags.get('cost') or trace_tags.get('cost_usd')
            if trace_model is None:
                trace_model = trace_tags.get('model')

            # Find root wrapper span (no parent_id)
            root_span = None
            for span in spans:
                if not getattr(span, 'parent_id', None):
                    root_span = span
                    break

            if not root_span:
                logger.warning(f"No root span found for trace {trace_id}")
                continue

            # Extract task metadata from root span
            task_id = self._get_attr(root_span, 'roma.task_id', 'task_id')

            if not task_id:
                # Handle trace without task_id
                logger.warning(f"No task_id found for trace {trace_id}")
                continue

            # Get agent type from root span (normalize to lowercase for consistent grouping)
            agent_type_raw = self._get_attr(root_span, 'roma.agent_type', 'agent_type') or getattr(root_span, 'name', 'unknown')
            agent_type = agent_type_raw.lower() if isinstance(agent_type_raw, str) else str(agent_type_raw).lower()

            # Extract goal from root span
            goal = self._get_attr(root_span, 'goal', 'roma.goal', 'task_goal')
            if not goal:
                inputs = getattr(root_span, 'inputs', {}) or {}
                if isinstance(inputs, dict):
                    goal = inputs.get('goal') or inputs.get('original_goal')

            # Create or get task entry
            if task_id not in tasks:
                tasks[task_id] = {
                    'task_id': task_id,
                    'parent_task_id': self._get_attr(root_span, 'roma.parent_task_id', 'parent_task_id'),
                    'goal': str(goal) if goal else None,
                    'task_type': self._get_attr(root_span, 'roma.task_type', 'task_type'),
                    'node_type': self._get_attr(root_span, 'roma.node_type', 'node_type'),
                    'status': self._get_attr(root_span, 'roma.status', 'status'),
                    'depth': self._get_attr(root_span, 'roma.depth', 'depth') or 0,
                    'metrics': {
                        'duration': 0.0,
                        'tokens': 0,
                        'cost': 0.0,
                    },
                    'agent_executions': [],  # NEW: list of agent executions
                    '_first_span_id': getattr(root_span, 'span_id', None),
                }

            task_entry = tasks[task_id]

            # Build agent execution record
            # Use trace-level metrics (execution_time_ms, tokens from MLflow)
            trace_duration_s = trace_info.execution_time_ms / 1000.0 if trace_info.execution_time_ms else 0.0

            try:
                trace_tokens_int = int(trace_tokens) if trace_tokens is not None else 0
            except (TypeError, ValueError):
                try:
                    trace_tokens_int = int(float(trace_tokens)) if trace_tokens is not None else 0
                except (TypeError, ValueError):
                    trace_tokens_int = 0

            agent_execution = {
                'trace_id': trace_id,
                'agent_type': agent_type,
                'spans': [],
                'metrics': {
                    'duration': trace_duration_s,  # Use trace-level duration from MLflow
                    'tokens': trace_tokens_int,
                    'cost': float(trace_cost) if trace_cost is not None else 0.0,
                },
            }

            # Pre-scan: Identify which spans have Tool.* children
            # This allows us to skip _extract_tool_calls for those spans (avoiding duplicates)
            spans_with_tool_children = set()
            for span in spans:
                span_name = getattr(span, 'name', '')
                if span_name.startswith('Tool.'):
                    parent_id = getattr(span, 'parent_id', None)
                    if parent_id:
                        spans_with_tool_children.add(parent_id)

            # Process all spans in this trace (INCLUDING root wrapper for TUI visibility)
            for span in spans:
                span_type = self._get_attr(span, 'roma.span_type', 'span_type')

                # Check if this is the root wrapper (agent-level span like "aggregator", "atomizer")
                is_root_wrapper = (getattr(span, 'span_id', None) == getattr(root_span, 'span_id', None))
                start_ns = getattr(span, 'start_time_ns', 0) or 0
                end_ns = getattr(span, 'end_time_ns', 0) or 0
                duration = max(0.0, (end_ns - start_ns) / 1e9)
                tm = self._extract_token_metrics(span)

                # Duration is already set from trace-level execution_time_ms
                # Don't sum child span durations (they overlap/nest, not additive!)

                # Determine token/cost for this span
                span_tokens_int = 0
                span_cost = None
                span_model = None

                if is_root_wrapper:
                    # Root wrapper gets agent-level metrics
                    span_tokens_int = trace_tokens_int
                    span_cost = float(trace_cost) if trace_cost is not None else 0.0
                    span_model = trace_model
                else:
                    # Child spans: use trace-level tokens for LM calls, span-level for others
                    span_name = getattr(span, 'name', '')
                    if 'LM' in span_name or '__call__' in span_name:
                        # This is likely the LM call span - assign trace-level metrics
                        span_tokens_value = trace_tokens_int if trace_tokens is not None else (tm.total_tokens if tm else 0)
                        span_cost = float(trace_cost) if trace_cost is not None else (tm.cost if tm else None)
                        span_model = trace_model or (tm.model if tm else None)
                        # Also check span attributes for model (OpenTelemetry standard)
                        if not span_model:
                            span_model = self._get_attr(span, 'gen_ai.request.model', 'llm.model', 'model')
                    else:
                        # Non-LM spans get span-level metrics if available
                        span_tokens_value = tm.total_tokens if tm else 0
                        span_cost = tm.cost if tm else None
                        span_model = tm.model if tm else None
                        # Also check span attributes for model
                        if not span_model:
                            span_model = self._get_attr(span, 'gen_ai.request.model', 'llm.model', 'model')

                    try:
                        span_tokens_int = int(span_tokens_value)
                    except (TypeError, ValueError):
                        try:
                            span_tokens_int = int(float(span_tokens_value))
                        except (TypeError, ValueError):
                            span_tokens_int = 0

                # Add span to this agent execution (including root wrapper!)
                # All spans in an agent execution get the agent_type as their module for proper grouping
                # Normalize module name to lowercase for consistent grouping in TUI
                span_module_raw = self._get_attr(span, 'roma.module_name', 'roma.module', 'module') or agent_type
                span_module = span_module_raw.lower() if isinstance(span_module_raw, str) else str(span_module_raw).lower()

                # Extract errors from span events (for TUI Error Analysis View)
                error_message, exception_type = self._extract_span_errors(span)

                # Determine tool_calls: Skip _extract_tool_calls for:
                # 1. Spans that will have Tool.* children (populated later from children)
                # 2. Tool.* spans themselves (they ARE the tool execution, not a caller)
                current_span_id = getattr(span, 'span_id', None)
                span_name = getattr(span, 'name', '')

                if current_span_id in spans_with_tool_children or span_name.startswith('Tool.'):
                    # Skip extraction - either has Tool.* children OR is a Tool.* span itself
                    tool_calls_for_span = []
                else:
                    # Regular span with no Tool.* involvement - use _extract_tool_calls
                    tool_calls_for_span = self._extract_tool_calls(span)

                agent_execution['spans'].append({
                    'span_id': current_span_id,
                    'parent_id': getattr(span, 'parent_id', None),
                    'name': getattr(span, 'name', 'span'),
                    'module': span_module,
                    'start_ns': start_ns,
                    'start_time': (
                        datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc).isoformat() if start_ns else None
                    ),
                    'duration': duration,
                    'tokens': span_tokens_int,
                    'cost': span_cost,
                    'model': span_model,
                    'tool_calls': tool_calls_for_span,
                    'inputs': getattr(span, 'inputs', None),
                    'outputs': getattr(span, 'outputs', None),
                    'reasoning': self._get_attr(span, 'reasoning'),
                    'is_wrapper': is_root_wrapper,  # Flag for TUI to recognize wrapper spans
                    'error': error_message,  # Error message from exception events
                    'exception': exception_type,  # Exception type from exception events
                })

            # Collect Tool.* child spans into their parent's tool_calls array
            # Build span_id -> span dict for quick lookup
            span_dict = {sp['span_id']: sp for sp in agent_execution['spans'] if sp['span_id']}

            # Extract Tool.* child spans into parent's tool_calls
            # (Parent's tool_calls is already empty if it has Tool.* children - see pre-scan above)
            for sp in agent_execution['spans']:
                span_name = sp.get('name', '')
                if span_name.startswith('Tool.'):
                    # This is a tool call span - add it to parent's tool_calls
                    parent_id = sp.get('parent_id')
                    if parent_id and parent_id in span_dict:
                        parent_span = span_dict[parent_id]

                        # Create tool call dict from Tool.* span
                        tool_name = span_name[5:]  # Remove "Tool." prefix

                        # Get the original span object to access attributes
                        original_span = None
                        for orig_span in spans:
                            if getattr(orig_span, 'span_id', None) == sp['span_id']:
                                original_span = orig_span
                                break

                        # Extract toolkit and tool_type from span attributes (set by ROMAToolSpanCallback)
                        toolkit_name = None
                        tool_type = None
                        if original_span:
                            toolkit_name = self._get_attr(original_span, 'roma.toolkit_name', 'toolkit')
                            tool_type = self._get_attr(original_span, 'roma.tool_type', 'tool_type')

                        tool_call = {
                            'name': tool_name,
                            'tool': tool_name,
                            'toolkit': toolkit_name or 'unknown',
                            'tool_type': tool_type or 'unknown',
                            'arguments': sp.get('inputs'),
                            'output': sp.get('outputs'),
                            'duration': sp.get('duration'),
                        }

                        # Add error/exception if tool failed
                        if sp.get('error'):
                            tool_call['error'] = sp['error']
                        if sp.get('exception'):
                            tool_call['exception'] = sp['exception']
                            tool_call['status'] = 'failed'

                        # Add to parent's tool_calls (already empty, no duplicates possible)
                        parent_span['tool_calls'].append(tool_call)

            # Sort spans by start time
            agent_execution['spans'].sort(key=lambda sp: sp['start_ns'])

            # Convert start_ns to start_ts
            for sp in agent_execution['spans']:
                start_ns = sp.pop('start_ns', None)
                if start_ns:
                    sp['start_ts'] = start_ns / 1e9

            # Add agent execution to task
            task_entry['agent_executions'].append(agent_execution)

            # Aggregate metrics to task level
            task_entry['metrics']['duration'] += agent_execution['metrics']['duration']
            task_entry['metrics']['tokens'] += agent_execution['metrics']['tokens']
            task_entry['metrics']['cost'] += agent_execution['metrics']['cost']

        # Convert to list and clean up
        task_list = []
        for entry in tasks.values():
            # Sort agent executions by agent type (atomizer, planner, executor, aggregator, verifier)
            agent_order = {'atomizer': 0, 'planner': 1, 'executor': 2, 'aggregator': 3, 'verifier': 4}
            entry['agent_executions'].sort(key=lambda ae: agent_order.get(ae['agent_type'], 999))

            # Remove internal tracking fields
            entry.pop('_first_span_id', None)
            task_list.append(entry)

        # Calculate summary
        total_agent_executions = sum(len(entry['agent_executions']) for entry in task_list)
        total_spans = sum(
            sum(len(ae['spans']) for ae in entry['agent_executions'])
            for entry in task_list
        )

        summary = {
            'total_tasks': len(task_list),
            'total_agent_executions': total_agent_executions,
            'total_spans': total_spans,
            'total_duration': sum(entry['metrics']['duration'] for entry in task_list),
            'total_tokens': sum(entry['metrics']['tokens'] for entry in task_list),
            'total_cost': sum(entry['metrics']['cost'] for entry in task_list),
        }

        return {
            'tasks': task_list,
            'summary': summary,
            'fallback_spans': fallback_spans,
        }
