from collections.abc import Callable

from app.domain.errors import NotFound
from app.domain.models import PushLog, Stream
from app.keitaro import KeitaroClient
from app.repositories import CampaignRepository


class StreamEditor:
    """Сценарии редактора: правка черновика потока, публикация и отмена.

    Сами правила — в `Stream`; здесь только загрузить, применить, сохранить.
    """

    def __init__(self, keitaro: KeitaroClient, repo: CampaignRepository):
        self._keitaro = keitaro
        self._repo = repo

    async def add_offer(self, stream_id: int, offer_id: int) -> Stream:
        offer = await self._keitaro.find_offer(offer_id)
        if offer is None:
            raise NotFound(f"Оффер #{offer_id} не найден в Keitaro")
        return await self._edit(stream_id, lambda s: s.add_offer(offer.id, offer.name))

    async def remove_offer(self, stream_id: int, offer_id: int) -> Stream:
        return await self._edit(stream_id, lambda s: s.remove_offer(offer_id))

    async def bring_back(self, stream_id: int, offer_id: int) -> Stream:
        return await self._edit(stream_id, lambda s: s.bring_back(offer_id))

    async def set_pinned(self, stream_id: int, offer_id: int, pinned: bool) -> Stream:
        return await self._edit(stream_id, lambda s: s.set_pinned(offer_id, pinned))

    async def set_share(self, stream_id: int, offer_id: int, share: int) -> Stream:
        return await self._edit(stream_id, lambda s: s.set_share(offer_id, share))

    async def push(self, stream_id: int) -> Stream:
        stream = await self._repo.get_stream(stream_id)
        before = stream.snapshot()
        published = await self._keitaro.update_stream_offers(stream_id, stream.publishable_offers())
        stream.sync_published(published.offers, {o.offer_id: o.offer_name for o in stream.offers})
        self._log(stream, "push", before)
        await self._repo.commit()
        return stream

    async def cancel(self, stream_id: int) -> Stream:
        stream = await self._repo.get_stream(stream_id)
        if stream.dirty:
            before = stream.snapshot()
            stream.discard_draft()
            self._log(stream, "cancel", before)
            await self._repo.commit()
        return stream

    async def _edit(self, stream_id: int, change: Callable[[Stream], None]) -> Stream:
        stream = await self._repo.get_stream(stream_id)
        change(stream)  # доменная ошибка прерывает до commit — черновик в БД не меняется
        await self._repo.commit()
        return stream

    def _log(self, stream: Stream, action: str, before: list[dict]) -> None:
        log = PushLog(
            campaign_id=stream.campaign_id, stream_id=stream.id, action=action, before=before, after=stream.snapshot()
        )
        self._repo.add(log)
