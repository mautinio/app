from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import Settings, get_settings
from app.domain.errors import Conflict, DomainError, NotFound
from app.keitaro import KeitaroError, create_keitaro_client

STATIC = Path(__file__).parent / "static"


def _domain_status(exc: DomainError) -> int:
    if isinstance(exc, NotFound):
        return 404
    if isinstance(exc, Conflict):
        return 409
    return 400


async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=_domain_status(exc))


async def _keitaro_error(_: Request, exc: KeitaroError) -> JSONResponse:
    # «Не найдено» в Keitaro — это 404 и для нашего клиента; прочие ошибки трекера — 502 Bad Gateway
    status = 404 if exc.status == 404 else 502
    return JSONResponse({"detail": f"Keitaro: {exc.message}"}, status_code=status)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.keitaro = create_keitaro_client(
            base_url=settings.tracker_url, api_key=settings.keitaro_api_key, timeout=settings.keitaro_timeout
        )
        yield
        await app.state.keitaro.aclose()

    app = FastAPI(title="Keitaro wrapper", lifespan=lifespan)
    app.include_router(router)
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(KeitaroError, _keitaro_error)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
