"""知识库业务逻辑:数据集与文档管理、上传入库编排。

文档上传:同步解析为文本并落库(status=pending),再投递 Celery 任务做分块+embedding。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import Dataset, Document
from app.repositories.knowledge import (
    DatasetRepository,
    DocumentRepository,
    SegmentRepository,
)
from app.services import document_parser
from app.tasks.document import process_document


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.datasets = DatasetRepository(session)
        self.documents = DocumentRepository(session)
        self.segments = SegmentRepository(session)

    # ---- 数据集 ----
    async def create_dataset(
        self, *, user_id: uuid.UUID, name: str, description: str | None
    ) -> Dataset:
        ds = await self.datasets.create(
            user_id=user_id,
            name=name,
            description=description,
            embedding_model=settings.embedding_model,
        )
        await self.session.commit()
        await self.session.refresh(ds)
        return ds

    async def list_datasets(self, user_id: uuid.UUID) -> list[Dataset]:
        return await self.datasets.list_for_user(user_id)

    async def get_dataset(self, dataset_id: uuid.UUID, user_id: uuid.UUID) -> Dataset | None:
        return await self.datasets.get(dataset_id, user_id)

    # ---- 文档 ----
    async def upload_document(
        self, *, dataset: Dataset, filename: str, data: bytes
    ) -> Document:
        """解析文件为文本、落库(pending),并投递异步处理任务。"""
        file_type = document_parser.detect_file_type(filename)
        text = document_parser.parse(data, file_type)

        doc = await self.documents.create(
            dataset_id=dataset.id, name=filename, file_type=file_type
        )
        doc.content = text
        doc.char_count = len(text)
        await self.session.commit()
        await self.session.refresh(doc)

        process_document.delay(str(doc.id))
        return doc

    async def list_documents(self, dataset_id: uuid.UUID) -> list[Document]:
        return await self.documents.list_for_dataset(dataset_id)
