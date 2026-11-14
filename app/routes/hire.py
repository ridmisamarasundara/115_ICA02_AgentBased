from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.messages import Performative as P
from app.database import get_db
from app.deps import flash, require_user
from app.models import HireRequest, Venue
from app.schemas import HIRE_LABELS, HireForm
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()


def _venues(db):
    return db.query(Venue).filter_by(open_for_hire=True).order_by(Venue.name).all()


def _render(request, db, form=None, errors=None, proposal=None, status_code=200):
    return templates.TemplateResponse(request, "hire/form.html", {
        "venues": _venues(db), "form": form or {}, "errors": errors or [], "proposal": proposal},
        status_code=status_code)


@router.get("/hire")
def hire_form(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/hire", dependencies=[Depends(verify_csrf)])
def hire_submit(request: Request, venue_id: str = Form(""), start_time: str = Form(""), end_time: str = Form(""),
                guests: str = Form(""), purpose: str = Form(""), user=Depends(require_user),
                db: Session = Depends(get_db)):
    form = {"venue_id": venue_id, "start_time": start_time, "end_time": end_time,
            "guests": guests, "purpose": purpose}
    try:
        data = HireForm(venue_id=venue_id, start_time=start_time, end_time=end_time, guests=guests, purpose=purpose)
    except ValidationError as exc:
        errors = [f"{HIRE_LABELS.get(str(e['loc'][0]), e['loc'][0])}: {e['msg'].replace('Value error, ', '')}"
                  for e in exc.errors()]
        return _render(request, db, form, errors, status_code=400)

    reply = ask(db, "VenueAgent", "hire_request", sender=f"User #{user.id}", venue_id=data.venue_id,
                user_id=user.id, start_time=data.start_time.isoformat(), end_time=data.end_time.isoformat(),
                guests=data.guests, purpose=data.purpose)

    if reply.performative == P.AGREE:
        flash(request, f"Your venue hire is confirmed. Price: Rs. {reply.content['price']:,.2f}"
                       f"{' (includes weekend surcharge)' if reply.content.get('weekend_surcharge') else ''}.",
              "success")
        return RedirectResponse("/hire/my", status_code=303)
    if reply.performative == P.INFORM:
        flash(request, f"Price: Rs. {reply.content['price']:,.2f}. {reply.content['reason']}. "
                       "You will be notified when the admin decides.", "info")
        return RedirectResponse("/hire/my", status_code=303)
    if reply.performative == P.PROPOSE:
        alternatives = [{**a, "start": datetime.fromisoformat(a["start_time"]),
                         "end": datetime.fromisoformat(a["end_time"])} for a in reply.content["alternatives"]]
        return _render(request, db, form, proposal={"reason": reply.content["reason"], "alternatives": alternatives})
    return _render(request, db, form, [reply.content.get("reason", "The request could not be processed")],
                   status_code=400)


@router.get("/hire/my")
def my_hire_requests(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    rows = db.query(HireRequest).filter_by(user_id=user.id).order_by(HireRequest.id.desc()).all()
    venues = {v.id: v.name for v in db.query(Venue).all()}
    return templates.TemplateResponse(request, "hire/my.html", {
        "items": [{"r": r, "venue": venues.get(r.venue_id, "?")} for r in rows]})
