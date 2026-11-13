# Keitaro wrapper

Обёртка над [Keitaro](https://keitaro.io) Admin API: **создаватор кампаний** и **редактор офферов** в потоках.

Стек: FastAPI, SQLAlchemy 2.0 (async), Alembic, httpx; фронт — один HTML + vanilla JS без сборки.

## Что умеет

### 1. Создаватор кампаний
Форма: название, гео (`MX, AU, RO` — одна или несколько стран), оффер (поиск с автокомплитом по ID/названию),
плюс домен, группа и источник (списки подгружаются из API, значения по умолчанию — из `.env`).

Создаёт в Keitaro кампанию (`type=position`, CPC) с двумя потоками:

| # | Поток | Что делает |
|---|-------|-----------|
| 1 | `AU,MX -> Google` | фильтр `country = accept [AU, MX]`, `schema=redirect`, редирект на `https://google.com` |
| 2 | `Offers` | без фильтров, `schema=landings` без лендингов → сразу на выбранный оффер (доля 100%) |

Если создание потоков упало, кампания удаляется, чтобы в трекере не оставались полусобранные кампании.
Созданная кампания сразу загружается в обёртку и открывается в редакторе.

### 2. Редактор кампании (повторяет логику из видео)
Обёртка хранит у себя зеркало кампании: потоки и привязки офферов (`campaigns`, `streams`, `stream_offers`).

- **Fetch streams from KT** — загрузить/обновить кампанию из Keitaro. Любую кампанию трекера можно подтянуть поиском.
  Потоки без офферов показываются просто как поток — их фильтры и редиректы не разбираем.
  Офферы, которые обёртка знала, но которых больше нет в Keitaro (удалили руками в трекере), не пропадают,
  а уходят в архив — серые, со статусом *removed* и кнопкой **Bring back**.
- **Add** (поиск оффера с автокомплитом по API Keitaro) → доли пересчитываются, поток становится **жёлтым** —
  это черновик: он хранится в БД и переживает перезагрузку страницы, а в Keitaro пока ничего не меняется.
- **Push to KT** — публикует черновик потока в Keitaro. **Cancel** — откатывает черновик к опубликованному
  состоянию: добавленные до публикации офферы удаляются, поток снова белый.
- **Remove** → оффер серый, доля 0%, поток жёлтый. После Push оффер пропадает из Keitaro, но остаётся у нас в архиве.
  **Bring back** возвращает его (тоже через черновик).
- **Пересчёт долей**: при каждом добавлении/удалении/возврате активные офферы делят 100% поровну
  (целые, сумма всегда 100: 3 → 34/33/33).
- **📌 Пин**: закреплённая доля не меняется при пересчётах, остальные делят остаток
  (пример из видео: 25% закреплено + два оффера → 38/37). Клик по доле позволяет ввести её вручную —
  оффер при этом закрепляется. Если закреплены все активные офферы и в сумме не 100%, операция отклоняется с подсказкой.
- Push не даст опубликовать поток без активных офферов или с суммой долей ≠ 100%.
- **Статистика** (`/report/build`) за выбранный период: клики, уники, боты, конверсии, CR, доход по офферам и по потоку.
  У архивных офферов клики тоже показываются, поэтому «Итого» сходится с цифрами потока.
- **История публикаций**: каждый Push/Cancel пишется в `push_log` (было → стало).

## Запуск

### Docker (проще всего)
```bash
cp .env.example .env        # вписать KEITARO_URL и KEITARO_API_KEY
docker compose up --build   # миграции применяются автоматически при старте
```
Открыть http://localhost:8000 (Swagger — http://localhost:8000/docs).

### Локально (Python 3.11+)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # для разработки и тестов: requirements-dev.txt
cp .env.example .env        # вписать KEITARO_URL и KEITARO_API_KEY
alembic upgrade head        # миграции
uvicorn app.main:app --reload
```

### Демо без доступа к Keitaro
Если `KEITARO_URL` пустой или `KEITARO_MOCK=true`, приложение работает со встроенным in-memory
имитатором Keitaro API (`app/fake_keitaro.py`) с тестовыми офферами и одной кампанией. В шапке будет плашка «демо-режим».

## Настройки (`.env`)

| Переменная | Описание |
|---|---|
| `KEITARO_URL` | адрес трекера, например `https://tlgk.host` (`/admin_api/v1` добавится сам) |
| `KEITARO_API_KEY` | ключ из «Профиль → API ключи» |
| `KEITARO_MOCK` | `true` — фейковый Keitaro |
| `KEITARO_TIMEZONE` | таймзона для отчётов, по умолчанию `Europe/Moscow` |
| `DEFAULT_DOMAIN_ID`, `DEFAULT_GROUP_ID`, `DEFAULT_TRAFFIC_SOURCE_ID` | что выбрано в форме по умолчанию |
| `GEO_REDIRECT_URL` | куда редиректит первый поток, по умолчанию `https://google.com` |
| `DATABASE_URL` | по умолчанию SQLite `sqlite+aiosqlite:///./testorator.db`; для Postgres — `postgresql+asyncpg://...` (+ `pip install asyncpg`) |

Домен, группа и источник необязательны: если у пользователя API их нет (так на тестовом трекере — доменов и
источников там нет), кампания создаётся без них, а URL строится от хоста трекера: `https://<tracker>/<alias>`.

## Миграции
```bash
alembic upgrade head                                  # применить
alembic revision --autogenerate -m "описание"         # новая миграция после изменения app/models.py
alembic downgrade -1                                  # откатить последнюю
```

## Тесты и линтер
```bash
pip install -r requirements-dev.txt
pytest -q                     # домен + API (против фейкового Keitaro)
ruff check . && ruff format --check .

# e2e в браузере (сценарий из видео); без Playwright эти тесты пропускаются
playwright install chromium
pytest tests/e2e
```
- `tests/test_domain.py` — бизнес-правила на чистых объектах, без БД и HTTP: доли, пины, черновик, архив, синхронизация.
- `tests/test_api.py` — весь HTTP API против фейкового Keitaro: создание кампании (структура потоков, откат при ошибке),
  fetch, push/cancel, удаление оффера прямо в Keitaro, сценарий с пином из видео, статистика.
- `tests/e2e/test_ui.py` — тот же сценарий кликами в Chromium (Page Object), заодно ловит ошибки JS в консоли.

Тесты не читают локальный `.env` (`APP_ENV_FILE=""`), так что ваши настройки на них не влияют.

## API

| Метод | Путь | |
|---|---|---|
| GET | `/api/meta` | домены, группы, источники, значения по умолчанию |
| GET | `/api/offers?q=` | поиск офферов для автокомплита |
| POST | `/api/campaigns` | создать кампанию `{name, geo, offer_id, domain_id?, group_id?, traffic_source_id?}` |
| GET | `/api/campaigns` | кампании, загруженные в обёртку |
| GET | `/api/keitaro/campaigns?q=` | поиск кампаний в Keitaro |
| POST | `/api/campaigns/{id}/fetch` | Fetch streams from KT |
| GET | `/api/campaigns/{id}?date_from=&date_to=` | потоки, офферы, доли, черновики, статистика |
| GET | `/api/campaigns/{id}/history` | журнал публикаций |
| POST | `/api/streams/{sid}/offers` | добавить оффер в черновик `{offer_id}` |
| POST | `/api/streams/{sid}/offers/{offer_id}/remove` | удалить (в архив) |
| POST | `/api/streams/{sid}/offers/{offer_id}/bring-back` | вернуть из архива |
| POST | `/api/streams/{sid}/offers/{offer_id}/pin` | закрепить/открепить долю `{pinned}` |
| PUT | `/api/streams/{sid}/offers/{offer_id}/share` | задать долю вручную `{share}` (закрепляет) |
| POST | `/api/streams/{sid}/push` | опубликовать черновик в Keitaro |
| POST | `/api/streams/{sid}/cancel` | отменить черновик |

## Архитектура

```
app/
  domain/            бизнес-правила, без HTTP и Keitaro
    models.py        сущности Campaign / Stream / StreamOffer с поведением: add/remove/bring_back,
                     pin, rebalance, discard_draft, publishable_offers, sync_published
    shares.py        целочисленное деление 100% (34/33/33)
    geo.py           разбор гео-кодов
    errors.py        NotFound / Conflict / InvalidOperation — без HTTP-кодов
  keitaro/
    client.py        типизированный клиент Admin API (DTO KtCampaign, KtStream, KtOffer) —
                     единственное место, которое знает формат JSON Keitaro
    fake.py          in-memory имитация API для тестов и демо
  services/          сценарии (application layer): загрузить агрегат → вызвать метод → сохранить
    campaign_creator.py  создатор кампаний (+ откат при ошибке)
    campaign_sync.py     Fetch streams from KT
    stream_editor.py     черновик, push, cancel
    stats.py             отчёты Keitaro
  repositories.py    загрузка агрегатов из БД
  api/               HTTP: роуты, pydantic-схемы ответов, DI (Annotated-зависимости)
  main.py            create_app(): сборка приложения, маппинг доменных ошибок в HTTP-коды
  static/js/         фронт на ES-модулях: api (клиент бэкенда), ui (Autocomplete, Toast),
                     creator, editor, stream-card, main
alembic/             миграции
tests/               domain / api / e2e
```

Зависимости направлены внутрь: `api → services → domain`, `services → keitaro`. Домен ничего не знает ни про HTTP,
ни про Keitaro; поэтому все правила редактора проверяются юнит-тестами на обычных объектах.

Сознательные упрощения (YAGNI): сущности домена — это сразу ORM-модели (отдельный слой «чистых» классов с маппингом
здесь ничего бы не дал); у клиента Keitaro нет абстрактного интерфейса — подмена в тестах делается на уровне HTTP
фейковым приложением, а не моками.
