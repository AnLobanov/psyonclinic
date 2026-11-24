import asyncio

import httpx
import pytest

from doctor_compare.config import Settings
from doctor_compare.sources import SourceError, load_catalog, load_medical


def catalog_html(page, next_page=None):
    next_link = f'<a rel="next" href="/doctors?page={next_page}">Далее</a>' if next_page else ""
    return f"""
    <article class="doctor-card"><div class="p-5">
      <h3><a href="/doctors/ivanov-{page}">Иванов Иван Иванович</a></h3>
      <p class="text-teal-700">Терапевт</p>
      <p class="text-slate-500">Стаж 12 лет</p>
      <div><strong>4,5</strong></div>
      <p class="truncate">Клиника А</p>
      <div><strong>от 2 550 ₽</strong></div>
    </div></article>
    {next_link}
    """


def test_medical_pagination_stops_at_200_and_sends_bearer():
    pages = []

    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json={
            "current_page": page, "last_page": 12, "total": 300, "data": [
                {"id": str(page * 25 + i), "first_name": "Иван", "last_name": "Иванов",
                 "middle_name": "Иванович", "specialty": "Терапевт", "experience_years": 0}
                for i in range(25)
            ],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await load_medical(client, Settings(medical_api_key="test-key"))

    records, total = asyncio.run(run())
    assert pages == list(range(1, 9))
    assert len(records) == 200 and total == 300
    assert records[0].name == "Иванов Иван Иванович"
    assert records[0].experience == 0
    assert (records[0].first_name, records[0].last_name) == ("Иван", "Иванов")
    assert {"first_name", "last_name"}.isdisjoint(records[0].model_dump())


def test_catalog_follows_html_pages_and_keeps_public_price():
    def respond(request):
        assert "Authorization" not in request.headers
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, text=catalog_html(page, page + 1 if page < 3 else None))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await load_catalog(client)

    records, pages = asyncio.run(run())
    assert pages == len(records) == 3
    assert records[-1].experience == 12
    assert records[-1].clinic == "Клиника А"
    assert records[-1].price == "от 2 550 ₽"


def test_catalog_stops_at_three_pages_even_when_more_are_available():
    async def run():
        def respond(request):
            page = int(request.url.params["page"])
            assert page <= 3
            return httpx.Response(200, text=catalog_html(page, page + 1))

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await load_catalog(client)

    records, pages = asyncio.run(run())
    assert pages == len(records) == 3


def test_catalog_broken_markup_is_an_error():
    async def run():
        transport = httpx.MockTransport(lambda _: httpx.Response(200, text="<h1>Ошибка</h1>"))
        async with httpx.AsyncClient(transport=transport) as client:
            await load_catalog(client)

    with pytest.raises(SourceError, match="Doctor Catalog"):
        asyncio.run(run())
