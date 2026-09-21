import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    name: str = Field(min_length=3)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        errors = []

        if not re.search(r"[A-Z]", value):
            errors.append("one uppercase letter")
        if not re.search(r"[0-9]", value):
            errors.append("one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            errors.append("one special character")

        if errors:
            raise ValueError(f"Password must contain at least {', '.join(errors)}")

        return value


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
