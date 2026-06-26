"""知识库路由:数据集 CRUD、文档上传/列表、检索测试。"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.knowledge import (
    CitationOut,
    DatasetCreate,
    DatasetOut,
    DocumentOut,
    RetrieveIn,
)
from app.services.knowledge import KnowledgeService
from app.services.retrieval import RetrievalService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def _require_dataset(
    dataset_id: uuid.UUID, user: User, service: KnowledgeService
):
    ds = await service.get_dataset(dataset_id, user.id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return ds


@router.post("/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    data: DatasetCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = KnowledgeService(session)
    return await service.create_dataset(
        user_id=current_user.id, name=data.name, description=data.description
    )


@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).list_datasets(current_user.id)


@router.post(
    "/datasets/{dataset_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    dataset_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = KnowledgeService(session)
    ds = await _require_dataset(dataset_id, current_user, service)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    return await service.upload_document(
        dataset=ds, filename=file.filename or "未命名", data=data
    )


@router.get("/datasets/{dataset_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    dataset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = KnowledgeService(session)
    await _require_dataset(dataset_id, current_user, service)
    return await service.list_documents(dataset_id)


@router.post("/datasets/{dataset_id}/retrieve", response_model=list[CitationOut])
async def retrieve(
    dataset_id: uuid.UUID,
    data: RetrieveIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = KnowledgeService(session)
    await _require_dataset(dataset_id, current_user, service)
    citations = await RetrievalService(session).retrieve(
        dataset_id=dataset_id, query=data.query, top_k=data.top_k
    )
    return citations
