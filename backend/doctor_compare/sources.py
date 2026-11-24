import asyncio
import re
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field

from .config import Settings
from .models import Doctor

BASE_URL = "https://interview.psyonclinic.ru"
MEDICAL_URL = f"{BASE_URL}/api/v1/specialists"
CATALOG_URL = f"{BASE_URL}/doctors"
MEDICAL_LIMIT = 200
MEDICAL_PAGE_SIZE = 100
CATALOG_PAGE_LIMIT = 3


class SourceError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class MedicalDoctor(BaseModel):
    id: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    middle_name: str | None = None
    specialty: str | None = None
    experience_years: int | None = Field(default=None, ge=0)

    def to_doctor(self) -> Doctor:
        name = " ".join(
            part.strip()
            for part in (self.last_name, self.first_name, self.middle_name)
            if part and part.strip()
        )
        return Doctor(
            id=self.id, name=name, specialty=self.specialty, experience=self.experience_years,
            first_name=self.first_name, last_name=self.last_name,
        )


class MedicalPage(BaseModel):
    current_page: int = Field(ge=1)
    last_page: int = Field(ge=1)
    total: int = Field(ge=0)
    data: list[MedicalDoctor]


async def get_page(
    client: httpx.AsyncClient,
    url: str,
    page: int,
    source: str,
    headers: dict[str, str] | None = None,
    per_page: int | None = None,
) -> httpx.Response:
    try:
        params = {"page": page}
        if per_page is not None:
            params["per_page"] = per_page
        for attempt in range(3):
            try:
                response = await client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
            else:
                if attempt == 2 or response.status_code not in (500, 502, 503, 504):
                    break
            await asyncio.sleep(0.25)
        response.raise_for_status()
    except httpx.TimeoutException:
        raise SourceError(f"{source} не ответил вовремя (страница {page}).", 504) from None
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if source == "Medical API" and status in (401, 403):
            message = "Medical API отклонил ключ. Проверьте MEDICAL_API_KEY на сервере."
        elif status == 429:
            message = f"{source} ограничил число запросов. Повторите чуть позже."
        else:
            message = f"{source} вернул HTTP {status} (страница {page})."
        raise SourceError(message) from None
    except httpx.RequestError:
        raise SourceError(f"Не удалось подключиться к {source} (страница {page}).") from None
    return response


async def load_medical(client: httpx.AsyncClient, settings: Settings) -> tuple[list[Doctor], int]:
    key = settings.medical_api_key.get_secret_value().strip()
    if not key:
        raise SourceError("Укажите MEDICAL_API_KEY в окружении сервера.", 503)

    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    records: dict[str, Doctor] = {}
    for page in range(1, MEDICAL_LIMIT + 1):
        response = await get_page(
            client, MEDICAL_URL, page, "Medical API", headers, per_page=MEDICAL_PAGE_SIZE
        )
        try:
            data = MedicalPage.model_validate(response.json())
        except ValueError:
            raise SourceError(f"Не удалось прочитать ответ Medical API (страница {page}).") from None

        if data.current_page != page or (not data.data and (page < data.last_page or data.total)):
            raise SourceError(f"Medical API вернул некорректную пагинацию (страница {page}).")
        for item in data.data:
            records[item.id] = item.to_doctor()
            if len(records) == MEDICAL_LIMIT:
                return list(records.values()), data.total
        if page >= data.last_page:
            return list(records.values()), data.total
    raise SourceError("Medical API не завершил пагинацию.")


def text_at(card: Tag, selector: str) -> str | None:
    tag = card.select_one(selector)
    return (tag.get_text(" ", strip=True) or None) if tag else None


def catalog_page_number(link: Tag) -> int | None:
    query = urlsplit(str(link["href"])).query
    value = parse_qs(query).get("page", [""])[0]
    if value.isascii() and value.isdecimal() and len(value) <= 4:
        return int(value)
    return None


def parse_catalog(html: str, page: int) -> tuple[list[Doctor], bool]:
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for card in soup.select("article.doctor-card"):
        link = card.select_one("h3 a[href]")
        name = text_at(card, "h3 a")
        if not link or not name:
            raise SourceError(f"В Doctor Catalog нет ФИО в карточке (страница {page}).")
        experience_text = text_at(card, "p.text-slate-500") or ""
        years = re.search(r"\bстаж\s*:?\s*(\d+)", experience_text, re.IGNORECASE)
        price = next(
            (tag.get_text(" ", strip=True) for tag in card.select("strong") if "₽" in tag.get_text()),
            None,
        )
        records.append(
            Doctor(
                id=urlsplit(str(link["href"])).path,
                name=name,
                specialty=text_at(card, "p.text-teal-700"),
                experience=int(years[1]) if years else None,
                clinic=text_at(card, "p.truncate"),
                price=price,
            )
        )
    main = soup.select_one("main")
    empty = main is not None and re.search(r"Найдено:\s*0\b", main.get_text(" ", strip=True))
    if not records and not (page == 1 and empty):
        raise SourceError(f"В HTML Doctor Catalog не найдены карточки (страница {page}).")

    next_link = soup.select_one('a[rel="next"][href]')
    if next_link is not None and catalog_page_number(next_link) != page + 1:
        raise SourceError(f"Некорректная пагинация Doctor Catalog (страница {page}).")
    return records, next_link is not None


async def load_catalog(client: httpx.AsyncClient) -> tuple[list[Doctor], int]:
    records: dict[str, Doctor] = {}
    for page in range(1, CATALOG_PAGE_LIMIT + 1):
        response = await get_page(client, CATALOG_URL, page, "Doctor Catalog")
        items, has_next = parse_catalog(response.text, page)
        # Одинаковая карточка может встретиться на соседних страницах.
        records.update((item.id, item) for item in items)
        if not has_next:
            return list(records.values()), page
    return list(records.values()), CATALOG_PAGE_LIMIT
