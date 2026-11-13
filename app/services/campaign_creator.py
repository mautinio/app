import contextlib
import secrets
import string
from dataclasses import dataclass

from app.domain.errors import InvalidOperation, NotFound
from app.domain.geo import parse_countries
from app.domain.models import FULL_SHARE, Campaign
from app.keitaro import KeitaroClient, KeitaroError
from app.services.campaign_sync import CampaignSync


@dataclass(frozen=True)
class NewCampaign:
    name: str
    geo: str | list[str]
    offer_id: int
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


@dataclass(frozen=True)
class CreatorDefaults:
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None
    redirect_url: str


class CampaignCreator:
    """Создаёт кампанию с двумя потоками: «страны -> редирект» и «все остальные -> оффер»."""

    ALIAS_LENGTH = 7

    def __init__(self, keitaro: KeitaroClient, sync: CampaignSync, defaults: CreatorDefaults):
        self._keitaro = keitaro
        self._sync = sync
        self._defaults = defaults

    async def create(self, request: NewCampaign) -> Campaign:
        name = request.name.strip()
        if not name:
            raise InvalidOperation("Укажите название кампании")
        countries = parse_countries(request.geo)
        domain_id = request.domain_id or self._defaults.domain_id
        group_id = request.group_id or self._defaults.group_id
        source_id = request.traffic_source_id or self._defaults.traffic_source_id
        await self._validate_refs(request.offer_id, domain_id, group_id, source_id)

        kt_campaign = await self._keitaro.create_campaign(
            name=name, alias=self._random_alias(), domain_id=domain_id, group_id=group_id, traffic_source_id=source_id
        )
        try:
            await self._keitaro.create_redirect_stream(
                campaign_id=kt_campaign.id,
                name=f"{','.join(countries)} -> Google",
                position=1,
                url=self._defaults.redirect_url,
                countries=countries,
            )
            await self._keitaro.create_offers_stream(
                campaign_id=kt_campaign.id, name="Offers", position=2, offers={request.offer_id: FULL_SHARE}
            )
        except KeitaroError:
            await self._delete_quietly(kt_campaign.id)  # не оставляем в трекере полусобранную кампанию
            raise
        return await self._sync.fetch(kt_campaign.id, geo=countries)

    async def _validate_refs(self, offer_id: int, domain_id: int | None, group_id: int | None, source_id: int | None):
        if await self._keitaro.find_offer(offer_id) is None:
            raise NotFound(f"Оффер #{offer_id} не найден в Keitaro")
        checks = (
            (domain_id, self._keitaro.domains, "Домен"),
            (group_id, self._keitaro.campaign_groups, "Группа"),
            (source_id, self._keitaro.traffic_sources, "Источник"),
        )
        for ref_id, load, label in checks:
            if ref_id and not any(r.id == ref_id for r in await load()):
                raise NotFound(f"{label} #{ref_id} не найден(а) в Keitaro")

    async def _delete_quietly(self, campaign_id: int) -> None:
        with contextlib.suppress(KeitaroError):
            await self._keitaro.delete_campaign(campaign_id)

    @classmethod
    def _random_alias(cls) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(cls.ALIAS_LENGTH))
