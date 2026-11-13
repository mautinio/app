from fastapi import APIRouter, Query

from app.api.deps import KeitaroDep, SettingsDep
from app.api.schemas import Defaults, KeitaroCampaignOut, MetaOut, OfferOut, RefOut
from app.keitaro import Ref

router = APIRouter(tags=["catalog"])


def _refs(items: list[Ref]) -> list[RefOut]:
    return [RefOut(id=r.id, name=r.name) for r in items]


def _matches(query: str, *fields: object) -> bool:
    return any(query in str(f).lower() for f in fields)


@router.get("/meta", response_model=MetaOut)
async def meta(keitaro: KeitaroDep, settings: SettingsDep):
    return MetaOut(
        mock=settings.use_mock,
        keitaro_admin_url=settings.keitaro_admin_url,
        geo_redirect_url=settings.geo_redirect_url,
        defaults=Defaults(
            domain_id=settings.default_domain_id,
            group_id=settings.default_group_id,
            traffic_source_id=settings.default_traffic_source_id,
        ),
        domains=_refs(await keitaro.domains()),
        groups=_refs(await keitaro.campaign_groups()),
        traffic_sources=_refs(await keitaro.traffic_sources()),
    )


@router.get("/offers", response_model=list[OfferOut])
async def search_offers(keitaro: KeitaroDep, q: str = "", limit: int = Query(20, le=100)):
    q = q.strip().lower()
    offers = [o for o in await keitaro.offers() if o.state != "deleted" and _matches(q, o.id, o.name)]
    offers.sort(key=lambda o: (str(o.id) != q, -o.id))  # точное совпадение ID — первым, дальше новые
    return [OfferOut(id=o.id, name=o.name, state=o.state) for o in offers[:limit]]


@router.get("/keitaro/campaigns", response_model=list[KeitaroCampaignOut])
async def keitaro_campaigns(keitaro: KeitaroDep, q: str = ""):
    """Поиск кампаний прямо в Keitaro — чтобы загрузить любую из них в обёртку."""
    q = q.strip().lower()
    found = [c for c in await keitaro.campaigns() if c.state != "deleted" and _matches(q, c.id, c.name, c.alias)]
    found.sort(key=lambda c: -c.id)
    return [KeitaroCampaignOut(id=c.id, name=c.name, alias=c.alias, state=c.state) for c in found[:100]]
