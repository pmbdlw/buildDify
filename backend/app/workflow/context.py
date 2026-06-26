"""执行上下文与变量池。

变量池以 node_id 为命名空间,存每个节点的输出 dict。节点配置里用
`{{ node_id.field }}` 引用上游产物,执行时统一在这里解析:
- resolve_text:把模板里所有引用替换为字符串,拼回整段文本。
- resolve_value:若整段恰好是单个引用,返回其原始值(可为非字符串)。
"""

import re
from typing import Any

# 变量引用语法:{{ node_id.field }}(node_id / field 为字母数字下划线)
VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*\}\}")
# 整段恰为单个引用(用于取原始值而非字符串化)
SINGLE_VAR_RE = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*\}\}\s*$")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class VariablePool:
    """node_id -> 输出 dict 的命名空间存储。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def set_output(self, node_id: str, outputs: dict[str, Any]) -> None:
        self._data[node_id] = outputs

    def get(self, node_id: str, key: str) -> Any:
        return self._data.get(node_id, {}).get(key)

    def get_outputs(self, node_id: str) -> dict[str, Any]:
        return dict(self._data.get(node_id, {}))

    def resolve_text(self, template: str | None) -> str:
        """把模板中的所有 {{ node.field }} 替换为字符串后返回整段。"""
        if not template:
            return ""

        def repl(m: re.Match[str]) -> str:
            return _stringify(self.get(m.group(1), m.group(2)))

        return VAR_RE.sub(repl, template)

    def resolve_value(self, template: str | None) -> Any:
        """整段恰为单个引用时返回原始值,否则按文本解析返回字符串。"""
        if not template:
            return ""
        single = SINGLE_VAR_RE.match(template)
        if single:
            return self.get(single.group(1), single.group(2))
        return self.resolve_text(template)


class ExecutionContext:
    """一次运行的执行上下文:变量池 + DB 会话(供检索类节点用)。"""

    def __init__(self, session: Any) -> None:
        self.pool = VariablePool()
        self.session = session
