import contextlib
import logging
from fastapi import FastAPI, Header, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.routes_backtest import router as backtest_router
from app.api.routes_news import router as news_router
from app.api.routes_plan import router as plan_router
from app.api.routes_portfolio import router as portfolio_router
from app.api.routes_positions import router as positions_router
from app.api.routes_system import router as system_router
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


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verifies bearer token if configured, allowing easy local UI development."""
    if settings.env == "production" and settings.app_token != "demo-token-change-in-prod":
        if not credentials or credentials.credentials != settings.app_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API Bearer token")
    return True


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Swing Trading Intelligence Platform Backend...")
    init_db()
    # Cache instruments asynchronously/on boot if available
    try:
        provider_manager.angelone._load_cached_instruments()
        if not provider_manager.angelone.instrument_map:
            logger.info("Angel One scrip master is empty; fetching latest official instrument list...")
            provider_manager.angelone.refresh_instruments()
    except Exception as e:
        logger.warning(f"Initial instrument cache loading warning: {e}")
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API Routers under /api
app.include_router(system_router, prefix="/api", tags=["System & Settings"])
app.include_router(plan_router, prefix="/api", tags=["Trade Plan & Signals"])
app.include_router(watchlists_router, prefix="/api", tags=["Watchlists"])
app.include_router(positions_router, prefix="/api", tags=["Positions & Journal"])
app.include_router(portfolio_router, prefix="/api", tags=["Zerodha Portfolio & Valuation"])
app.include_router(news_router, prefix="/api", tags=["News Intelligence"])
app.include_router(backtest_router, prefix="/api", tags=["Backtesting & Research"])


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"app": "Swing Trading Intelligence Platform", "status": "Running"}
else:
    @app.get("/")
    def root():
        return {
            "app": "Swing Trading Intelligence Platform",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
            "disclaimer": "Signals are rules-based, not advice. Past/backtested performance does not guarantee future results.",
        }
