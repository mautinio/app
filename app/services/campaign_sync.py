from datetime import UTC, datetime

from app.domain.models import Campaign, Stream
from app.keitaro import KeitaroClient, KtCampaign
from app.repositories import CampaignRepository


class CampaignSync:
    """Fetch streams from KT: приводит локальное зеркало кампании к состоянию Keitaro."""

    def __init__(self, keitaro: KeitaroClient, repo: CampaignRepository, tracker_url: str | None):
        self._keitaro = keitaro
        self._repo = repo
        self._tracker_url = tracker_url

    async def fetch(self, campaign_id: int, *, geo: list[str] | None = None) -> Campaign:
        kt_campaign = await self._keitaro.campaign(campaign_id)
        kt_streams = [s for s in await self._keitaro.streams(campaign_id) if not s.deleted]
        names = await self._keitaro.offer_names()

        campaign = await self._repo.find_campaign(campaign_id)
        if campaign is None:
            campaign = Campaign(id=campaign_id, streams=[])
            self._repo.add(campaign)
        self._update_campaign(campaign, kt_campaign, geo)

        alive = set()
        for kt_stream in kt_streams:
            alive.add(kt_stream.id)
            stream = campaign.stream(kt_stream.id)
            if stream is None:
                stream = Stream(id=kt_stream.id, offers=[])
                campaign.streams.append(stream)
            stream.name = kt_stream.name
            stream.position = kt_stream.position
            stream.deleted = False
            stream.sync_published(kt_stream.offers, names)
        for stream in campaign.streams:
            stream.deleted = stream.id not in alive

        await self._repo.commit()
        return campaign

    def _update_campaign(self, campaign: Campaign, kt: KtCampaign, geo: list[str] | None) -> None:
        campaign.name = kt.name or f"Campaign {kt.id}"
        campaign.alias = kt.alias
        campaign.state = kt.state
        campaign.url = self._campaign_url(kt)
        campaign.fetched_at = datetime.now(UTC)
        if geo is not None:
            campaign.geo = geo
            campaign.created_by_wrapper = True

    def _campaign_url(self, kt: KtCampaign) -> str | None:
        """Ссылка для объявления. Без домена Keitaro отвечает на любом своём хосте — берём хост трекера."""
        host = (kt.domain or self._tracker_url or "").strip().rstrip("/")
        if not host or not kt.alias:
            return None
        if not host.startswith("http"):
            host = f"https://{host}"
        return f"{host}/{kt.alias}"
