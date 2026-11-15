import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.messages import Performative as P
from app.database import get_db
from app.deps import flash, require_role
from app.models import AgentState, Booking, Event, HireRequest, MessageLog, Ticket, Venue
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()
admin_only = require_role("admin")

AGENT_GOALS = {
    "VenueAgent": "Keep every venue's calendar free of clashes (event slots, private hire, pricing).",
    "BookingAgent": "Sell tickets fairly without overselling (limits, atomic seats, refunds).",
    "TicketAgent": "Admit each ticket exactly once (unique codes, door decisions).",
    "WaitlistAgent": "Pass freed seats to waiting customers (timed holds, expiry sweep every 30 s).",
    "NotificationAgent": "Tell the right person what affects them (listens to broadcasts).",
}
PERFORMATIVES = ["REQUEST", "AGREE", "REFUSE", "PROPOSE", "INFORM", "FAILURE"]
BADGES = {"REQUEST": "primary", "AGREE": "success", "REFUSE": "danger", "PROPOSE": "warning",
          "INFORM": "info", "FAILURE": "dark"}


@router.get("/admin")
def dashboard(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    rows = []
    for ev in db.query(Event).order_by(Event.start_time.desc(), Event.id.desc()).all():
        sold = db.query(func.coalesce(func.sum(Booking.quantity), 0)).filter(
            Booking.event_id == ev.id, Booking.status == "confirmed").scalar()
        revenue = db.query(func.coalesce(func.sum(Booking.total_amount - Booking.refund_amount), 0)).filter(
            Booking.event_id == ev.id).scalar()
        checkins = db.query(func.count(Ticket.id)).filter(Ticket.event_id == ev.id, Ticket.status == "used").scalar()
        rows.append({"event": ev, "venue": ev.venue.name, "capacity": ev.venue.capacity,
                     "offered": sum(c.quantity for c in ev.categories), "sold": int(sold),
                     "revenue": float(revenue), "checkins": int(checkins)})
    charted = [r for r in rows if r["event"].status != "draft"]
    chart = {"labels": [r["event"].title for r in charted], "sold": [r["sold"] for r in charted],
             "checkins": [r["checkins"] for r in charted], "revenue": [r["revenue"] for r in charted]}
    totals = {"sold": sum(r["sold"] for r in rows), "revenue": sum(r["revenue"] for r in rows),
              "checkins": sum(r["checkins"] for r in rows),
              "pending_hires": db.query(HireRequest).filter_by(status="escalated").count(),
              "messages": db.query(MessageLog).count()}
    return templates.TemplateResponse(request, "admin/dashboard.html", {"rows": rows, "chart": chart, "totals": totals})


# ------------------------------------------------------------ hire approvals
@router.get("/admin/hire")
def hire_requests(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    from app.models import User
    venues = {v.id: v.name for v in db.query(Venue).all()}
    users = {u.id: u.name for u in db.query(User).all()}
    rows = db.query(HireRequest).order_by(HireRequest.id.desc()).all()
    rows.sort(key=lambda r: r.status != "escalated")          # pending first (stable sort keeps newest first)
    items = [{"r": r, "venue": venues.get(r.venue_id, "?"), "user": users.get(r.user_id, "?")} for r in rows]
    return templates.TemplateResponse(request, "admin/hire.html", {"items": items})


@router.post("/admin/hire/{request_id}/resolve", dependencies=[Depends(verify_csrf)])
def hire_resolve(request_id: int, request: Request, decision: str = Form(""), reason: str = Form(""),
                 user=Depends(admin_only), db: Session = Depends(get_db)):
    if decision not in ("approve", "reject"):
        flash(request, "Choose approve or reject.", "danger")
        return RedirectResponse("/admin/hire", status_code=303)
    reply = ask(db, "VenueAgent", "resolve_hire", sender=f"Admin #{user.id}", request_id=request_id,
                decision=decision, reason=reason.strip())
    if reply.performative == P.AGREE:
        flash(request, f"Hire request #{request_id} {'approved' if decision == 'approve' else 'rejected'}.", "success")
    else:
        flash(request, reply.content.get("reason", "Could not update the request"), "danger")
    return RedirectResponse("/admin/hire", status_code=303)


# ------------------------------------------------------------ agent message log
def _summary(m):
    c = m.content or {}
    if c.get("reason"):
        return c["reason"]
    key = c.get("action") or c.get("event") or ""
    extras = [f"{k}={v}" for k, v in c.items() if k not in ("action", "event") and not isinstance(v, (list, dict))]
    return " ".join(filter(None, [key, ", ".join(extras[:4])]))


@router.get("/admin/messages")
def message_log(request: Request, conversation: str = "", agent: str = "", performative: str = "",
                user=Depends(admin_only), db: Session = Depends(get_db)):
    q = db.query(MessageLog)
    conversation = conversation.strip()
    if conversation:
        q = q.filter(MessageLog.conversation_id == conversation)
    if agent:
        q = q.filter(or_(MessageLog.sender == agent, MessageLog.receiver == agent))
    if performative in PERFORMATIVES:
        q = q.filter(MessageLog.performative == performative)
    rows = q.order_by(MessageLog.id.asc() if conversation else MessageLog.id.desc()).limit(200).all()
    items = [{"m": m, "summary": _summary(m), "badge": BADGES.get(m.performative, "secondary"),
              "json": json.dumps(m.content, indent=2, default=str)} for m in rows]
    return templates.TemplateResponse(request, "admin/messages.html", {
        "items": items, "conversation": conversation, "agent": agent, "performative": performative,
        "agents": list(AGENT_GOALS), "performatives": PERFORMATIVES})


# ------------------------------------------------------------ agent state
@router.get("/admin/agents")
def agent_state(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    groups = []
    for name, goal in AGENT_GOALS.items():
        rows = db.query(AgentState).filter_by(agent=name).order_by(AgentState.key).all()
        groups.append({"name": name, "goal": goal,
                       "state": [{"key": r.key, "value": (r.value or {}).get("v"), "updated": r.updated_at}
                                 for r in rows]})
    return templates.TemplateResponse(request, "admin/agents.html", {"groups": groups})
