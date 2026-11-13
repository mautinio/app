"""Схемы запросов и ответов API. Сборка ответа из доменных объектов — в фабричных методах `from_*`."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import Campaign, PushLog, Stream, StreamOffer
from app.services import CampaignStats

Metrics = dict[str, float]


# ------------------------------------------------------------ запросы


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    geo: str | list[str]
    offer_id: int
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


class OfferIn(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool


class ShareIn(BaseModel):
    share: int


# ------------------------------------------------------------ справочники


class RefOut(BaseModel):
    id: int
    name: str


class OfferOut(RefOut):
    state: str


class KeitaroCampaignOut(RefOut):
    alias: str
    state: str | None


class Defaults(BaseModel):
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None


class MetaOut(BaseModel):
    mock: bool
    keitaro_admin_url: str | None
    geo_redirect_url: str
    defaults: Defaults
    domains: list[RefOut]
    groups: list[RefOut]
    traffic_sources: list[RefOut]


# ------------------------------------------------------------ кампании и потоки


class CampaignOut(BaseModel):
    id: int
    name: str
    alias: str
    state: str | None
    url: str | None
    geo: list[str] | None
    created_by_wrapper: bool
    fetched_at: datetime | None

    @classmethod
    def from_campaign(cls, c: Campaign) -> "CampaignOut":
        return cls(
            id=c.id,
            name=c.name,
            alias=c.alias,
            state=c.state,
            url=c.url,
            geo=c.geo,
            created_by_wrapper=c.created_by_wrapper,
            fetched_at=c.fetched_at,
        )


class StreamOfferOut(BaseModel):
    offer_id: int
    name: str
    status: str
    share: int
    pinned: bool
    published: bool  # сейчас стоит в Keitaro
    pushed_status: str | None
    pushed_share: int | None
    dirty: bool
    stats: Metrics

    @classmethod
    def from_offer(cls, o: StreamOffer, stats: Metrics) -> "StreamOfferOut":
        return cls(
            offer_id=o.offer_id,
            name=o.offer_name,
            status=o.status,
            share=o.share,
            pinned=o.pinned,
            published=o.is_live,
            pushed_status=o.pushed_status,
            pushed_share=o.pushed_share,
            dirty=o.dirty,
            stats=stats,
        )


class UntrackedOfferOut(BaseModel):
    """Клики по офферу, которого обёртка не знает (убран из потока до того, как кампанию загрузили)."""

    offer_id: int
    stats: Metrics


class StreamOut(BaseModel):
    id: int
    name: str
    position: int
    has_offers: bool
    dirty: bool
    shares_total: int
    stats: Metrics
    offers: list[StreamOfferOut]
    untracked_offers: list[UntrackedOfferOut]

    @classmethod
    def from_stream(cls, s: Stream, stats: CampaignStats | None = None) -> "StreamOut":
        stats = stats or CampaignStats()
        known = {o.offer_id for o in s.offers}
        offers = sorted(s.offers, key=lambda o: (not o.is_active, o.id or 0))  # активные сверху, архив снизу
        return cls(
            id=s.id,
            name=s.name,
            position=s.position,
            has_offers=s.has_offers,
            dirty=s.dirty,
            shares_total=s.shares_total,
            stats=stats.for_stream(s.id),
            offers=[StreamOfferOut.from_offer(o, stats.for_offer(s.id, o.offer_id)) for o in offers],
            untracked_offers=[
                UntrackedOfferOut(offer_id=oid, stats=m) for oid, m in stats.offers_of(s.id).items() if oid not in known
            ],
        )


class CampaignDetailOut(CampaignOut):
    date_from: str
    date_to: str
    stats_error: str | None
    streams: list[StreamOut]


class HistoryOut(BaseModel):
    id: int
    stream_id: int
    action: str
    before: list[dict]
    after: list[dict]
    created_at: datetime | None

    @classmethod
    def from_log(cls, r: PushLog) -> "HistoryOut":
        return cls(
            id=r.id, stream_id=r.stream_id, action=r.action, before=r.before, after=r.after, created_at=r.created_at
        )
