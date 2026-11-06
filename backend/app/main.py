import contextlib
import logging
from fastapi import Depends, FastAPI, Header, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.routes_backtest import router as backtest_router
from app.api.routes_data import router as data_router
from app.api.routes_news import router as news_router
from app.api.routes_plan import router as plan_router
from app.api.routes_portfolio import router as portfolio_router
from app.api.routes_positions import router as positions_router
from app.api.routes_system import router as system_router
from app.api.routes_universe import router as universe_router
from app.api.routes_watchlists import router as watchlists_router
from app.db import init_db
from app.providers.manager import provider_manager
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("swing_algo")

security = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """Require the configured bearer token on every non-health API route in production."""
    if settings.env.strip().lower() == "production":
        if not credentials or credentials.credentials != settings.app_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API Bearer token")
    return True


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Swing Trading Intelligence Platform Backend...")
    init_db()
    # Cache instruments in non-blocking background thread on boot so Uvicorn starts immediately
    import threading
    def _async_load_instruments():
        try:
            provider_manager.angelone._load_cached_instruments()
            if not provider_manager.angelone.instrument_map:
                logger.info("Angel One scrip master is empty; fetching latest official instrument list in background...")
                provider_manager.angelone.refresh_instruments()
        except Exception as e:
            logger.warning(f"Initial instrument cache loading warning: {e}")

    threading.Thread(target=_async_load_instruments, daemon=True, name="instrument_loader").start()

    # Start scheduler
    start_scheduler()
    yield
    # Shutdown
    logger.info("Shutting down background scheduler...")
    stop_scheduler()


app = FastAPI(
    title="Swing Trading Intelligence Platform",
    version="1.0.0",
    description="End-of-day positional swing-trading signal platform for Indian (NSE) and US equities.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
origins = [
    "https://algo-trading-xi-opal.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API Routers under /api
protected_api = [Depends(verify_token)]
app.include_router(system_router, prefix="/api", tags=["System & Settings"], dependencies=protected_api)
app.include_router(plan_router, prefix="/api", tags=["Trade Plan & Signals"], dependencies=protected_api)
app.include_router(watchlists_router, prefix="/api", tags=["Watchlists"], dependencies=protected_api)
app.include_router(positions_router, prefix="/api", tags=["Positions & Journal"], dependencies=protected_api)
app.include_router(portfolio_router, prefix="/api", tags=["Zerodha Portfolio & Valuation"], dependencies=protected_api)
app.include_router(news_router, prefix="/api", tags=["News Intelligence"], dependencies=protected_api)
app.include_router(backtest_router, prefix="/api", tags=["Backtesting & Research"], dependencies=protected_api)
app.include_router(data_router, prefix="/api", tags=["Historical Data & Ingestion"], dependencies=protected_api)
app.include_router(universe_router, prefix="/api", tags=["Universe & Coverage"], dependencies=protected_api)


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# High-priority, zero-latency health and liveness endpoints for Render/orchestration probes
@app.api_route("/", methods=["GET", "HEAD", "OPTIONS"], tags=["Health"])
def root():
    return {
        "status": "HEALTHY",
        "service": "algo-trading-backend",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
        "disclaimer": "Signals are rules-based, not advice. Past/backtested performance does not guarantee future results.",
    }


@app.api_route("/health", methods=["GET", "HEAD", "OPTIONS"], tags=["Health"])
@app.api_route("/healthz", methods=["GET", "HEAD", "OPTIONS"], tags=["Health"])
@app.api_route("/ping", methods=["GET", "HEAD", "OPTIONS"], tags=["Health"])
def liveness():
    return {"status": "HEALTHY", "service": "algo-trading-backend"}


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if any(full_path.startswith(p) for p in ("api", "docs", "redoc", "openapi.json", "health", "healthz", "ping")):
            raise HTTPException(status_code=404, detail="Not Found")
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"app": "Swing Trading Intelligence Platform", "status": "Running"}
