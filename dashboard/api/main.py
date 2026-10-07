"""Dashboard API: FastAPI app serving /api/* (password-gated) and the Vite build as static files.

Run locally: uvicorn dashboard.api.main:app --port 8080   (from the repo root)
Env: DASHBOARD_PASSWORD, MAPS_BROWSER_KEY (both Secret Manager secrets on Cloud Run).
"""
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth
from .routers import places, sites, traffic, weather

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

app = FastAPI(title="Pertamina SPBU traffic dashboard", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)  # POST /api/login: open

# Every router below is gated: 401 without a valid session cookie. Later beads add one line each here
# (`api.include_router(<module>.router)`) plus the import above. Router paths carry no /api prefix.
api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])
api.include_router(sites.router)
api.include_router(traffic.router)
api.include_router(weather.router)
api.include_router(places.router)
app.include_router(api)


@app.get("/health")
def health():
    return {"status": "ok"}


# Static files. /assets are the hashed Vite bundles; any other unknown GET (not /api) gets the SPA shell so
# client-side routes such as /site/24.351.97 survive a reload. Hooked on 404, so route order does not matter.
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request: Request, exc: StarletteHTTPException):
    path = request.url.path
    if exc.status_code == 404 and request.method == "GET" and not path.startswith("/api") \
            and not path.startswith("/assets/") and (DIST / "index.html").is_file():
        candidate = (DIST / path.lstrip("/")).resolve()
        if candidate.is_file() and DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
