from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent_client import ask
from app.agents.messages import Performative as P
from app.constants import EVENT_CATEGORIES
from app.database import get_db
from app.deps import flash, require_role
from app.models import Booking, Event, TicketCategory, Venue
from app.models._util import utcnow
from app.schemas import EVENT_LABELS, VENUE_LABELS, EventForm, VenueForm, format_errors
from app.security import verify_csrf
from app.templating import templates

router = APIRouter()
admin_only = require_role("admin")
FMT = "%Y-%m-%dT%H:%M"


# ============================================================ venues
def _venue_page(request, venue=None, form=None, errors=None, status_code=200):
    if form is None and venue is not None:
        form = {"name": venue.name, "location": venue.location, "capacity": venue.capacity,
                "description": venue.description, "image_url": venue.image_url,
                "hourly_rate": venue.hourly_rate, "open_for_hire": venue.open_for_hire}
    return templates.TemplateResponse(request, "admin/venue_form.html",
                                      {"venue": venue, "form": form or {}, "errors": errors or []},
                                      status_code=status_code)


def _read_venue(name, location, capacity, description, image_url, hourly_rate, open_for_hire):
    form = {"name": name, "location": location, "capacity": capacity, "description": description,
            "image_url": image_url, "hourly_rate": hourly_rate, "open_for_hire": bool(open_for_hire)}
    try:
        return VenueForm(name=name, location=location, capacity=capacity, description=description,
                         image_url=image_url, hourly_rate=hourly_rate, open_for_hire=bool(open_for_hire)), [], form
    except ValidationError as exc:
        return None, format_errors(exc, VENUE_LABELS), form


@router.get("/admin/venues")
def venues_list(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "admin/venues_list.html",
                                      {"venues": db.query(Venue).order_by(Venue.name).all()})


@router.get("/admin/venues/new")
def venue_new(request: Request, user=Depends(admin_only)):
    return _venue_page(request)


@router.post("/admin/venues/new", dependencies=[Depends(verify_csrf)])
def venue_create(request: Request, name: str = Form(""), location: str = Form(""), capacity: str = Form(""),
                 description: str = Form(""), image_url: str = Form(""), hourly_rate: str = Form(""),
                 open_for_hire: str = Form(""), user=Depends(admin_only), db: Session = Depends(get_db)):
    data, errors, form = _read_venue(name, location, capacity, description, image_url, hourly_rate, open_for_hire)
    if errors:
        return _venue_page(request, None, form, errors, 400)
    db.add(Venue(**data.model_dump()))
    db.commit()
    flash(request, f"Venue '{data.name}' created.", "success")
    return RedirectResponse("/admin/venues", status_code=303)


@router.get("/admin/venues/{venue_id}/edit")
def venue_edit(venue_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(404, "Venue not found")
    return _venue_page(request, venue)


@router.post("/admin/venues/{venue_id}/edit", dependencies=[Depends(verify_csrf)])
def venue_update(venue_id: int, request: Request, name: str = Form(""), location: str = Form(""),
                 capacity: str = Form(""), description: str = Form(""), image_url: str = Form(""),
                 hourly_rate: str = Form(""), open_for_hire: str = Form(""), user=Depends(admin_only),
                 db: Session = Depends(get_db)):
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(404, "Venue not found")
    data, errors, form = _read_venue(name, location, capacity, description, image_url, hourly_rate, open_for_hire)
    if errors:
        return _venue_page(request, venue, form, errors, 400)
    for key, value in data.model_dump().items():
        setattr(venue, key, value)
    db.commit()
    flash(request, f"Venue '{venue.name}' updated.", "success")
    return RedirectResponse("/admin/venues", status_code=303)


# ============================================================ events
def _event_page(request, db, event=None, form=None, errors=None, locked=False, status_code=200):
    if form is None and event is not None:
        form = {"title": event.title, "category": event.category, "venue_id": str(event.venue_id),
                "start_time": event.start_time.strftime(FMT), "end_time": event.end_time.strftime(FMT),
                "description": event.description,
                "cats": [{"id": c.id, "name": c.name, "price": c.price, "quantity": c.quantity}
                         for c in sorted(event.categories, key=lambda c: c.id)]}
    form = form or {}
    if not form.get("cats"):
        form["cats"] = [{"id": "", "name": "", "price": "", "quantity": ""}]
    return templates.TemplateResponse(request, "admin/event_form.html", {
        "event": event, "form": form, "errors": errors or [], "locked": locked,
        "venues": db.query(Venue).order_by(Venue.name).all(), "categories": EVENT_CATEGORIES},
        status_code=status_code)


def _read_event(title, category, venue_id, start_time, end_time, description, cat_id, cat_name, cat_price, cat_qty):
    cat_id, cat_name, cat_price, cat_qty = cat_id or [], cat_name or [], cat_price or [], cat_qty or []

    def at(lst, i):
        return lst[i].strip() if i < len(lst) else ""

    rows = []
    for i in range(max(len(cat_id), len(cat_name), len(cat_price), len(cat_qty))):
        row = {"id": at(cat_id, i), "name": at(cat_name, i), "price": at(cat_price, i), "quantity": at(cat_qty, i)}
        if any(row.values()):
            rows.append(row)
    form = {"title": title, "category": category, "venue_id": venue_id, "start_time": start_time,
            "end_time": end_time, "description": description, "cats": rows}
    try:
        data = EventForm(title=title, category=category, venue_id=venue_id, start_time=start_time,
                         end_time=end_time, description=description, categories=rows)
        return data, [], form
    except ValidationError as exc:
        return None, format_errors(exc, EVENT_LABELS), form


def _agent_checks(db, user, venue_id, start, end, total_tickets, exclude_event_id=None):
    """VenueAgent decides: capacity (C1) and clash-free slot (E1-E3). Returns a list of refusal reasons."""
    errors = []
    sender = f"Admin #{user.id}"
    r = ask(db, "VenueAgent", "check_capacity", sender=sender, venue_id=venue_id, total_tickets=total_tickets)
    if r.performative != P.AGREE:
        errors.append(r.content.get("reason", "Capacity check failed"))
    r = ask(db, "VenueAgent", "check_slot", sender=sender, venue_id=venue_id, start_time=start.isoformat(),
            end_time=end.isoformat(), exclude_event_id=exclude_event_id)
    if r.performative != P.AGREE:
        errors.append(r.content.get("reason", "The time slot is not available"))
    return errors


def _sold_anything(ev):
    return any(c.sold > 0 for c in ev.categories)


@router.get("/admin/events")
def events_list(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    items = []
    for ev in db.query(Event).order_by(Event.start_time.desc(), Event.id.desc()).all():
        sold = sum(b.quantity for b in db.query(Booking).filter_by(event_id=ev.id, status="confirmed").all())
        items.append({"event": ev, "venue": ev.venue.name, "offered": sum(c.quantity for c in ev.categories),
                      "sold": sold})
    return templates.TemplateResponse(request, "admin/events_list.html", {"items": items})


@router.get("/admin/events/new")
def event_new(request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    return _event_page(request, db)


@router.post("/admin/events/new", dependencies=[Depends(verify_csrf)])
def event_create(request: Request, title: str = Form(""), category: str = Form(""), venue_id: str = Form(""),
                 start_time: str = Form(""), end_time: str = Form(""), description: str = Form(""),
                 action: str = Form("draft"), cat_id: list[str] | None = Form(None),
                 cat_name: list[str] | None = Form(None), cat_price: list[str] | None = Form(None),
                 cat_qty: list[str] | None = Form(None), user=Depends(admin_only), db: Session = Depends(get_db)):
    data, errors, form = _read_event(title, category, venue_id, start_time, end_time, description,
                                     cat_id, cat_name, cat_price, cat_qty)
    publish = action == "publish"
    if data and publish and data.start_time <= utcnow():
        errors.append("An event that starts in the past cannot be published")
    if data and not errors:
        errors = _agent_checks(db, user, data.venue_id, data.start_time, data.end_time,
                               sum(c.quantity for c in data.categories))
    if errors:
        return _event_page(request, db, None, form, errors, status_code=400)

    ev = Event(title=data.title, category=data.category, venue_id=data.venue_id, start_time=data.start_time,
               end_time=data.end_time, description=data.description, status="published" if publish else "draft")
    db.add(ev)
    db.flush()
    for c in data.categories:
        db.add(TicketCategory(event_id=ev.id, name=c.name, price=c.price, quantity=c.quantity))
    db.commit()
    flash(request, f"Event '{ev.title}' {'published' if publish else 'saved as a draft'}.", "success")
    return RedirectResponse("/admin/events", status_code=303)


@router.get("/admin/events/{event_id}/edit")
def event_edit(event_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(404, "Event not found")
    if ev.status == "cancelled":
        flash(request, "A cancelled event cannot be edited.", "warning")
        return RedirectResponse("/admin/events", status_code=303)
    return _event_page(request, db, ev, locked=_sold_anything(ev))


@router.post("/admin/events/{event_id}/edit", dependencies=[Depends(verify_csrf)])
def event_update(event_id: int, request: Request, title: str = Form(""), category: str = Form(""),
                 venue_id: str = Form(""), start_time: str = Form(""), end_time: str = Form(""),
                 description: str = Form(""), action: str = Form("draft"), cat_id: list[str] | None = Form(None),
                 cat_name: list[str] | None = Form(None), cat_price: list[str] | None = Form(None),
                 cat_qty: list[str] | None = Form(None), user=Depends(admin_only), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(404, "Event not found")
    if ev.status == "cancelled":
        flash(request, "A cancelled event cannot be edited.", "warning")
        return RedirectResponse("/admin/events", status_code=303)

    if _sold_anything(ev):
        # Tickets exist: only the descriptive fields may change (time, venue and tickets stay fixed).
        errors = []
        if not 3 <= len(title.strip()) <= 200:
            errors.append("Title: must be 3 to 200 characters")
        if category not in EVENT_CATEGORIES:
            errors.append("Category: choose a valid category")
        if len(description.strip()) > 2000:
            errors.append("Description: must be at most 2000 characters")
        if errors:
            return _event_page(request, db, ev, None, errors, locked=True, status_code=400)
        ev.title, ev.category, ev.description = title.strip(), category, description.strip()
        db.commit()
        flash(request, "Event details updated.", "success")
        return RedirectResponse("/admin/events", status_code=303)

    data, errors, form = _read_event(title, category, venue_id, start_time, end_time, description,
                                     cat_id, cat_name, cat_price, cat_qty)
    publish = action == "publish" and ev.status == "draft"
    if data and publish and data.start_time <= utcnow():
        errors.append("An event that starts in the past cannot be published")
    existing = {c.id: c for c in ev.categories}
    if data:
        posted_ids = {c.id for c in data.categories if c.id is not None}
        for c in data.categories:
            if c.id is not None and c.id not in existing:
                errors.append(f"Ticket category {c.id} does not belong to this event")
        extra = sum(c.quantity for cid, c in existing.items() if cid not in posted_ids)
        if not errors:
            errors = _agent_checks(db, user, data.venue_id, data.start_time, data.end_time,
                                   sum(c.quantity for c in data.categories) + extra, exclude_event_id=ev.id)
    if errors:
        return _event_page(request, db, ev, form, errors, status_code=400)

    ev.title, ev.category, ev.venue_id = data.title, data.category, data.venue_id
    ev.start_time, ev.end_time, ev.description = data.start_time, data.end_time, data.description
    for c in data.categories:
        if c.id is None:
            db.add(TicketCategory(event_id=ev.id, name=c.name, price=c.price, quantity=c.quantity))
        else:
            row = existing[c.id]
            row.name, row.price, row.quantity = c.name, c.price, c.quantity
    if publish:
        ev.status = "published"
    db.commit()
    flash(request, f"Event '{ev.title}' updated{' and published' if publish else ''}.", "success")
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/admin/events/{event_id}/publish", dependencies=[Depends(verify_csrf)])
def event_publish(event_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(404, "Event not found")
    problems = []
    if ev.status != "draft":
        problems.append("Only draft events can be published")
    elif not ev.categories:
        problems.append("Add at least one ticket category first")
    elif ev.start_time <= utcnow():
        problems.append("An event that starts in the past cannot be published")
    else:
        problems = _agent_checks(db, user, ev.venue_id, ev.start_time, ev.end_time,
                                 sum(c.quantity for c in ev.categories), exclude_event_id=ev.id)
    if problems:
        flash(request, "Cannot publish: " + "; ".join(problems), "danger")
    else:
        ev.status = "published"
        db.commit()
        flash(request, f"'{ev.title}' is now published.", "success")
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/admin/events/{event_id}/cancel", dependencies=[Depends(verify_csrf)])
def event_cancel(event_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    reply = ask(db, "BookingAgent", "cancel_event", sender=f"Admin #{user.id}", event_id=event_id)
    if reply.performative == P.AGREE:
        flash(request, f"Event cancelled. {reply.content['bookings_refunded']} booking(s) fully refunded "
                       f"(Rs. {reply.content['total_refunded']:,.2f}).", "success")
    else:
        flash(request, reply.content.get("reason", "The event could not be cancelled"), "danger")
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/admin/events/{event_id}/delete", dependencies=[Depends(verify_csrf)])
def event_delete(event_id: int, request: Request, user=Depends(admin_only), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(404, "Event not found")
    if ev.status != "draft":
        flash(request, "Only draft events can be deleted. Cancel a published event instead.", "danger")
    else:
        db.delete(ev)
        db.commit()
        flash(request, "Draft deleted.", "info")
    return RedirectResponse("/admin/events", status_code=303)
