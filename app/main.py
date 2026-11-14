from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import SECRET_KEY
from app.agents.registry import setup_agents
from app.agents.scheduler import start_scheduler, stop_scheduler
from app.database import Base, engine
import app.models  # noqa: F401  (registers all tables on Base)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="EventSphere")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    setup_agents()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/health")
def health():
    return {"status": "ok"}
