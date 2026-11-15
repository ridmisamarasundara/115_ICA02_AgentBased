from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.messages import Performative as P
from app.agents.ticket_agent import CHECKIN_OPENS_BEFORE
from app.database import get_db
from app.deps import require_role
from app.models import Event
from app.models._util import utcnow
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()
staff_or_admin = require_role("staff", "admin")


@router.get("/staff/scan")
def scanner_page(request: Request, event: int = 0, user=Depends(staff_or_admin), db: Session = Depends(get_db)):
    now = utcnow()
    events = (db.query(Event).filter(Event.status == "published", Event.end_time > now)
              .order_by(Event.start_time, Event.id).all())
    items = [{"event": e, "open_now": e.start_time - CHECKIN_OPENS_BEFORE <= now <= e.end_time} for e in events]
    ids = [i["event"].id for i in items]
    if event in ids:
        selected = event
    else:
        selected = next((i["event"].id for i in items if i["open_now"]), ids[0] if ids else 0)
    return templates.TemplateResponse(request, "staff/scan.html", {"items": items, "selected": selected})


class ScanIn(BaseModel):
    code: str
    event_id: int


@router.post("/api/scan", dependencies=[Depends(verify_csrf)])
def scan_ticket(payload: ScanIn, user=Depends(staff_or_admin), db: Session = Depends(get_db)):
    """The scanner page posts here. TicketAgent makes the decision; this only relays it as JSON."""
    reply = ask(db, "TicketAgent", "scan", sender=f"Staff #{user.id}", code=payload.code, event_id=payload.event_id)
    c = reply.content
    result = {"ok": reply.performative == P.AGREE, "decision": c.get("decision", "error"),
              "reason": c.get("reason", "")}
    for key in ("holder", "category", "event_title", "scan_count", "suspicious"):
        if key in c:
            result[key] = c[key]
    return result
