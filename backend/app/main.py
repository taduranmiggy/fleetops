from pathlib import Path
import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import (
    admin,
    admin_analytics,
    analytics_predict,
    analytics_prescribe,
    auth,
    bookings,
    clerk_auth,
    completion,
    customer,
    customer_route_estimate,
    customer_sites,
    dispatch,
    driver,
    feedback,
    geo_places,
    helper_ops,
    manager,
    payments,
    ratings,
    reports,
    schedule,
    toll_matrix,
    toll_plazas,
    workflow,
)
from app.core.config import settings
from app.core.paths import uploads_root
from app.db import apply_runtime_schema_fixes, get_db
from app.services.route_estimate import PreciseDistanceUnavailable

logging.basicConfig(
    level=logging.INFO if settings.app_env.strip().lower() == "production" else logging.DEBUG,
    format="ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
)
logger = logging.getLogger(__name__)


def require_db(db=Depends(get_db)) -> None:
    db.execute(text("SELECT 1"))


app = FastAPI(title=settings.app_name)


@app.exception_handler(PreciseDistanceUnavailable)
async def precise_distance_unavailable_handler(request: Request, exc: PreciseDistanceUnavailable) -> JSONResponse:
    logger.warning(
        "PreciseDistanceUnavailable path=%s method=%s detail=%s",
        request.url.path,
        request.method,
        exc.detail,
    )
    return JSONResponse(status_code=400, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error path=%s method=%s", request.url.path, request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/", methods=["GET", "HEAD"])
def root() -> dict:
    """Small public landing route for deployment and path verification."""
    return {
        "name": settings.app_name,
        "status": "ok",
        "health": "/health",
        "readiness": "/ready",
        "docs": "/docs",
        "api_prefix": "/api",
    }


@app.on_event("startup")
def startup() -> None:
    uploads_root()
    apply_runtime_schema_fixes()
    try:
        from app.db import SessionLocal
        from app.services.toll_plaza_seed import ensure_toll_reference_data

        db = SessionLocal()
        try:
            ensure_toll_reference_data(db)
        finally:
            db.close()
    except Exception:
        logging.getLogger(__name__).exception("Failed to seed toll plaza / matrix reference data")


@app.api_route("/health", methods=["GET", "HEAD"])
def health() -> dict:
    """Liveness only — does not open a DB session (so dev proxies can detect uvicorn is up).

    HEAD is allowed so `wait-on` and other probes that use HEAD succeed (GET-only routes return 405).
    """
    return {"status": "ok"}


@app.api_route("/ready", methods=["GET", "HEAD"])
def ready(db=Depends(get_db)) -> dict:
    """Readiness probe — confirms DB connectivity."""
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


SENSITIVE_UPLOAD_PREFIXES = (
    "payment_proofs/",
    "booking_documents/",
    "delivery_receiving/",
)


@app.api_route("/uploads/{file_path:path}", methods=["GET", "HEAD"])
def serve_upload(file_path: str):
    normalized = str(Path(file_path).as_posix()).lstrip("/")
    if not normalized:
        raise HTTPException(status_code=404, detail="File not found")
    lowered = normalized.lower()
    if lowered.startswith(SENSITIVE_UPLOAD_PREFIXES):
        raise HTTPException(
            status_code=403,
            detail="Sensitive files must be accessed through authenticated endpoints.",
        )

    base = uploads_root().resolve()
    target = (base / normalized).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


_api_deps = [Depends(require_db)]

# Core
app.include_router(auth.router, prefix="/api", dependencies=_api_deps)
app.include_router(bookings.router, prefix="/api", dependencies=_api_deps)
app.include_router(customer.router, prefix="/api", dependencies=_api_deps)
app.include_router(dispatch.router, prefix="/api", dependencies=_api_deps)
app.include_router(driver.router, prefix="/api", dependencies=_api_deps)
app.include_router(helper_ops.router, prefix="/api", dependencies=_api_deps)
app.include_router(geo_places.router, prefix="/api", dependencies=_api_deps)
app.include_router(manager.router, prefix="/api", dependencies=_api_deps)
app.include_router(admin.router, prefix="/api", dependencies=_api_deps)
app.include_router(toll_matrix.router, prefix="/api", dependencies=_api_deps)
app.include_router(toll_plazas.router, prefix="/api", dependencies=_api_deps)
app.include_router(toll_plazas.public_router, prefix="/api", dependencies=_api_deps)
app.include_router(admin_analytics.router, prefix="/api", dependencies=_api_deps)
app.include_router(ratings.router, prefix="/api", dependencies=_api_deps)
app.include_router(reports.router, prefix="/api", dependencies=_api_deps)
app.include_router(clerk_auth.router, prefix="/api", dependencies=_api_deps)
app.include_router(workflow.router, prefix="/api", dependencies=_api_deps)

# Paper §3.2 / §3.5 additions
app.include_router(payments.router, prefix="/api", dependencies=_api_deps)
app.include_router(feedback.router, prefix="/api", dependencies=_api_deps)
app.include_router(completion.router, prefix="/api", dependencies=_api_deps)
app.include_router(customer_sites.router, prefix="/api", dependencies=_api_deps)
app.include_router(customer_route_estimate.router, prefix="/api", dependencies=_api_deps)
app.include_router(schedule.router, prefix="/api", dependencies=_api_deps)
app.include_router(analytics_predict.router, prefix="/api", dependencies=_api_deps)
app.include_router(analytics_prescribe.router, prefix="/api", dependencies=_api_deps)

