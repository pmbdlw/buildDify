"""检索业务:query 向量化 + pgvector top-k,产出可用于拼接上下文的引用片段。"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.factory import provider_for_model, resolve_provider
from app.repositories.knowledge import SegmentRepository


@dataclass
class Citation:
    index: int  # 引用编号(从 1 起),用于回答里的 [1][2] 标注
    document_id: uuid.UUID
    content: str
    score: float


class RetrievalService:
    def __init__(self, session: AsyncSession) -> None:
        self.segments = SegmentRepository(session)

    async def retrieve(
        self, *, dataset_id: uuid.UUID, query: str, top_k: int | None = None
    ) -> list[Citation]:
        k = top_k or settings.kb_retrieval_top_k
        provider = resolve_provider(provider_for_model(settings.embedding_model))
        [vector] = await provider.embed([query], model=settings.embedding_model)
        hits = await self.segments.search(
            dataset_id=dataset_id, query_embedding=vector, top_k=k
        )
        return [
            Citation(
                index=i + 1,
                document_id=seg.document_id,
                content=seg.content,
                score=round(score, 4),
            )
            for i, (seg, score) in enumerate(hits)
        ]


def build_rag_system_prompt(base_system: str | None, citations: list[Citation]) -> str:
    """把检索片段拼成「参考资料」注入 system,要求模型按编号标注引用。"""
    refs = "\n\n".join(f"[{c.index}] {c.content}" for c in citations)
    guide = (
        "你是知识库问答助手。请优先依据下面的「参考资料」回答用户问题,"
        "并在引用到资料处用 [编号] 标注来源(如 [1][2])。"
        "若参考资料中没有相关信息,请明确说明并基于常识谨慎作答。\n\n"
        f"参考资料:\n{refs}"
    )
    return f"{base_system}\n\n{guide}" if base_system else guide
