from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from sqlmodel import select
from app.core.security import DbSessionDep, CurrentUserDep
from app.models.domain import Summary, SessionRecord
from app.services.center_service import insert_occurrence

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

    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == data.sessionId)).first()
    ficha = session_rec.ficha if session_rec else data.sessionId
    drive_folder_url = session_rec.drive_folder_url if session_rec else ""

    try:
        result = await insert_occurrence(data.sessionId, ficha, data.summaryText, drive_folder_url)
        total = result.get("total_inserido", "?") if isinstance(result, dict) else "?"
        if session_rec:
            session_rec.center_inserted = True
            session_rec.center_duplicate = False
            session.commit()
        return InsertMGMResponse(message=f"{total} ocorrência(s) inserida(s) no Center com sucesso", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
