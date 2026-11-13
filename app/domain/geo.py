import re

from app.domain.errors import InvalidOperation

_CODE = re.compile(r"^[A-Z]{2}$")
_SEPARATORS = re.compile(r"[\s,;]+")


def parse_countries(raw: str | list[str]) -> list[str]:
    """«mx, AU;ro» -> ["MX", "AU", "RO"]: ISO-коды из двух букв, без дублей, порядок сохраняется."""
    items = raw if isinstance(raw, list) else _SEPARATORS.split(raw)
    countries: list[str] = []
    for item in filter(None, (i.strip() for i in items)):
        code = item.upper()
        if not _CODE.match(code):
            raise InvalidOperation(f"Некорректный гео-код: «{item}». Нужен ISO-код из 2 букв, например AU")
        if code not in countries:
            countries.append(code)
    if not countries:
        raise InvalidOperation("Укажите хотя бы один гео-код страны")
    return countries
