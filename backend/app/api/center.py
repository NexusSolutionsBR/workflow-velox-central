import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlmodel import select
from app.core.security import DbSessionDep, CurrentUserDep
from app.models.domain import Summary
from app.core.config import settings

router = APIRouter()

class InsertMGMRequest(BaseModel):
    sessionId: str
    summaryText: str

class InsertMGMResponse(BaseModel):
    message: str
    data: Any = None

@router.post("/mgm", response_model=InsertMGMResponse)
async def insert_mgm(data: InsertMGMRequest, current_user: CurrentUserDep, session: DbSessionDep):
    if not data.sessionId or not data.summaryText:
        raise HTTPException(status_code=400, detail="Faltam dados")

    summary_rec = session.exec(select(Summary).where(Summary.session_id == data.sessionId)).first()
    if summary_rec:
        summary_rec.edited_summary = data.summaryText
        session.commit()

    if not settings.CENTER_API_KEY:
        print(f"[Center API Mock] Enviando MGM para {data.sessionId}")
        return InsertMGMResponse(message="MGM inserido com sucesso (Simulado)")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.CENTER_API_URL,
                json={"sessionId": data.sessionId, "summary": data.summaryText},
                headers={"Authorization": f"Bearer {settings.CENTER_API_KEY}"}
            )
            response.raise_for_status()
            return InsertMGMResponse(message="MGM inserido com sucesso", data=response.json())
    except Exception as e:
        print(f"Erro ao inserir MGM no Center: {e}")
        raise HTTPException(status_code=500, detail="Erro ao inserir no Center API")
