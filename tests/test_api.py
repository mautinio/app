import pytest

from app.keitaro import fake as fake_keitaro

pytestmark = pytest.mark.asyncio

# демо-кампания в фейковом Keitaro: 7, потоки 11 (AU -> google, без офферов) и 12 (3749 и 3717 по 50%)


def kt_shares(stream_id):
    s = next(s for s in fake_keitaro.state["streams"] if s["id"] == stream_id)
    return {o["offer_id"]: o["share"] for o in s["offers"]}


def view(stream):
    return {o["offer_id"]: (o["status"], o["share"]) for o in stream["offers"]}


async def fetch(client, cid=7):
    r = await client.post(f"/api/campaigns/{cid}/fetch")
    assert r.status_code == 200, r.text
    return (await client.get(f"/api/campaigns/{cid}")).json()


def stream_of(campaign, sid):
    return next(s for s in campaign["streams"] if s["id"] == sid)


async def test_create_campaign(client):
    r = await client.post(
        "/api/campaigns",
        json={
            "name": "test camp",
            "geo": "au, mx",
            "offer_id": 3801,
            "domain_id": 1,
            "group_id": 1,
            "traffic_source_id": 2,
        },
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["geo"] == ["AU", "MX"] and c["created_by_wrapper"]
    assert c["url"] == f"https://in.posdk.xyz/{c['alias']}"

    camp = next(x for x in fake_keitaro.state["campaigns"] if x["id"] == c["id"])
    assert (camp["domain_id"], camp["group_id"], camp["traffic_source_id"]) == (1, 1, 2)
    geo, offers = sorted(
        (s for s in fake_keitaro.state["streams"] if s["campaign_id"] == c["id"]), key=lambda s: s["position"]
    )
    assert geo["schema"] == "redirect" and geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}]
    assert geo["offers"] == []
    assert offers["schema"] == "landings" and offers["filters"] == []
    assert kt_shares(offers["id"]) == {3801: 100}

    # кампания сразу загружена в обёртку
    detail = (await client.get(f"/api/campaigns/{c['id']}")).json()
    assert [s["has_offers"] for s in detail["streams"]] == [False, True]
    assert view(detail["streams"][1]) == {3801: ("active", 100)}
    assert (await client.get("/api/campaigns")).json()[0]["id"] == c["id"]


async def test_create_campaign_validation(client):
    assert (
        await client.post("/api/campaigns", json={"name": "x", "geo": "Australia", "offer_id": 3801})
    ).status_code == 400
    assert (await client.post("/api/campaigns", json={"name": "x", "geo": "AU", "offer_id": 999999})).status_code == 404


async def test_create_rolls_back_on_stream_error(app, client, monkeypatch):
    from app.keitaro import KeitaroError

    async def boom(**_):
        raise KeitaroError(500, "boom")

    monkeypatch.setattr(app.state.keitaro, "create_offers_stream", boom)
    r = await client.post("/api/campaigns", json={"name": "x", "geo": "AU", "offer_id": 3801})
    assert r.status_code == 502
    assert fake_keitaro.state["campaigns"][-1]["state"] == "deleted"


async def test_fetch(client):
    c = await fetch(client)
    assert [s["id"] for s in c["streams"]] == [11, 12]
    assert stream_of(c, 11)["has_offers"] is False
    s12 = stream_of(c, 12)
    assert view(s12) == {3749: ("active", 50), 3717: ("active", 50)}
    assert not s12["dirty"]


async def test_add_is_draft_until_push(client):
    await fetch(client)
    s = (await client.post("/api/streams/12/offers", json={"offer_id": 3900})).json()
    assert view(s) == {3749: ("active", 34), 3717: ("active", 33), 3900: ("active", 33)}
    assert s["dirty"]
    assert kt_shares(12) == {3749: 50, 3717: 50}  # Keitaro не тронут

    # черновик переживает перезагрузку страницы
    assert stream_of((await client.get("/api/campaigns/7")).json(), 12)["dirty"]

    s = (await client.post("/api/streams/12/push")).json()
    assert not s["dirty"]
    assert kt_shares(12) == {3749: 34, 3717: 33, 3900: 33}


async def test_cancel_drops_added_offers(client):
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    await client.post("/api/streams/12/offers/3749/remove")
    s = (await client.post("/api/streams/12/cancel")).json()
    assert view(s) == {3749: ("active", 50), 3717: ("active", 50)}
    assert not s["dirty"]
    assert kt_shares(12) == {3749: 50, 3717: 50}


async def test_remove_archives_and_bring_back(client):
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    await client.post("/api/streams/12/push")

    s = (await client.post("/api/streams/12/offers/3749/remove")).json()
    assert view(s) == {3717: ("active", 50), 3900: ("active", 50), 3749: ("removed", 0)}
    assert s["dirty"]
    await client.post("/api/streams/12/push")
    assert kt_shares(12) == {3717: 50, 3900: 50}  # из Keitaro исчез

    c = (await client.get("/api/campaigns/7")).json()
    assert view(stream_of(c, 12))[3749] == ("removed", 0)  # а у нас остался в архиве

    s = (await client.post("/api/streams/12/offers/3749/bring-back")).json()
    assert s["dirty"] and view(s)[3749] == ("active", 34)
    await client.post("/api/streams/12/push")
    assert kt_shares(12) == {3749: 34, 3717: 33, 3900: 33}


async def test_remove_unpublished_offer_disappears(client):
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    s = (await client.post("/api/streams/12/offers/3900/remove")).json()
    assert view(s) == {3749: ("active", 50), 3717: ("active", 50)}
    assert not s["dirty"]


async def test_fetch_marks_offers_deleted_in_keitaro_as_removed(client):
    await fetch(client)
    # пользователь удалил оффер прямо в Keitaro
    stream = next(s for s in fake_keitaro.state["streams"] if s["id"] == 12)
    stream["offers"] = [o for o in stream["offers"] if o["offer_id"] != 3749]
    stream["offers"][0]["share"] = 100
    c = await fetch(client)
    s12 = stream_of(c, 12)
    assert view(s12) == {3717: ("active", 100), 3749: ("removed", 0)}
    assert not s12["dirty"]
    s = (await client.post("/api/streams/12/offers/3749/bring-back")).json()
    assert view(s) == {3717: ("active", 50), 3749: ("active", 50)}


async def test_pin(client):
    # сценарий из видео: 4 оффера по 25%, пиним один, удаляем два, возвращаем один
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    await client.post("/api/streams/12/offers", json={"offer_id": 3901})
    await client.post("/api/streams/12/push")
    assert kt_shares(12) == {3749: 25, 3717: 25, 3900: 25, 3901: 25}

    await client.post("/api/streams/12/offers/3717/pin", json={"pinned": True})
    await client.post("/api/streams/12/offers/3749/remove")
    s = (await client.post("/api/streams/12/offers/3900/remove")).json()
    assert view(s)[3717] == ("active", 25) and view(s)[3901] == ("active", 75)
    s = (await client.post("/api/streams/12/offers/3749/bring-back")).json()
    assert view(s)[3717] == ("active", 25)
    assert view(s)[3749][1] + view(s)[3901][1] == 75
    await client.post("/api/streams/12/push")
    assert kt_shares(12)[3717] == 25 and sum(kt_shares(12).values()) == 100


async def test_manual_share_pins(client):
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    s = (await client.put("/api/streams/12/offers/3900/share", json={"share": 60})).json()
    assert view(s) == {3749: ("active", 20), 3717: ("active", 20), 3900: ("active", 60)}
    assert next(o for o in s["offers"] if o["offer_id"] == 3900)["pinned"]
    assert (await client.put("/api/streams/12/offers/3900/share", json={"share": 101})).status_code == 400


async def test_errors(client):
    await fetch(client)
    assert (await client.post("/api/streams/12/offers", json={"offer_id": 3749})).status_code == 409
    assert (await client.post("/api/streams/999/offers", json={"offer_id": 3900})).status_code == 404
    assert (await client.post("/api/streams/12/offers/3749/bring-back")).status_code == 400
    await client.post("/api/streams/12/offers/3749/remove")
    await client.post("/api/streams/12/offers/3717/remove")
    r = await client.post("/api/streams/12/push")
    assert r.status_code == 400 and "активных" in r.json()["detail"]
    assert kt_shares(12) == {3749: 50, 3717: 50}
    assert (await client.get("/api/campaigns/123456")).status_code == 404


async def test_stats(client):
    c = await fetch(client)
    c = (await client.get("/api/campaigns/7?date_from=2026-11-01&date_to=2026-11-13")).json()
    s12 = stream_of(c, 12)
    assert s12["stats"]["clicks"] == sum(o["stats"]["clicks"] for o in s12["offers"])


async def test_history(client):
    await fetch(client)
    await client.post("/api/streams/12/offers", json={"offer_id": 3900})
    await client.post("/api/streams/12/push")
    await client.post("/api/streams/12/offers/3900/remove")
    await client.post("/api/streams/12/cancel")
    h = (await client.get("/api/campaigns/7/history")).json()
    assert [x["action"] for x in h[:2]] == ["cancel", "push"]


async def test_offer_search(client):
    assert (await client.get("/api/offers?q=3717")).json()[0]["id"] == 3717
    assert {o["id"] for o in (await client.get("/api/offers?q=keto")).json()} == {3900, 3901}
