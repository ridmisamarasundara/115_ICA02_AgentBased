import re

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
