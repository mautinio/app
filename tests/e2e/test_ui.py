"""Сквозной сценарий из видео в настоящем браузере (Playwright) на демо-Keitaro.

Запуск: pip install playwright && playwright install chromium && pytest tests/e2e
Без Playwright тест пропускается.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

sync_api = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    db = os.path.join(tempfile.mkdtemp(), "e2e.db")
    env = {
        **os.environ,
        "APP_ENV_FILE": "",
        "KEITARO_MOCK": "true",
        "KEITARO_URL": "",
        "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
    }
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env, check=True, capture_output=True
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(f"{url}/api/campaigns")
            break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield url
    proc.terminate()


@pytest.fixture
def page(server):
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("dialog", lambda d: d.accept())
        page.goto(server)
        yield page
        browser.close()
    assert errors == [], errors


class EditorPage:
    """Page object редактора: прячет селекторы, тест читается как сценарий из видео."""

    def __init__(self, page, stream_id: int):
        self.page = page
        self.stream_id = stream_id

    @property
    def card(self):
        return self.page.locator(f"[data-stream='{self.stream_id}']")

    def row(self, offer_id: int):
        return self.card.locator(f"tr[data-offer='{offer_id}']")

    def _settle(self):
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(150)

    def state(self) -> dict[int, str]:
        """{offer_id: "34%" | "0% removed" | "25% pin"}"""
        result = {}
        for i in range(self.card.locator("tr[data-offer]").count()):
            row = self.card.locator("tr[data-offer]").nth(i)
            text = row.locator(".share-link").inner_text()
            if "removed" in (row.get_attribute("class") or ""):
                text += " removed"
            if row.locator(".pin.on").count():
                text += " pin"
            result[int(row.get_attribute("data-offer"))] = text
        return result

    @property
    def dirty(self) -> bool:
        return "dirty" in (self.card.get_attribute("class") or "")

    def add(self, offer_id: int):
        field = self.card.locator(".add-offer")
        field.click()
        field.type(str(offer_id))
        self.card.locator(".ac-list li", has_text=f"[{offer_id}]").click()
        self.card.locator(".add-btn").click()
        self._settle()

    def click(self, selector: str, offer_id: int | None = None):
        (self.row(offer_id) if offer_id else self.card).locator(selector).click()
        self._settle()

    def set_share(self, offer_id: int, value: int):
        self.row(offer_id).locator(".share-link").click()
        self.row(offer_id).locator("input").fill(str(value))
        self.row(offer_id).locator("input").press("Enter")
        self._settle()


def test_create_campaign(page):
    page.fill("input[name=name]", "ui camp")
    page.fill("input[name=geo]", "au, ro")
    page.click("#create-offer")
    page.type("#create-offer", "keto")
    page.locator("#tab-create .ac-list li", has_text="[3901]").click()
    page.click("button[type=submit]")
    result = page.locator(".result")
    result.wait_for()
    assert "создана" in result.inner_text() and "AU, RO" in result.inner_text()
    page.click(".result [data-open]")
    page.locator(".stream").first.wait_for()
    assert page.locator(".stream").count() == 2
    assert "#edit/" in page.url


def test_editor_scenario_from_video(page):
    page.click("[data-tab=edit]")
    page.click("#kt-search")
    page.type("#kt-search", "campaign 2")
    page.locator("#tab-edit .ac-list li", has_text="#7").click()
    editor = EditorPage(page, 12)
    editor.card.wait_for()
    assert editor.state() == {3749: "50%", 3717: "50%"} and not editor.dirty
    assert "Поток без офферов" in page.locator(".stream").first.inner_text()

    editor.add(3900)  # черновик: поток жёлтый, переживает перезагрузку
    assert editor.state() == {3749: "34%", 3717: "33%", 3900: "33%"} and editor.dirty
    page.reload()
    editor.card.wait_for()
    assert editor.dirty

    editor.click(".cancel")
    assert editor.state() == {3749: "50%", 3717: "50%"} and not editor.dirty

    editor.add(3900)
    editor.add(3901)
    editor.click(".push")
    assert set(editor.state().values()) == {"25%"} and not editor.dirty

    editor.click(".pin", 3717)
    editor.click(".remove", 3749)
    editor.click(".remove", 3900)
    assert editor.state() == {3717: "25% pin", 3901: "75%", 3749: "0% removed", 3900: "0% removed"}
    editor.click(".push")

    editor.click(".bring-back", 3749)
    assert editor.state() == {3749: "38%", 3717: "25% pin", 3901: "37%", 3900: "0% removed"}
    assert "возвращён" in editor.row(3749).inner_text()
    editor.click(".push")

    editor.set_share(3901, 50)
    assert editor.state() == {3749: "25%", 3717: "25% pin", 3901: "50% pin", 3900: "0% removed"}
    editor.click(".push")
    assert "опубликовано в Keitaro" in page.locator(".history").inner_text()
