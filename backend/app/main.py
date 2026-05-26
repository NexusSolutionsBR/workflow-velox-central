from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings
from app.api import auth, sessions, center, audit

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET não configurado no ambiente — defina no .env")
    SQLModel.metadata.create_all(engine)
    # Migrações incrementais — colunas adicionadas após criação inicial das tabelas
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE scheduled_sync ADD COLUMN IF NOT EXISTS contact_name VARCHAR"))
        conn.commit()
    yield

app = FastAPI(
    title="Velox API",
    description="API para automação de extração de ocorrências e resumos com ChatGPT e Google Drive",
    version="1.0.0",
    lifespan=lifespan
)

from app.core.audit import AuditLogMiddleware

# CORS configuration — origens explícitas para suportar cookies httpOnly
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuditLogMiddleware)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(center.router, prefix="/center", tags=["center"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API do Velox"}
