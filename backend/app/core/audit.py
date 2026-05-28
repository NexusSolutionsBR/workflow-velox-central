import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.database import engine
from sqlmodel import Session
from app.models.domain import AuditLog
from app.core.config import settings

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
        
        try:
            response = await call_next(request)
            status_str = "SUCCESS" if response.status_code < 400 else "ERROR"
            
            if request.url.path.startswith(("/api/sessions", "/api/center", "/api/auth")):
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
