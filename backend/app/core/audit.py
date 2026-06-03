import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.database import engine
from sqlmodel import Session
from app.models.domain import AuditLog
from app.core.config import settings

# Leituras de alta frequência (polling/listagem) que NÃO devem poluir a auditoria.
# Mantemos no log apenas ações relevantes (login, start, cancel, insert, export, etc.).
def _should_audit(method: str, path: str) -> bool:
    if not path.startswith(("/api/sessions", "/api/center", "/api/auth")):
        return False
    if method == "GET":
        # listagens e polling de status — puro ruído, registrado a cada 2s
        if path in ("/api/sessions", "/api/sessions/scheduled-syncs"):
            return False
        if path.endswith("/status"):
            return False
    return True


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = None
        token = request.cookies.get("access_token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        if token:
            try:
                payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
                user_id = payload.get("id")
            except Exception:
                pass

        action = request.method + " " + request.url.path
        audit = _should_audit(request.method, request.url.path)

        try:
            response = await call_next(request)
            status_str = "SUCCESS" if response.status_code < 400 else "ERROR"

            if audit:
                with Session(engine) as session:
                    log = AuditLog(
                        user_id=user_id,
                        action=action,
                        endpoint=str(request.url.path),
                        status=status_str,
                        ip=request.client.host if request.client else None
                    )
                    session.add(log)
                    session.commit()
            return response
        except Exception as e:
            if audit:
                with Session(engine) as session:
                    log = AuditLog(
                        user_id=user_id,
                        action=action,
                        endpoint=str(request.url.path),
                        status="ERROR",
                        error=str(e),
                        ip=request.client.host if request.client else None
                    )
                    session.add(log)
                    session.commit()
            raise e
