"""Асинхронный клиент Keitaro Admin API v1.

Единственное место, которое знает формат JSON Keitaro: наружу отдаются типизированные DTO.
"""

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx


class KeitaroError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Keitaro API {status}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Ref:
    """Элемент справочника: домен, группа, источник."""

    id: int
    name: str


@dataclass(frozen=True)
class KtOffer:
    id: int
    name: str
    state: str


@dataclass(frozen=True)
class KtCampaign:
    id: int
    name: str
    alias: str
    state: str | None
    domain: str | None  # URL домена кампании, если задан


@dataclass(frozen=True)
class KtStream:
    id: int
    name: str
    position: int
    state: str
    offers: dict[int, int] = field(default_factory=dict)  # offer_id -> share

    @property
    def deleted(self) -> bool:
        return self.state == "deleted"


def _campaign(d: dict) -> KtCampaign:
    return KtCampaign(
        id=int(d["id"]),
        name=d.get("name") or "",
        alias=d.get("alias") or "",
        state=d.get("state"),
        domain=d.get("domain"),
    )


def _stream(d: dict) -> KtStream:
    return KtStream(
        id=int(d["id"]),
        name=d.get("name") or f"Stream {d['id']}",
        position=int(d.get("position") or 0),
        state=d.get("state") or "active",
        offers={int(o["offer_id"]): int(o.get("share") or 0) for o in d.get("offers") or []},
    )


def _refs(items: list[dict]) -> list[Ref]:
    return [Ref(id=int(i["id"]), name=i.get("name") or "") for i in items]


class KeitaroClient:
    OFFERS_TTL = 60.0  # офферы нужны автокомплиту на каждое нажатие — кэшируем

    def __init__(self, http: httpx.AsyncClient):
        self._http = http
        self._offers: tuple[float, list[KtOffer]] | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------ справочники

    async def offers(self) -> list[KtOffer]:
        now = time.monotonic()
        if self._offers is None or now - self._offers[0] > self.OFFERS_TTL:
            data = await self._request("GET", "offers")
            offers = [KtOffer(int(o["id"]), o.get("name") or "", o.get("state") or "active") for o in data]
            self._offers = (now, offers)
        return self._offers[1]

    async def find_offer(self, offer_id: int) -> KtOffer | None:
        return next((o for o in await self.offers() if o.id == offer_id), None)

    async def offer_names(self) -> dict[int, str]:
        return {o.id: o.name for o in await self.offers()}

    async def domains(self) -> list[Ref]:
        return _refs(await self._request("GET", "domains"))

    async def campaign_groups(self) -> list[Ref]:
        return _refs(await self._request("GET", "groups", params={"type": "campaigns"}))

    async def traffic_sources(self) -> list[Ref]:
        return _refs(await self._request("GET", "traffic_sources"))

    # ------------------------------------------------------------ кампании и потоки

    async def campaigns(self) -> list[KtCampaign]:
        return [_campaign(c) for c in await self._request("GET", "campaigns")]

    async def campaign(self, campaign_id: int) -> KtCampaign:
        return _campaign(await self._request("GET", f"campaigns/{campaign_id}"))

    async def create_campaign(
        self, *, name: str, alias: str, domain_id: int | None, group_id: int | None, traffic_source_id: int | None
    ) -> KtCampaign:
        data = await self._request(
            "POST",
            "campaigns",
            json={
                "name": name,
                "alias": alias,
                "type": "position",
                "state": "active",
                "domain_id": domain_id,
                "group_id": group_id or 0,
                "traffic_source_id": traffic_source_id or 0,
                "cost_type": "CPC",
                "cost_value": 0,
                "cost_currency": "USD",
                "cost_auto": True,
            },
        )
        return _campaign(data)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"campaigns/{campaign_id}")

    async def streams(self, campaign_id: int) -> list[KtStream]:
        return [_stream(s) for s in await self._request("GET", f"campaigns/{campaign_id}/streams")]

    async def create_redirect_stream(
        self, *, campaign_id: int, name: str, position: int, url: str, countries: list[str]
    ) -> KtStream:
        """Поток «страны из списка -> редирект на url»."""
        return await self._create_stream(
            campaign_id=campaign_id,
            name=name,
            position=position,
            schema="redirect",
            action_payload=url,
            filters=[{"name": "country", "mode": "accept", "payload": countries}],
        )

    async def create_offers_stream(
        self, *, campaign_id: int, name: str, position: int, offers: dict[int, int]
    ) -> KtStream:
        """Поток без фильтров, ведёт прямо на офферы (без лендингов)."""
        return await self._create_stream(
            campaign_id=campaign_id,
            name=name,
            position=position,
            schema="landings",
            landings=[],
            offers=self._offers_payload(offers),
        )

    async def update_stream_offers(self, stream_id: int, offers: dict[int, int]) -> KtStream:
        """Полностью заменяет офферы потока."""
        return _stream(
            await self._request("PUT", f"streams/{stream_id}", json={"offers": self._offers_payload(offers)})
        )

    async def _create_stream(self, *, campaign_id: int, name: str, position: int, **extra: Any) -> KtStream:
        payload = {
            "campaign_id": campaign_id,
            "name": name,
            "type": "regular",
            "position": position,
            "weight": 100,
            "state": "active",
            "action_type": "http",
            "collect_clicks": True,
            "filter_or": False,
            "filters": [],
            **extra,
        }
        return _stream(await self._request("POST", "streams", json=payload))

    @staticmethod
    def _offers_payload(offers: dict[int, int]) -> list[dict]:
        return [{"offer_id": oid, "share": share, "state": "active"} for oid, share in offers.items()]

    # ------------------------------------------------------------ отчёты

    async def report(
        self,
        *,
        campaign_id: int,
        date_from: date,
        date_to: date,
        timezone: str,
        grouping: list[str],
        metrics: list[str],
    ) -> list[dict]:
        data = await self._request(
            "POST",
            "report/build",
            json={
                "range": {"from": date_from.isoformat(), "to": date_to.isoformat(), "timezone": timezone},
                "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_id}],
                "grouping": grouping,
                "metrics": metrics,
                "limit": 10000,
            },
        )
        return data.get("rows", [])

    # ------------------------------------------------------------ транспорт

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise KeitaroError(502, f"не удалось связаться с Keitaro: {e}") from e
        if response.status_code >= 400:
            raise KeitaroError(response.status_code, self._error_text(response))
        return response.json() if response.content else None

    @staticmethod
    def _error_text(response: httpx.Response) -> str:
        try:
            body = response.json()
            message = body.get("error") or body.get("message") or response.text
        except (ValueError, AttributeError):
            message = response.text
        return str(message)[:500]


def create_keitaro_client(*, base_url: str | None, api_key: str, timeout: float) -> KeitaroClient:
    """Клиент к настоящему Keitaro или, если base_url пуст, к встроенному фейку (демо и тесты)."""
    if not base_url:
        from app.keitaro.fake import fake_app

        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fake_app),
            base_url="http://fake-keitaro/admin_api/v1/",
            headers={"Api-Key": "mock"},
        )
    else:
        http = httpx.AsyncClient(
            base_url=f"{base_url}/admin_api/v1/",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )
    return KeitaroClient(http)
