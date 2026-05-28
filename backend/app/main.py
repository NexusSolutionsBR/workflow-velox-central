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
        conn.execute(text("ALTER TABLE session ADD COLUMN IF NOT EXISTS drive_folder_url VARCHAR"))
        conn.execute(text("ALTER TABLE session ADD COLUMN IF NOT EXISTS center_inserted BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE session ADD COLUMN IF NOT EXISTS center_duplicate BOOLEAN DEFAULT FALSE"))
        conn.commit()
    yield

import os
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Velox API",
    description="API para automação de extração de ocorrências e resumos com ChatGPT e Google Drive",
    version="1.0.0",
    lifespan=lifespan
)

# Servir arquivos estáticos da pasta backend/app/static
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Copiar a logo da pasta templates para a pasta static, se existir
templates_logo = os.path.join(os.path.dirname(__file__), "templates", "logo-velox.png")
static_logo = os.path.join(static_dir, "logo-velox.png")
if os.path.exists(templates_logo):
    import shutil
    shutil.copy2(templates_logo, static_logo)

app.mount("/static", StaticFiles(directory=static_dir), name="static")


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

from fastapi import APIRouter
api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(center.router, prefix="/center", tags=["center"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(api_router)

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API do Velox"}
