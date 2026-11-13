from fastapi import APIRouter

from app.api.deps import EditorDep
from app.api.schemas import OfferIn, PinIn, ShareIn, StreamOut

router = APIRouter(prefix="/streams/{stream_id}", tags=["stream editor"])


@router.post("/offers", response_model=StreamOut)
async def add_offer(stream_id: int, body: OfferIn, editor: EditorDep):
    return StreamOut.from_stream(await editor.add_offer(stream_id, body.offer_id))


@router.post("/offers/{offer_id}/remove", response_model=StreamOut)
async def remove_offer(stream_id: int, offer_id: int, editor: EditorDep):
    return StreamOut.from_stream(await editor.remove_offer(stream_id, offer_id))


@router.post("/offers/{offer_id}/bring-back", response_model=StreamOut)
async def bring_back(stream_id: int, offer_id: int, editor: EditorDep):
    return StreamOut.from_stream(await editor.bring_back(stream_id, offer_id))


@router.post("/offers/{offer_id}/pin", response_model=StreamOut)
async def pin(stream_id: int, offer_id: int, body: PinIn, editor: EditorDep):
    return StreamOut.from_stream(await editor.set_pinned(stream_id, offer_id, body.pinned))


@router.put("/offers/{offer_id}/share", response_model=StreamOut)
async def set_share(stream_id: int, offer_id: int, body: ShareIn, editor: EditorDep):
    return StreamOut.from_stream(await editor.set_share(stream_id, offer_id, body.share))


@router.post("/push", response_model=StreamOut)
async def push(stream_id: int, editor: EditorDep):
    return StreamOut.from_stream(await editor.push(stream_id))


@router.post("/cancel", response_model=StreamOut)
async def cancel(stream_id: int, editor: EditorDep):
    return StreamOut.from_stream(await editor.cancel(stream_id))
