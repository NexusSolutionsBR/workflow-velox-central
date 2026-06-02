from fastapi import APIRouter, Depends, Query
from sqlmodel import select, desc, col
from typing import Any
import json

from app.core.security import DbSessionDep, require_role
from app.models.domain import AuditLog, User

router = APIRouter()

# Logs de auditoria expõem IPs e ações de todos os usuários — restrito a ADMIN.
@router.get("", response_model=Any)
def get_audit_logs(
    session: DbSessionDep,
    current_user: User = Depends(require_role(["ADMIN"])),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    statement = select(AuditLog).order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    logs = session.exec(statement).all()

    user_ids = {log.user_id for log in logs if log.user_id}
    users = {
        u.id: u.name
        for u in session.exec(select(User).where(col(User.id).in_(user_ids))).all()
    } if user_ids else {}

    result = []
    for log in logs:
        payload_data = log.payload
        if payload_data and isinstance(payload_data, str):
            try:
                payload_data = json.loads(payload_data)
            except Exception:
                pass

        result.append({
            "id": log.id,
            "user_id": log.user_id,
            "user_name": users.get(log.user_id) if log.user_id else "Não autenticado",
            "action": log.action,
            "endpoint": log.endpoint,
            "session_id": log.session_id,
            "ficha": log.ficha,
            "status": log.status,
            "error": log.error,
            "ip": log.ip,
            "payload": payload_data,
            "created_at": log.created_at.isoformat()
        })

    return {"data": result, "total": len(result)}
