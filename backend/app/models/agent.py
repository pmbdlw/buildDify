"""Agent 模型:agent_tool / agent_thought。

- agent_tool:Agent 应用绑定的工具(内置工具的启用与参数化)。
  type 为内置工具键(knowledge_retrieval / http_request / code_exec);
  config 存该工具的固定参数(如 http 的 url 模板、检索的 dataset_id / top_k)。
  工具挂在 app_id 上(而非配置版本),MVP 下与配置版本解耦,简化管理。
- agent_thought:一次 Agent 回合(ReAct)的思考轨迹步骤,用于前端轨迹回放。
  kind: thought(模型思考文本)/ tool_call(请求调用工具)/ observation(工具返回)/ answer(最终答复)。

外键(user_id / app_id / conversation_id / message_id)按规范统一命名但不建物理约束,仅加索引。
"""

import uuid

from sqlalchemy import Boolean, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

# 内置工具类型键
TOOL_KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
TOOL_HTTP_REQUEST = "http_request"
TOOL_CODE_EXEC = "code_exec"

# 轨迹步骤类型
THOUGHT_THINK = "thought"
THOUGHT_TOOL_CALL = "tool_call"
THOUGHT_OBSERVATION = "observation"
THOUGHT_ANSWER = "answer"


class AgentTool(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "agent_tool"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # 内置工具类型键
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # 工具固定参数(如 url 模板、dataset_id、top_k)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class AgentThought(Base, TimestampMixin):
    __tablename__ = "agent_thought"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # 归属的助手消息(一轮回合最终落库的 assistant message)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # 步骤类型:thought / tool_call / observation / answer
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # 思考/答复文本(thought / answer)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 工具调用(tool_call / observation)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 步骤顺序(从 0 起),用于轨迹回放排序
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
