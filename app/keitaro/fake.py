"""In-memory имитация нужной части Keitaro Admin API v1.

Используется в тестах и в демо-режиме (KEITARO_MOCK=true или пустой KEITARO_URL),
чтобы проект можно было запустить и потрогать без доступа к реальному трекеру.
"""

import hashlib
import itertools
from copy import deepcopy

from fastapi import FastAPI, Header, HTTPException, Request

fake_app = FastAPI()

SEED = {
    "domains": [{"id": 1, "name": "in.posdk.xyz"}, {"id": 2, "name": "go.example-track.com"}],
    "groups": [{"id": 1, "name": "FORTESTS", "type": "campaigns"}, {"id": 2, "name": "MAIN", "type": "campaigns"}],
    "traffic_sources": [{"id": 1, "name": "FORTESTS"}, {"id": 2, "name": "Facebook"}],
    "offers": [
        {
            "id": 3717,
            "name": "Miaflow [BEAUTY-RO-BE_0008] [pl - prize ro -] 1. Основной, Румыния JS",
            "state": "active",
        },
        {"id": 3749, "name": "Miaflow [BEAUTY-RO-BE_0009] [pl - spin ro -] 2. Основной, Румыния JS", "state": "active"},
        {"id": 3801, "name": "Cardioton [HEALTH-MX_0012] Мексика", "state": "active"},
        {"id": 3802, "name": "Cardioton [HEALTH-MX_0013] Мексика, прелендинг", "state": "active"},
        {"id": 3900, "name": "Keto Slim [DIET-AU_0001] Австралия", "state": "active"},
        {"id": 3901, "name": "Keto Slim [DIET-AU_0002] Австралия JS", "state": "active"},
    ],
}

state: dict = {}
_ids = itertools.count(100)


def reset() -> None:
    global _ids
    state.clear()
    state.update(deepcopy(SEED))
    state["campaigns"] = [
        {
            "id": 7,
            "name": "campaign 2",
            "alias": "wVqN1R",
            "type": "position",
            "state": "active",
            "domain_id": 1,
            "group_id": 1,
            "traffic_source_id": 1,
        },
    ]
    state["streams"] = [
        {
            "id": 11,
            "campaign_id": 7,
            "name": "Flow 1",
            "type": "regular",
            "position": 1,
            "state": "active",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": "https://google.com",
            "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}],
            "offers": [],
        },
        {
            "id": 12,
            "campaign_id": 7,
            "name": "Flow 2",
            "type": "regular",
            "position": 2,
            "state": "active",
            "schema": "landings",
            "action_type": "http",
            "action_payload": None,
            "filters": [],
            "offers": [
                {"id": 1, "offer_id": 3749, "share": 50, "state": "active"},
                {"id": 2, "offer_id": 3717, "share": 50, "state": "active"},
            ],
        },
    ]
    _ids = itertools.count(100)


reset()


def _auth(key: str | None) -> None:
    if not key:
        raise HTTPException(401, "Unauthorized")


def _find(kind: str, item_id: int) -> dict:
    for item in state[kind]:
        if item["id"] == item_id:
            return item
    raise HTTPException(404, f"{kind} {item_id} not found")


@fake_app.exception_handler(HTTPException)
async def _err(_, exc: HTTPException):
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@fake_app.get("/admin_api/v1/{kind}")
async def list_items(kind: str, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    if kind not in ("domains", "groups", "traffic_sources", "offers", "campaigns"):
        raise HTTPException(404, "not found")
    return state[kind]


@fake_app.get("/admin_api/v1/campaigns/{cid}")
async def get_campaign(cid: int, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    return _find("campaigns", cid)


@fake_app.post("/admin_api/v1/campaigns")
async def create_campaign(request: Request, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    body = await request.json()
    if not body.get("name") or not body.get("alias"):
        raise HTTPException(400, "name and alias are required")
    if any(c["alias"] == body["alias"] for c in state["campaigns"]):
        raise HTTPException(400, "alias already taken")
    domain = next((d for d in state["domains"] if d["id"] == body.get("domain_id")), None)
    camp = {"id": next(_ids), **body, "domain": f"https://{domain['name']}/" if domain else None}
    state["campaigns"].append(camp)
    return camp


@fake_app.delete("/admin_api/v1/campaigns/{cid}")
async def delete_campaign(cid: int, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    _find("campaigns", cid)["state"] = "deleted"
    return None


@fake_app.get("/admin_api/v1/campaigns/{cid}/streams")
async def campaign_streams(cid: int, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    _find("campaigns", cid)
    return [s for s in state["streams"] if s["campaign_id"] == cid]


def _norm_offers(stream_id: int, offers: list[dict]) -> list[dict]:
    known = {o["id"] for o in state["offers"]}
    out = []
    for o in offers:
        if o["offer_id"] not in known:
            raise HTTPException(400, f"offer {o['offer_id']} not found")
        out.append(
            {
                "id": next(_ids),
                "stream_id": stream_id,
                "offer_id": o["offer_id"],
                "share": int(o.get("share", 100)),
                "state": o.get("state", "active"),
            }
        )
    return out


@fake_app.post("/admin_api/v1/streams")
async def create_stream(request: Request, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    body = await request.json()
    _find("campaigns", body["campaign_id"])
    sid = next(_ids)
    stream = {"id": sid, "state": "active", "filters": [], **body}
    stream["offers"] = _norm_offers(sid, body.get("offers") or [])
    state["streams"].append(stream)
    return stream


@fake_app.put("/admin_api/v1/streams/{sid}")
async def update_stream(sid: int, request: Request, api_key: str | None = Header(None, alias="Api-Key")):
    _auth(api_key)
    stream = _find("streams", sid)
    body = await request.json()
    if "offers" in body:
        body["offers"] = _norm_offers(sid, body["offers"])
    stream.update(body)
    return stream


def _fake_num(*parts) -> int:
    return int(hashlib.md5(":".join(map(str, parts)).encode()).hexdigest()[:6], 16)


@fake_app.post("/admin_api/v1/report/build")
async def report(request: Request, api_key: str | None = Header(None, alias="Api-Key")):
    """Детерминированные «клики» на (поток, оффер, период), чтобы цифры в демо были стабильными."""
    _auth(api_key)
    body = await request.json()
    cid = next(f["expression"] for f in body["filters"] if f["name"] == "campaign_id")
    period = f"{body['range']['from']}..{body['range']['to']}"
    pairs = []
    for s in state["streams"]:
        if s["campaign_id"] != cid:
            continue
        if s["offers"]:
            pairs += [(s, o) for o in s["offers"]]
        else:
            pairs.append((s, None))
    raw = []
    for s, o in pairs:
        clicks = _fake_num(s["id"], o and o["offer_id"], period) % 400
        if o:
            clicks = clicks * o["share"] // 100
        conv = clicks // 25
        raw.append(
            {
                "stream_id": s["id"],
                "offer_id": o["offer_id"] if o else None,
                "clicks": clicks,
                "stream_unique_clicks": clicks * 9 // 10,
                "bots": clicks // 20,
                "conversions": conv,
                "sales": conv // 2,
                "revenue": round(conv * 7.5, 2),
                "cost": 0,
                "profit": round(conv * 7.5, 2),
            }
        )
    grouping = body.get("grouping", [])
    metrics = body.get("metrics", [])
    agg: dict = {}
    for r in raw:
        key = tuple(r[g] for g in grouping)
        row = agg.setdefault(key, {**{g: r[g] for g in grouping}, **{m: 0 for m in metrics}})
        for m in metrics:
            row[m] += r.get(m, 0)
    rows = [r for r in agg.values() if all(r[g] is not None for g in grouping)]
    return {"rows": rows, "total": len(rows)}
