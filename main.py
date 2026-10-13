import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from models.db import init_db, engine
from routers import auth, divination, history, payment, debug

logger = logging.getLogger("qimen_app")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle (replaces deprecated @app.on_event)."""
    try:
        init_db()
        logger.info("Database initialised.")
    except RuntimeError as exc:
        logger.exception("Startup failed due to runtime configuration error: %s", exc)
        raise
    except Exception:
        logger.exception("Database initialization failed on startup")
        raise
    yield


app = FastAPI(lifespan=lifespan)

# 🌟 跨域白名單：由 ALLOWED_ORIGINS 環境變數控制（逗號分隔）
# Capacitor 原生端（Android/iOS）的請求不帶 Origin 標頭，本就不受 CORS 限制，
# 因此無需使用 "*" 萬用字元。舊版全開設定會讓任何網站都能呼叫本 API。
_DEFAULT_ORIGINS = (
    "http://localhost:8000,http://127.0.0.1:8000,"
    "https://kenttangtel-qimen-api.hf.space"
)
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # 明確白名單，不再使用 "*"
    allow_credentials=False,         # 使用 Bearer Token，不需要 Cookie
    allow_methods=["*"],             # 允許所有請求方法 (POST, GET, OPTIONS 等)
    allow_headers=["*"],             # 允許所有請求標頭
)


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception in ASGI request")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


BASE_DIR = os.path.dirname(__file__)
WWW_DIR = os.path.join(BASE_DIR, "www")
app.mount("/static", StaticFiles(directory=WWW_DIR), name="static")


@app.get("/health")
async def health_check():
    """輕量健康檢查：確認服務存活，並探測資料庫連線。"""
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: database probe failed")
        db_ok = False

    payload = {"status": "ok" if db_ok else "degraded", "database": db_ok}
    return JSONResponse(status_code=200 if db_ok else 503, content=payload)


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(WWW_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/manifest.json")
async def get_manifest():
    manifest_path = os.path.join(WWW_DIR, "manifest.json")
    return FileResponse(manifest_path)


@app.get("/sw.js")
async def get_sw():
    sw_path = os.path.join(WWW_DIR, "sw.js")
    return FileResponse(sw_path, media_type="application/javascript")


app.include_router(divination.router)
app.include_router(auth.router)
app.include_router(history.router)
app.include_router(payment.router)
app.include_router(debug.router)
