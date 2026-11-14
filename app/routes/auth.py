from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_user, flash, login_user, safe_next
from app.models import User
from app.schemas import RegisterForm
from app.security import hash_password, verify_csrf, verify_password
from app.templating import templates

router = APIRouter()
HOME_BY_ROLE = {"admin": "/admin", "staff": "/staff/scan", "attendee": "/"}


@router.get("/register")
def register_page(request: Request, user=Depends(current_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"errors": [], "form": {}})


@router.post("/register", dependencies=[Depends(verify_csrf)])
def register(request: Request, name: str = Form(""), email: str = Form(""), password: str = Form(""),
             confirm: str = Form(""), db: Session = Depends(get_db)):
    form = {"name": name, "email": email}
    try:
        data = RegisterForm(name=name, email=email, password=password, confirm=confirm)
    except ValidationError as exc:
        errors = [e["msg"].replace("Value error, ", "") for e in exc.errors()]
        return templates.TemplateResponse(request, "register.html", {"errors": errors, "form": form}, status_code=400)
    if db.query(User).filter(User.email == data.email).first():
        return templates.TemplateResponse(request, "register.html",
                                          {"errors": ["An account with this email already exists"], "form": form},
                                          status_code=400)
    # The role is never taken from the form: every self-registered user is an attendee.
    user = User(name=data.name, email=data.email, password_hash=hash_password(data.password), role="attendee")
    db.add(user)
    db.commit()
    login_user(request, user)
    flash(request, "Welcome to EventSphere! Your account has been created.", "success")
    return RedirectResponse("/", status_code=303)


@router.get("/login")
def login_page(request: Request, next: str = "", user=Depends(current_user)):
    if user:
        return RedirectResponse(HOME_BY_ROLE.get(user.role, "/"), status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": safe_next(next) or ""})


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form(""),
          db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html",
                                          {"error": "Invalid email or password", "next": safe_next(next) or ""},
                                          status_code=400)
    login_user(request, user)
    return RedirectResponse(safe_next(next) or HOME_BY_ROLE.get(user.role, "/"), status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
