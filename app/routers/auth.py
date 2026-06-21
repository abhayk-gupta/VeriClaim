import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError

from app.config import get_settings
from app.database import get_session
from app.models.agent import Agent
from app.schemas.agent import AgentRead, Token
import bcrypt

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(Agent).where(Agent.email == form_data.username))
    agent = result.scalar_one_or_none()
    
    if not agent or not verify_password(form_data.password, agent.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive agent"
        )
    
    access_token = create_access_token(data={"sub": str(agent.id)})
    return {"access_token": access_token, "token_type": "bearer"}

from app.auth_deps import get_current_agent

@router.get("/me", response_model=AgentRead)
async def get_me(current_agent: Agent = Depends(get_current_agent)):
    return current_agent
