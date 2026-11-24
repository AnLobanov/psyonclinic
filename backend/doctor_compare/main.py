import asyncio
from contextlib import asynccontextmanager
from time import monotonic

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, Settings
from .matching import compare
from .models import Report
from .sources import SourceError, load_catalog, load_medical

CACHE_SECONDS = 60


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    report: Report | None = None
    updated_at = 0.0
    lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(timeout=8) as client:
            app.state.http = client
            yield

    app = FastAPI(title="Сверка врачей", lifespan=lifespan, docs_url="/api/docs")

    @app.exception_handler(SourceError)
    async def source_error(_request: Request, error: SourceError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(error)}, status_code=error.status, headers={"Cache-Control": "no-store"}
        )

    async def get_report(client: httpx.AsyncClient, refresh: bool) -> Report:
        nonlocal report, updated_at
        if not config.medical_api_key.get_secret_value().strip():
            raise SourceError("Укажите MEDICAL_API_KEY в окружении сервера.", 503)

        previous = report
        async with lock:
            if report is not None and (
                report is not previous or (not refresh and monotonic() - updated_at < CACHE_SECONDS)
            ):
                return report

            medical_task = asyncio.create_task(load_medical(client, config))
            catalog_task = asyncio.create_task(load_catalog(client))
            try:
                async with asyncio.timeout(55):
                    (medical, total), (catalog, pages) = await asyncio.gather(
                        medical_task, catalog_task
                    )
            except TimeoutError:
                raise SourceError("Источники не ответили вовремя. Повторите обновление.", 504) from None
            finally:
                for task in (medical_task, catalog_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(medical_task, catalog_task, return_exceptions=True)

            report = Report(
                medical_count=len(medical), medical_total=total,
                catalog_count=len(catalog), catalog_pages=pages,
                rows=compare(medical, catalog),
            )
            updated_at = monotonic()
            return report

    @app.get("/api/comparison", response_model=Report)
    async def comparison(request: Request, response: Response) -> Report:
        response.headers["Cache-Control"] = "no-store"
        return await get_report(request.app.state.http, refresh=False)

    dist = PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
