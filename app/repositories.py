from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.errors import NotFound
from app.domain.models import Campaign, PushLog, Stream


class CampaignRepository:
    """Загрузка и сохранение агрегатов. Всегда подгружает потоки с офферами целиком — ленивой загрузки в async нет."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_campaign(self, campaign_id: int) -> Campaign | None:
        return await self._session.scalar(
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .options(selectinload(Campaign.streams).selectinload(Stream.offers))
        )

    async def get_campaign(self, campaign_id: int) -> Campaign:
        campaign = await self.find_campaign(campaign_id)
        if campaign is None:
            raise NotFound("Кампания ещё не загружена в обёртку — нажмите Fetch streams from KT")
        return campaign

    async def get_stream(self, stream_id: int) -> Stream:
        stream = await self._session.scalar(
            select(Stream).where(Stream.id == stream_id).options(selectinload(Stream.offers))
        )
        if stream is None or stream.deleted:
            raise NotFound(f"Поток #{stream_id} не найден — сначала загрузите кампанию из Keitaro (Fetch)")
        return stream

    async def list_campaigns(self) -> list[Campaign]:
        return list(await self._session.scalars(select(Campaign).order_by(Campaign.id.desc())))

    async def history(self, campaign_id: int, limit: int = 50) -> list[PushLog]:
        return list(
            await self._session.scalars(
                select(PushLog).where(PushLog.campaign_id == campaign_id).order_by(PushLog.id.desc()).limit(limit)
            )
        )

    def add(self, entity: Campaign | PushLog) -> None:
        self._session.add(entity)

    async def commit(self) -> None:
        await self._session.commit()
