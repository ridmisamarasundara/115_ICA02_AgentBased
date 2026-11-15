import re
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterForm(BaseModel):
    name: str
    email: str
    password: str
    confirm: str

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = v.strip()
        if not 2 <= len(v) <= 100:
            raise ValueError("Name must be 2 to 100 characters")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip().lower()
        if len(v) > 255 or not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v):
        if not 8 <= len(v) <= 64:
            raise ValueError("Password must be 8 to 64 characters")
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one number")
        return v

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm:
            raise ValueError("Passwords do not match")
        return self


class HireForm(BaseModel):
    venue_id: int
    start_time: datetime
    end_time: datetime
    guests: int
    purpose: str

    @field_validator("guests")
    @classmethod
    def _guests(cls, v):
        if not 1 <= v <= 5000:
            raise ValueError("Guests must be between 1 and 5000")
        return v

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, v):
        v = v.strip()
        if not 3 <= len(v) <= 255:
            raise ValueError("Purpose must be 3 to 255 characters")
        return v


HIRE_LABELS = {"venue_id": "Venue", "start_time": "Start time", "end_time": "End time",
               "guests": "Guests", "purpose": "Purpose"}


# ---------------------------------------------------------------- admin forms
from app.constants import EVENT_CATEGORIES  # noqa: E402


def format_errors(exc, labels: dict) -> list[str]:
    out = []
    for e in exc.errors():
        loc = e["loc"]
        if len(loc) >= 3 and loc[0] == "categories":
            label = f"Ticket category {int(loc[1]) + 1} {labels.get(str(loc[2]), loc[2])}"
        elif loc:
            label = labels.get(str(loc[0]), str(loc[0]))
        else:
            label = "Form"
        out.append(f"{label}: {e['msg'].replace('Value error, ', '')}")
    return out


class VenueForm(BaseModel):
    name: str
    location: str
    capacity: int
    description: str = ""
    image_url: str = ""
    hourly_rate: float
    open_for_hire: bool = False

    @field_validator("name", "location")
    @classmethod
    def _text(cls, v):
        v = v.strip()
        if not 2 <= len(v) <= 150:
            raise ValueError("must be 2 to 150 characters")
        return v

    @field_validator("capacity")
    @classmethod
    def _capacity(cls, v):
        if not 1 <= v <= 100000:
            raise ValueError("must be between 1 and 100000")
        return v

    @field_validator("hourly_rate")
    @classmethod
    def _rate(cls, v):
        if not 0 <= v <= 10_000_000:
            raise ValueError("must be 0 or more")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v):
        v = v.strip()
        if len(v) > 2000:
            raise ValueError("must be at most 2000 characters")
        return v

    @field_validator("image_url")
    @classmethod
    def _image(cls, v):
        v = v.strip()
        if v and not re.match(r"^https?://", v, re.I):
            raise ValueError("must start with http:// or https://")
        if len(v) > 500:
            raise ValueError("is too long")
        return v


VENUE_LABELS = {"name": "Name", "location": "Location", "capacity": "Capacity", "description": "Description",
                "image_url": "Image URL", "hourly_rate": "Hourly hire rate", "open_for_hire": "Open for hire"}


class TicketCategoryIn(BaseModel):
    id: int | None = None
    name: str
    price: float
    quantity: int

    @field_validator("id", mode="before")
    @classmethod
    def _blank_id(cls, v):
        return None if v in ("", None) else v

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = v.strip()
        if not 1 <= len(v) <= 100:
            raise ValueError("name must be 1 to 100 characters")
        return v

    @field_validator("price")
    @classmethod
    def _price(cls, v):
        if not 0 <= v <= 10_000_000:
            raise ValueError("must be 0 or more")
        return round(v, 2)

    @field_validator("quantity")
    @classmethod
    def _qty(cls, v):
        if not 1 <= v <= 100000:
            raise ValueError("must be between 1 and 100000")
        return v


class EventForm(BaseModel):
    title: str
    category: str
    venue_id: int
    start_time: datetime
    end_time: datetime
    description: str = ""
    categories: list[TicketCategoryIn]

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        v = v.strip()
        if not 3 <= len(v) <= 200:
            raise ValueError("must be 3 to 200 characters")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v not in EVENT_CATEGORIES:
            raise ValueError("choose one of: " + ", ".join(EVENT_CATEGORIES))
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v):
        v = v.strip()
        if len(v) > 2000:
            raise ValueError("must be at most 2000 characters")
        return v

    @field_validator("categories")
    @classmethod
    def _need_one(cls, v):
        if not v:
            raise ValueError("Add at least one ticket category")
        return v

    @model_validator(mode="after")
    def _times(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after the start time")
        return self


EVENT_LABELS = {"title": "Title", "category": "Category", "venue_id": "Venue", "start_time": "Start time",
                "end_time": "End time", "description": "Description", "categories": "Ticket categories",
                "name": "name", "price": "price", "quantity": "quantity"}
