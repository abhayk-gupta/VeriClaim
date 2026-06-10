import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
import re


class CustomerBase(BaseModel):
    phone_e164: str
    full_name: str
    email: Optional[str] = None
    whatsapp_opt_in: bool = True

    @field_validator("phone_e164")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{6,14}$", v):
            raise ValueError("Phone must be in E.164 format, e.g. +14155552671")
        return v


class CustomerCreate(CustomerBase):
    pass


class CustomerRead(CustomerBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
