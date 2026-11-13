"""Доменные правила — без БД, HTTP и Keitaro."""

import pytest

from app.domain.errors import Conflict, InvalidOperation, NotFound
from app.domain.geo import parse_countries
from app.domain.models import OfferStatus, Stream
from app.domain.shares import split_evenly

A, R = OfferStatus.ACTIVE, OfferStatus.REMOVED


@pytest.mark.parametrize("n", range(1, 101))
def test_split_evenly_sums_to_total(n):
    shares = split_evenly(100, n)
    assert len(shares) == n and sum(shares) == 100
    assert max(shares) - min(shares) <= 1


def test_split_examples():
    assert split_evenly(100, 2) == [50, 50]
    assert split_evenly(100, 3) == [34, 33, 33]
    assert split_evenly(75, 2) == [38, 37]
    assert split_evenly(100, 0) == []


def test_parse_countries():
    assert parse_countries("mx, AU;ro  au") == ["MX", "AU", "RO"]
    with pytest.raises(InvalidOperation):
        parse_countries("Australia")
    with pytest.raises(InvalidOperation):
        parse_countries(" , ")


def published_stream(**shares: int) -> Stream:
    """Поток, опубликованный в Keitaro с долями {offer_id: share} (ключи вида o3749)."""
    stream = Stream(id=1, name="s", offers=[])
    stream.sync_published({int(k[1:]): v for k, v in shares.items()}, {})
    return stream


def view(stream: Stream) -> dict[int, tuple[str, int]]:
    return {o.offer_id: (o.status, o.share) for o in stream.offers}


def test_add_creates_draft():
    s = published_stream(o1=50, o2=50)
    s.add_offer(3, "new")
    assert view(s) == {1: (A, 34), 2: (A, 33), 3: (A, 33)}
    assert s.dirty
    with pytest.raises(Conflict):
        s.add_offer(3, "new")


def test_remove_archives_published_and_drops_draft():
    s = published_stream(o1=50, o2=50)
    s.add_offer(3, "new")
    s.remove_offer(3)  # черновой — исчезает совсем
    assert view(s) == {1: (A, 50), 2: (A, 50)} and not s.dirty
    s.remove_offer(1)  # опубликованный — в архив
    assert view(s) == {1: (R, 0), 2: (A, 100)} and s.dirty
    with pytest.raises(InvalidOperation):
        s.remove_offer(1)


def test_bring_back_and_add_from_archive():
    s = published_stream(o1=50, o2=50)
    s.remove_offer(1)
    s.bring_back(1)
    assert view(s) == {1: (A, 50), 2: (A, 50)} and not s.dirty
    s.remove_offer(1)
    s.add_offer(1, "same")  # добавить архивный = вернуть
    assert view(s)[1] == (A, 50)


def test_discard_draft():
    s = published_stream(o1=50, o2=50)
    s.add_offer(3, "new")
    s.remove_offer(1)
    s.discard_draft()
    assert view(s) == {1: (A, 50), 2: (A, 50)} and not s.dirty


def test_pinned_share_survives_rebalance():
    # сценарий из видео: 4 по 25%, закрепляем один, удаляем два, возвращаем один -> 38/25/37
    s = published_stream(o1=25, o2=25, o3=25, o4=25)
    s.set_pinned(2, True)
    s.remove_offer(1)
    s.remove_offer(3)
    assert view(s)[2] == (A, 25) and view(s)[4] == (A, 75)
    s.bring_back(1)
    assert [view(s)[i][1] for i in (1, 2, 4)] == [38, 25, 37]


def test_manual_share_pins_offer():
    s = published_stream(o1=34, o2=33, o3=33)
    s.set_share(3, 60)
    assert view(s) == {1: (A, 20), 2: (A, 20), 3: (A, 60)}
    assert s.offer(3).pinned
    with pytest.raises(InvalidOperation):
        s.set_share(3, 101)


def test_all_pinned_must_sum_to_100():
    s = published_stream(o1=60, o2=40)
    s.set_pinned(1, True)
    s.set_pinned(2, True)
    with pytest.raises(InvalidOperation):
        s.remove_offer(2)


def test_publishable_offers_validation():
    s = published_stream(o1=50, o2=50)
    assert s.publishable_offers() == {1: 50, 2: 50}
    s.offer(1).share = 70
    with pytest.raises(InvalidOperation):
        s.publishable_offers()
    s = published_stream(o1=100)
    s.offer(1).archive()
    with pytest.raises(InvalidOperation):
        s.publishable_offers()


def test_sync_published_archives_offers_missing_in_keitaro():
    s = published_stream(o1=50, o2=50)
    s.add_offer(3, "draft")
    s.sync_published({2: 100}, {2: "two"})
    assert view(s) == {1: (R, 0), 2: (A, 100)}  # 1 в архиве, черновой 3 отброшен
    assert s.offer(2).offer_name == "two" and not s.dirty


def test_unknown_offer():
    with pytest.raises(NotFound):
        published_stream(o1=100).remove_offer(42)
