from dataclasses import dataclass, field
from datetime import date

from app.keitaro import KeitaroClient, KeitaroError

Metrics = dict[str, float]


@dataclass
class CampaignStats:
    """Статистика кампании за период: по потокам и по парам (поток, оффер)."""

    streams: dict[int, Metrics] = field(default_factory=dict)
    offers: dict[tuple[int, int], Metrics] = field(default_factory=dict)
    error: str | None = None

    def for_stream(self, stream_id: int) -> Metrics:
        return self.streams.get(stream_id, {})

    def for_offer(self, stream_id: int, offer_id: int) -> Metrics:
        return self.offers.get((stream_id, offer_id), {})

    def offers_of(self, stream_id: int) -> dict[int, Metrics]:
        return {oid: m for (sid, oid), m in self.offers.items() if sid == stream_id}


class StatsService:
    STREAM_METRICS = ("clicks", "stream_unique_clicks", "bots")
    OFFER_METRICS = ("clicks", "stream_unique_clicks", "bots", "conversions", "sales", "revenue", "cost", "profit")

    def __init__(self, keitaro: KeitaroClient, timezone: str):
        self._keitaro = keitaro
        self._timezone = timezone

    async def campaign_stats(self, campaign_id: int, date_from: date, date_to: date) -> CampaignStats:
        """Ошибка отчёта не должна ломать редактор — возвращаем пустую статистику с текстом ошибки."""
        stats = CampaignStats()
        try:
            period = (campaign_id, date_from, date_to)
            for row in await self._report(*period, ("stream_id",), self.STREAM_METRICS):
                stats.streams[int(row["stream_id"])] = self._metrics(row, self.STREAM_METRICS)
            for row in await self._report(*period, ("stream_id", "offer_id"), self.OFFER_METRICS):
                if row.get("stream_id") and row.get("offer_id"):
                    key = (int(row["stream_id"]), int(row["offer_id"]))
                    stats.offers[key] = self._metrics(row, self.OFFER_METRICS)
        except KeitaroError as e:
            stats.error = e.message
        return stats

    async def _report(
        self, campaign_id: int, date_from: date, date_to: date, grouping: tuple[str, ...], metrics: tuple[str, ...]
    ) -> list[dict]:
        return await self._keitaro.report(
            campaign_id=campaign_id,
            date_from=date_from,
            date_to=date_to,
            timezone=self._timezone,
            grouping=list(grouping),
            metrics=list(metrics),
        )

    @staticmethod
    def _metrics(row: dict, names: tuple[str, ...]) -> Metrics:
        def number(value) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        return {name: number(row.get(name)) for name in names}
