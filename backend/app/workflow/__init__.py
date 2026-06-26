"""工作流执行引擎。

对外暴露执行入口与结果类型;上层 service 调用 execute_workflow 驱动一次运行。
"""

from app.workflow.engine import (
    NodeRunRecord,
    RunResult,
    WorkflowError,
    execute_workflow,
)

__all__ = [
    "NodeRunRecord",
    "RunResult",
    "WorkflowError",
    "execute_workflow",
]
