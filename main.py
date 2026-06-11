import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from models.db import init_db
from routers import auth, divination, history, payment

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(__file__)
WWW_DIR = os.path.join(BASE_DIR, "www")
app.mount("/static", StaticFiles(directory=WWW_DIR), name="static")


@app.on_event("startup")
def on_startup():
    init_db()


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