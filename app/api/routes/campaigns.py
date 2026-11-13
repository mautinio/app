from datetime import date

from fastapi import APIRouter

from app.api.deps import CreatorDep, RepoDep, StatsDep, SyncDep
from app.api.schemas import CampaignDetailOut, CampaignIn, CampaignOut, HistoryOut, StreamOut
from app.services import NewCampaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", status_code=201, response_model=CampaignOut)
async def create_campaign(body: CampaignIn, creator: CreatorDep):
    return CampaignOut.from_campaign(await creator.create(NewCampaign(**body.model_dump())))


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(repo: RepoDep):
    return [CampaignOut.from_campaign(c) for c in await repo.list_campaigns()]


@router.post("/{campaign_id}/fetch", response_model=CampaignOut)
async def fetch_campaign(campaign_id: int, sync: SyncDep):
    """Fetch streams from KT: загрузить или обновить кампанию, её потоки и офферы из Keitaro."""
    return CampaignOut.from_campaign(await sync.fetch(campaign_id))


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def campaign_detail(
    campaign_id: int,
    repo: RepoDep,
    stats_service: StatsDep,
    date_from: date | None = None,
    date_to: date | None = None,
):
    campaign = await repo.get_campaign(campaign_id)
    date_from = date_from or date.today()
    date_to = date_to or date.today()
    stats = await stats_service.campaign_stats(campaign_id, date_from, date_to)
    return CampaignDetailOut(
        **CampaignOut.from_campaign(campaign).model_dump(),
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        stats_error=stats.error,
        streams=[StreamOut.from_stream(s, stats) for s in campaign.visible_streams],
    )


@router.get("/{campaign_id}/history", response_model=list[HistoryOut])
async def history(campaign_id: int, repo: RepoDep):
    return [HistoryOut.from_log(r) for r in await repo.history(campaign_id)]
