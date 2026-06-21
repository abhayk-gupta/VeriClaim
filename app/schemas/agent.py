import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class AgentBase(BaseModel):
    email: EmailStr
    full_name: str


class AgentCreate(AgentBase):
    password: str


class AgentRead(AgentBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str
