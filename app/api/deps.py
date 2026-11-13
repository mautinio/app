"""Сборка зависимостей для роутов. Единственное место, где сервисы связываются с настройками и инфраструктурой.

Роуты получают готовые объекты через `Annotated`-алиасы: `editor: EditorDep`.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.keitaro import KeitaroClient
from app.repositories import CampaignRepository
from app.services import CampaignCreator, CampaignSync, StatsService, StreamEditor
from app.services.campaign_creator import CreatorDefaults


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_keitaro(request: Request) -> KeitaroClient:
    return request.app.state.keitaro


SettingsDep = Annotated[Settings, Depends(get_settings)]
KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_repo(session: SessionDep) -> CampaignRepository:
    return CampaignRepository(session)


RepoDep = Annotated[CampaignRepository, Depends(get_repo)]


def get_sync(keitaro: KeitaroDep, repo: RepoDep, settings: SettingsDep) -> CampaignSync:
    return CampaignSync(keitaro, repo, settings.tracker_url)


SyncDep = Annotated[CampaignSync, Depends(get_sync)]


def get_creator(keitaro: KeitaroDep, sync: SyncDep, settings: SettingsDep) -> CampaignCreator:
    defaults = CreatorDefaults(
        domain_id=settings.default_domain_id,
        group_id=settings.default_group_id,
        traffic_source_id=settings.default_traffic_source_id,
        redirect_url=settings.geo_redirect_url,
    )
    return CampaignCreator(keitaro, sync, defaults)


def get_editor(keitaro: KeitaroDep, repo: RepoDep) -> StreamEditor:
    return StreamEditor(keitaro, repo)


def get_stats(keitaro: KeitaroDep, settings: SettingsDep) -> StatsService:
    return StatsService(keitaro, settings.keitaro_timezone)


CreatorDep = Annotated[CampaignCreator, Depends(get_creator)]
EditorDep = Annotated[StreamEditor, Depends(get_editor)]
StatsDep = Annotated[StatsService, Depends(get_stats)]
