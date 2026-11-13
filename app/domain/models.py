"""Доменные сущности — локальное зеркало кампаний Keitaro.

Сущности одновременно ORM-модели (прагматичный компромисс: отдельный слой «чистых» классов + маппинг
здесь ничего бы не дал) и носители бизнес-правил. Сервисы только загружают агрегат, вызывают его метод
и сохраняют — правила черновика, пинов и архива живут здесь.

Агрегат — `Stream` с его привязками `StreamOffer`. У привязки два состояния:
- черновик (`status`, `share`) — то, что видит и меняет пользователь;
- опубликованное (`pushed_status`, `pushed_share`) — то, что сейчас в Keitaro; `None` — ещё не публиковалась.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.errors import Conflict, InvalidOperation, NotFound
from app.domain.shares import split_evenly

FULL_SHARE = 100


class OfferStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # = ID в Keitaro
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    geo: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # если создана нашим создатором
    created_by_wrapper: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position"
    )

    @property
    def visible_streams(self) -> list["Stream"]:
        return [s for s in self.streams if not s.deleted]

    def stream(self, stream_id: int) -> "Stream | None":
        return next((s for s in self.streams if s.id == stream_id), None)


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # = ID в Keitaro
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)  # поток удалён в Keitaro

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )

    # ------------------------------------------------------------ состояние

    @property
    def has_offers(self) -> bool:
        """Потоки без офферов (например, редирект на google) редактор не трогает."""
        return bool(self.offers)

    @property
    def dirty(self) -> bool:
        """Есть неопубликованные изменения — поток «жёлтый»."""
        return any(o.dirty for o in self.offers)

    @property
    def active_offers(self) -> list["StreamOffer"]:
        return [o for o in self.offers if o.is_active]

    @property
    def shares_total(self) -> int:
        return sum(o.share for o in self.active_offers)

    def offer(self, offer_id: int) -> "StreamOffer":
        found = self._find(offer_id)
        if found is None:
            raise NotFound(f"Оффера #{offer_id} нет в потоке")
        return found

    def _find(self, offer_id: int) -> "StreamOffer | None":
        return next((o for o in self.offers if o.offer_id == offer_id), None)

    def snapshot(self) -> list[dict]:
        return [o.snapshot() for o in self.offers]

    # ------------------------------------------------------------ правка черновика

    def add_offer(self, offer_id: int, name: str) -> None:
        existing = self._find(offer_id)
        if existing is not None and existing.is_active:
            raise Conflict(f"Оффер #{offer_id} уже есть в потоке")
        if existing is not None:
            existing.restore()  # был в архиве — то же, что Bring Back
        else:
            self.offers.append(StreamOffer(offer_id=offer_id, offer_name=name, status=OfferStatus.ACTIVE, share=0))
        self.rebalance()

    def remove_offer(self, offer_id: int) -> None:
        offer = self.offer(offer_id)
        if not offer.is_active:
            raise InvalidOperation(f"Оффер #{offer_id} уже удалён")
        if offer.is_published_ever:
            offer.archive()
        else:
            self.offers.remove(offer)  # черновая привязка — просто выбрасываем
        self.rebalance()

    def bring_back(self, offer_id: int) -> None:
        offer = self.offer(offer_id)
        if offer.is_active:
            raise InvalidOperation(f"Оффер #{offer_id} и так активен")
        offer.restore()
        self.rebalance()

    def set_pinned(self, offer_id: int, pinned: bool) -> None:
        offer = self.offer(offer_id)
        if pinned and not offer.is_active:
            raise InvalidOperation("Закрепить можно только активный оффер")
        offer.pinned = pinned

    def set_share(self, offer_id: int, share: int) -> None:
        """Ручная доля: оффер закрепляется с этим значением, остальные делят остаток."""
        if not 0 <= share <= FULL_SHARE:
            raise InvalidOperation("Доля должна быть от 0 до 100")
        offer = self.offer(offer_id)
        if not offer.is_active:
            raise InvalidOperation("Нельзя задать долю удалённому офферу — сначала верните его (Bring Back)")
        offer.share = share
        offer.pinned = True
        self.rebalance()

    def rebalance(self) -> None:
        """Закреплённые доли не трогаем, остаток до 100% делим поровну между остальными активными."""
        active = self.active_offers
        pinned = [o for o in active if o.pinned]
        free = [o for o in active if not o.pinned]
        pinned_total = sum(o.share for o in pinned)
        rest = FULL_SHARE - pinned_total
        if rest < 0:
            raise InvalidOperation(f"Закреплённые доли в сумме {pinned_total}% — больше 100%")
        if not free:
            if active and rest:
                raise InvalidOperation(
                    f"Все активные офферы закреплены, их доли в сумме {pinned_total}% вместо 100%. "
                    "Открепите хотя бы один оффер, чтобы доли можно было пересчитать."
                )
            return
        for offer, share in zip(free, split_evenly(rest, len(free)), strict=True):
            offer.share = share

    def discard_draft(self) -> None:
        """Cancel: вернуть опубликованное состояние, черновые привязки удалить."""
        for offer in list(self.offers):
            if offer.is_published_ever:
                offer.revert()
            else:
                self.offers.remove(offer)

    # ------------------------------------------------------------ публикация

    def publishable_offers(self) -> dict[int, int]:
        """{offer_id: share} для отправки в Keitaro; проверяет, что черновик можно публиковать."""
        active = self.active_offers
        if not active:
            raise InvalidOperation("В потоке не осталось активных офферов — Keitaro некуда будет отправлять трафик")
        if self.shares_total != FULL_SHARE:
            raise InvalidOperation(f"Сумма долей должна быть 100%, сейчас {self.shares_total}%")
        return {o.offer_id: o.share for o in active}

    def sync_published(self, published: dict[int, int], names: dict[int, str]) -> None:
        """Принять состояние из Keitaro как опубликованное и как черновик.

        Офферы, которых больше нет в Keitaro, уходят в архив (removed); черновые — отбрасываются.
        """
        for offer_id, share in published.items():
            offer = self._find(offer_id)
            if offer is None:
                offer = StreamOffer(offer_id=offer_id, offer_name="")
                self.offers.append(offer)
            offer.offer_name = names.get(offer_id) or offer.offer_name
            offer.mark_published(OfferStatus.ACTIVE, share)
        for offer in list(self.offers):
            if offer.offer_id in published:
                continue
            if offer.is_published_ever:
                offer.mark_published(OfferStatus.REMOVED, 0)
            else:
                self.offers.remove(offer)


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer)  # ID оффера в Keitaro
    offer_name: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default=OfferStatus.ACTIVE)
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    pushed_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pushed_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def is_active(self) -> bool:
        return self.status == OfferStatus.ACTIVE

    @property
    def is_published_ever(self) -> bool:
        return self.pushed_status is not None

    @property
    def is_live(self) -> bool:
        """Сейчас стоит в Keitaro."""
        return self.pushed_status == OfferStatus.ACTIVE

    @property
    def dirty(self) -> bool:
        if not self.is_published_ever:
            return self.is_active
        return (self.status, self.share) != (self.pushed_status, self.pushed_share)

    def archive(self) -> None:
        self.status = OfferStatus.REMOVED
        self.share = 0
        self.pinned = False

    def restore(self) -> None:
        self.status = OfferStatus.ACTIVE

    def revert(self) -> None:
        self.status = self.pushed_status
        self.share = self.pushed_share or 0

    def mark_published(self, status: OfferStatus, share: int) -> None:
        self.status = self.pushed_status = status
        self.share = self.pushed_share = share

    def snapshot(self) -> dict:
        return {"offer_id": self.offer_id, "status": self.status, "share": self.share, "pinned": self.pinned}


class PushLog(Base):
    """Журнал публикаций в Keitaro и отмен черновиков."""

    __tablename__ = "push_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(16))  # push / cancel
    before: Mapped[list] = mapped_column(JSON)
    after: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
