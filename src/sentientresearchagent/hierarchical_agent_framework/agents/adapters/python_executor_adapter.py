from __future__ import annotations
import asyncio, inspect
from importlib import import_module

def _import_from_string(path: str):
    module, name = path.rsplit(".", 1)
    mod = import_module(module)
    return getattr(mod, name)

class PythonExecutorAdapter:
    """
    Generic adapter that loads a dotted-path Python executor class and calls its async execute(input).

    It expects the agent config to include "executor_path" either at the top level
    or inside adapter_params.executor_path in agents.yaml.

    Example executor_path:
      "daypilot.roma_executor.DayPilotExecutor"
    """
    def __init__(self, config=None):
        self.config = config or {}

    async def execute(self, input, **kwargs):

        path = (
            self.config.get("executor_path")
            or (self.config.get("adapter_params") or {}).get("executor_path")
        )
        if not path:
            raise ValueError("executor_path not provided in agent config")

    
        ExecutorCls = _import_from_string(path)
        executor = ExecutorCls()


        data = input
        if isinstance(data, dict):
            try:
                in_model = _import_from_string(path.rsplit(".", 1)[0] + ".DayPilotInput")
                data = in_model.model_validate(data)
            except Exception:
                pass

      
        fn = getattr(executor, "execute")
        if inspect.iscoroutinefunction(fn):
            result = await fn(data)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, fn, data)


        try:
            return result.model_dump()
        except Exception:
            return result
