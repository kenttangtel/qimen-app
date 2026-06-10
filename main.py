from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from models.db import init_db
from routers import auth, divination, history, payment

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/manifest.json")
async def get_manifest():
    return FileResponse("manifest.json")


@app.get("/sw.js")
async def get_sw():
    return FileResponse("sw.js", media_type="application/javascript")


app.include_router(divination.router)
app.include_router(auth.router)
app.include_router(history.router)
app.include_router(payment.router)