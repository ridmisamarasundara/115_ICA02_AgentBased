from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401  (registers all tables on Base)
from app.agents.registry import setup_agents
from app.agents.scheduler import start_scheduler, stop_scheduler
from app.config import APP_ENV, SECRET_KEY, SEED_DEMO
from app.database import Base, SessionLocal, engine
from app.deps import LoginRequired
from app.routes import account, admin, auth, bookings, events, hire, staff
from app.templating import templates

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="EventSphere")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax",
                   https_only=(APP_ENV == "production"), max_age=60 * 60 * 8)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

for module in (events, bookings, hire, auth, account, admin, staff):
    app.include_router(module.router)


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(f"/login?next={quote(exc.next_url)}", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request, "error.html", {"status": exc.status_code, "detail": exc.detail},
                                      status_code=exc.status_code)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    setup_agents()
    if SEED_DEMO:
        from app.seed import seed_demo
        with SessionLocal() as db:
            seed_demo(db)
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/health")
def health():
    return {"status": "ok"}
