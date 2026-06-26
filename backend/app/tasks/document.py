"""文档处理任务:分块 → embedding → 入库,驱动文档状态机。

状态:pending →(进入任务)processing →(成功)ready /(异常)error。
worker 在独立事件循环中运行,使用 NullPool 的专用引擎,避免跨循环复用连接。
解析已在上传请求里完成并写入 kb_document.content,任务只做慢的 embedding 部分。
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.llm.factory import build_provider, provider_for_model
from app.models.knowledge import DOC_ERROR, DOC_PROCESSING, DOC_READY, Segment
from app.repositories.knowledge import DocumentRepository, SegmentRepository
from app.services.chunking import chunk_text
from app.tasks.celery_app import celery_app

_EMBED_BATCH = 32


async def _embed_all(texts: list[str]) -> list[list[float]]:
    """用 embedding 模型对所有分块向量化(分批,避免单次请求过大)。"""
    provider = build_provider(provider_for_model(settings.embedding_model))
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i : i + _EMBED_BATCH]
        vectors.extend(await provider.embed(batch, model=settings.embedding_model))
    return vectors


async def _process(document_id: uuid.UUID) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            docs = DocumentRepository(session)
            segments = SegmentRepository(session)
            doc = await docs.get(document_id)
            if doc is None:
                return
            doc.status = DOC_PROCESSING
            doc.error = None
            await session.commit()

            try:
                chunks = chunk_text(
                    doc.content or "",
                    chunk_size=settings.kb_chunk_size,
                    overlap=settings.kb_chunk_overlap,
                )
                vectors = await _embed_all(chunks) if chunks else []

                await segments.delete_for_document(doc.id)  # 幂等:重跑先清旧分段
                await segments.bulk_add(
                    [
                        Segment(
                            document_id=doc.id,
                            dataset_id=doc.dataset_id,
                            sort_order=idx,
                            content=text,
                            tokens=len(text),
                            embedding=vec,
                        )
                        for idx, (text, vec) in enumerate(zip(chunks, vectors, strict=True))
                    ]
                )
                doc.status = DOC_READY
                doc.segment_count = len(chunks)
                doc.error = None
                await session.commit()
            except Exception as exc:  # noqa: BLE001 —— 落库错误状态,任务不抛出以免无意义重试
                await session.rollback()
                doc = await docs.get(document_id)
                if doc is not None:
                    doc.status = DOC_ERROR
                    doc.error = str(exc)[:1000]
                    await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="kb.process_document")
def process_document(document_id: str) -> None:
    asyncio.run(_process(uuid.UUID(document_id)))
