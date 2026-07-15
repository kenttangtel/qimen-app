import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import logging

from models.db import init_db
from routers import auth, divination, history, payment, debug

app = FastAPI()

# 🌟 新增跨域白名單，徹底打通網頁端與手機 iOS / Android 原生端
origins = [
    "https://qimen-app-xwie.onrender.com",  # 您的 Render 前端網頁
    "http://localhost",                    # Android 原生域名 & 本地調試
    "http://localhost:5173",               # Vite 本地預設
    "http://localhost:3000",               # 其它前端本地預設
    "capacitor://localhost",               # iOS 原生網域 (App Store 上架必備)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # global logger (下面原本的第 16 行保持不變...)

logger = logging.getLogger("qimen_app")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled exception in ASGI request")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

BASE_DIR = os.path.dirname(__file__)
WWW_DIR = os.path.join(BASE_DIR, "www")
app.mount("/static", StaticFiles(directory=WWW_DIR), name="static")


@app.on_event("startup")
def on_startup():
    try:
        init_db()
    except RuntimeError as exc:
        logger.exception("Startup failed due to runtime configuration error: %s", exc)
        raise
    except Exception:
        logger.exception("Database initialization failed on startup")
        raise


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