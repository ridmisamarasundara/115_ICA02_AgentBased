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
