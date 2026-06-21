from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.config import get_settings
from app.database import get_session
from app.models.agent import Agent

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
settings = get_settings()

async def get_current_agent(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_session)) -> Agent:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        agent_id: str = payload.get("sub")
        if agent_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()
    
    if agent is None:
        raise credentials_exception
    if not agent.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive agent")
        
    return agent
