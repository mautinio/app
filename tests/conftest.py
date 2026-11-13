import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp}/test.db"
os.environ["APP_ENV_FILE"] = ""
os.environ["KEITARO_MOCK"] = "true"
os.environ["KEITARO_URL"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.domain.models import Campaign, PushLog, Stream, StreamOffer  # noqa: E402
from app.keitaro import fake  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrate():
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")


@pytest_asyncio.fixture
async def app():
    fake.reset()
    async with SessionLocal() as db:
        for model in (PushLog, StreamOffer, Stream, Campaign):
            await db.execute(delete(model))
        await db.commit()
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
