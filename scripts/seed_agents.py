"""
Seed the database with test agents for local development.

Usage (inside Docker):
    docker compose exec api python scripts/seed_agents.py
"""
import asyncio
import uuid
import sys
import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.models.agent import Agent

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def seed():
    async with SessionLocal() as session:
        async with session.begin():
            agent1 = Agent(
                id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
                email="agent1@vericlaim.com",
                full_name="Agent One",
                hashed_password=get_password_hash("password123"),
                is_active=True
            )
            agent2 = Agent(
                id=uuid.UUID("22222222-3333-4444-5555-666666666666"),
                email="agent2@vericlaim.com",
                full_name="Agent Two",
                hashed_password=get_password_hash("password123"),
                is_active=True
            )

            session.add_all([agent1, agent2])
            
    await engine.dispose()
    print("Seeded 2 test agents successfully.")
    print("  agent1@vericlaim.com / password123")
    print("  agent2@vericlaim.com / password123")

if __name__ == "__main__":
    asyncio.run(seed())
