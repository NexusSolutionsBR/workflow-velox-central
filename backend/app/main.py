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
        conn.execute(text("ALTER TABLE session ADD COLUMN IF NOT EXISTS error_message VARCHAR"))
        conn.commit()
    yield

import os
from fastapi.staticfiles import StaticFiles

# Docs interativas (Swagger/ReDoc/OpenAPI) só são expostas quando ENABLE_DOCS=true.
# Em produção ficam desligadas para não revelar a superfície da API a quem não tem token.
_docs_kwargs = (
    dict(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
    if settings.ENABLE_DOCS
    else dict(docs_url=None, redoc_url=None, openapi_url=None)
)

app = FastAPI(
    title="Velox API",
    description="API para automação de extração de ocorrências e resumos com ChatGPT e Google Drive",
    version="1.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
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


import jwt
from starlette.responses import JSONResponse
from app.core.audit import AuditLogMiddleware
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers de segurança aplicados a todas as respostas."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers.setdefault(
            "Cache-Control", "no-store, no-cache, must-revalidate, private"
        )
        return response


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Porta de entrada para /api: sem token válido, devolve 401 uniforme
    independentemente de a rota existir ou do método HTTP. Assim a existência
    de endpoints (e o 405 de método errado) não vaza para quem não tem token.

    Rotas públicas: login/logout e o preflight CORS (OPTIONS)."""
    _PUBLIC_PATHS = ("/api/auth/login", "/api/auth/logout")

    async def dispatch(self, request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api")
            or path in self._PUBLIC_PATHS
        ):
            return await call_next(request)

        token = request.cookies.get("access_token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]

        if token:
            try:
                jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
                return await call_next(request)
            except jwt.PyJWTError:
                pass

        return JSONResponse(status_code=401, content={"detail": "Não autenticado"})


# Ordem de registro: o último adicionado é o mais externo na requisição.
# Queremos AuthGate "dentro" de CORS/Security para que a resposta 401 ainda
# receba os headers de CORS (frontend precisa ler) e de segurança.
app.add_middleware(AuthGateMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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
