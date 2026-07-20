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
# 🟢 首席架構師優化版：全面解放跨域限制，專為行動端外殼打造
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 允許所有網域（徹底根治手機端 localhost 各種協議撞牆）
    allow_credentials=False,   # 關閉 Cookie 認證（我們用 Bearer Token，關閉後才可啟用 "*" 萬用字元）
    allow_methods=["*"],       # 允許所有請求方法 (POST, GET, OPTIONS 等)
    allow_headers=["*"],       # 允許所有請求標頭
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