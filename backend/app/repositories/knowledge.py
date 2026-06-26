"""知识库数据访问:数据集 / 文档 / 分段(含 pgvector 检索)。"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Dataset, Document, Segment


class DatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, user_id: uuid.UUID, name: str, description: str | None, embedding_model: str
    ) -> Dataset:
        ds = Dataset(
            user_id=user_id, name=name, description=description, embedding_model=embedding_model
        )
        self.session.add(ds)
        await self.session.flush()
        await self.session.refresh(ds)
        return ds

    async def get(self, dataset_id: uuid.UUID, user_id: uuid.UUID) -> Dataset | None:
        result = await self.session.execute(
            select(Dataset).where(
                Dataset.id == dataset_id,
                Dataset.user_id == user_id,
                Dataset.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[Dataset]:
        result = await self.session.execute(
            select(Dataset)
            .where(Dataset.user_id == user_id, Dataset.deleted_at.is_(None))
            .order_by(Dataset.updated_at.desc())
        )
        return list(result.scalars().all())


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, dataset_id: uuid.UUID, name: str, file_type: str
    ) -> Document:
        doc = Document(dataset_id=dataset_id, name=name, file_type=file_type)
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def get(self, document_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id, Document.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_dataset(self, dataset_id: uuid.UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.dataset_id == dataset_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())


class SegmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(Segment).where(Segment.document_id == document_id)
        )

    async def bulk_add(self, segments: list[Segment]) -> None:
        self.session.add_all(segments)
        await self.session.flush()

    async def search(
        self, *, dataset_id: uuid.UUID, query_embedding: list[float], top_k: int
    ) -> list[tuple[Segment, float]]:
        """按余弦距离检索 top-k 分段,返回 (segment, score),score=1-distance(越大越相关)。"""
        distance = Segment.embedding.cosine_distance(query_embedding)
        result = await self.session.execute(
            select(Segment, distance.label("distance"))
            .where(Segment.dataset_id == dataset_id)
            .order_by(distance.asc())
            .limit(top_k)
        )
        return [(row[0], 1.0 - float(row[1])) for row in result.all()]
