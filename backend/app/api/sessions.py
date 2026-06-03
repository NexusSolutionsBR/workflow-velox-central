import os
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Any, Optional
from sqlmodel import select, Session, col
import redis as redis_lib
from app.core.config import settings
from app.core.database import get_session
from app.core.security import DbSessionDep, CurrentUserDep, AdminUserDep
from app.models.domain import SessionRecord, Summary, ScheduledSync, User
from app.services.tasks import process_session, summarize_session, sync_session_images
from app.services.velox import fetch_session_messages

router = APIRouter()

_redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)


def _fetch_center_data(ficha: str) -> tuple[dict, str | None]:
    """Busca dados da ficha na API Center. Retorna (dados, mensagem_erro)."""
    identificador = getattr(settings, "CENTER_IDENTIFICADOR_FICHA", "")
    consulta_url = getattr(settings, "CENTER_CONSULTA_URL", "")
    if not identificador:
        return {}, "CENTER_IDENTIFICADOR_FICHA não configurado"
    if not consulta_url:
        return {}, "CENTER_CONSULTA_URL não configurado"
    try:
        import httpx
        with httpx.Client(timeout=10.0) as client:
            res = client.get(
                consulta_url,
                params={
                    "acao": "resultado",
                    "identificador": identificador,
                    "fichaparametro": ficha,
                },
            )
            res.raise_for_status()
            import json as _json
        data = res.json()
        # Algumas APIs retornam JSON duplamente codificado (string contendo JSON)
        if isinstance(data, str):
            data = _json.loads(data)
        if isinstance(data, list) and data:
            return data[0], None
        if isinstance(data, dict):
            return data, None
        return {}, f"Resposta inesperada do Center: {type(data).__name__}"
    except Exception as exc:
        return {}, f"Erro ao consultar Center: {exc}"


def _fill_template(template: str, data: dict) -> str:
    """Substitui {{campo}} pelos valores do dict, escapando HTML. Placeholders sem correspondência viram '—'."""
    for key, value in data.items():
        safe = escape(str(value)) if value is not None else '—'
        template = template.replace('{{' + key + '}}', safe)
    return re.sub(r'\{\{[^}]+\}\}', '—', template)


_IBGE_UF = {
    11:"RO",12:"AC",13:"AM",14:"RR",15:"PA",16:"AP",17:"TO",
    21:"MA",22:"PI",23:"CE",24:"RN",25:"PB",26:"PE",27:"AL",28:"SE",29:"BA",
    31:"MG",32:"ES",33:"RJ",35:"SP",
    41:"PR",42:"SC",43:"RS",
    50:"MS",51:"MT",52:"GO",53:"DF",
}

def _fmt_date(value: str) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).split(".")[0])
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)

def _fmt_currency(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)

def _format_center_data(data: dict) -> dict:
    """Formata campos do Center para exibição: datas, moedas, booleanos e UF."""
    if not data:
        return data
    d = dict(data)

    for f in ("data_criacao","data_lancamento","data_ocorrencia","data_acionamento",
              "data_autorizacao","data_chegada","data_previsao_chegada","data_encerramento",
              "data_encerramento_cobranca","data_finalizacao","data_confirmacao_prestador"):
        if f in d:
            d[f] = _fmt_date(d[f])

    for f in ("valor_veiculo","valor_carga","valor_total_recuperacao"):
        if f in d:
            d[f] = _fmt_currency(d[f])

    for f in ("previsao_cumprida","possui_ficha_filha"):
        if f in d:
            d[f] = "Sim" if d[f] else "Não"

    codigo_uf = d.get("estado_ocorrencia")
    if isinstance(codigo_uf, int):
        d["estado_uf"] = _IBGE_UF.get(codigo_uf, str(codigo_uf))
    else:
        d["estado_uf"] = str(codigo_uf) if codigo_uf else "—"

    return d


_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "report.html")
_REPORT_TEMPLATE = open(_TEMPLATE_PATH, encoding="utf-8").read()



class StartSessionRequest(BaseModel):
    url: str
    ficha: str
    do_transcribe: bool = True
    do_upload_images: bool = True
    do_summary: bool = False
    do_insert_center: bool = False


class StartSessionResponse(BaseModel):
    message: str
    sessionId: str


@router.get("")
def list_sessions(
    current_user: CurrentUserDep,
    session: DbSessionDep,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    ficha: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    query = select(SessionRecord)
    if ficha:
        query = query.where(col(SessionRecord.ficha).contains(ficha))
    if status:
        query = query.where(SessionRecord.status == status)
    query = query.order_by(col(SessionRecord.created_at).desc())

    total = len(session.exec(query).all())
    records = session.exec(query.offset((page - 1) * per_page).limit(per_page)).all()

    user_ids = {r.user_id for r in records if r.user_id}
    users = {u.id: u.name for u in session.exec(select(User).where(col(User.id).in_(user_ids))).all()} if user_ids else {}

    summary_ids = {r.session_id for r in records}
    summaries = {
        s.session_id
        for s in session.exec(
            select(Summary).where(col(Summary.session_id).in_(summary_ids))
        ).all()
    }

    return {
        "total": total,
        "page": page,
        "perPage": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "items": [
            {
                "sessionId": r.session_id,
                "ficha": r.ficha or "",
                "status": r.status,
                "contactName": r.contact_name,
                "operatorName": users.get(r.user_id) if r.user_id else None,
                "hasSummary": r.session_id in summaries,
                "hasRawContent": bool(r.raw_content),
                "createdAt": r.created_at.isoformat() + "Z" if r.created_at.tzinfo is None else r.created_at.isoformat(),
            }
            for r in records
        ],
    }


@router.post("/start", response_model=StartSessionResponse)
def start_processing(data: StartSessionRequest, current_user: CurrentUserDep, session: DbSessionDep):
    if not data.url or not data.ficha:
        raise HTTPException(status_code=400, detail="URL e Ficha são obrigatórios")

    session_id = ""
    try:
        parsed_url = urlparse(data.url)
        query_params = parse_qs(parsed_url.query)
        if "sessionId" in query_params:
            session_id = query_params["sessionId"][0]
        else:
            parts = parsed_url.path.strip("/").split("/")
            if parts:
                session_id = parts[-1]
    except Exception:
        raise HTTPException(status_code=400, detail="URL inválida")

    if not session_id or len(session_id) < 5:
        raise HTTPException(status_code=400, detail="Não foi possível extrair o sessionId da URL")

    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if session_rec:
        session_rec.ficha = data.ficha
        session_rec.status = "PROCESSING"
        session_rec.task_id = None
        session_rec.user_id = current_user.id
        session_rec.session_url = data.url
    else:
        session_rec = SessionRecord(
            session_id=session_id,
            ficha=data.ficha,
            status="PROCESSING",
            user_id=current_user.id,
            session_url=data.url,
        )
        session.add(session_rec)
    session.commit()

    # Limpar logs e conteúdo da execução anterior
    try:
        _redis.delete(f"pipeline_logs:{session_id}")
        _redis.delete(f"ai_content:{session_id}")
        _redis.delete(f"raw_content:{session_id}")
    except Exception:
        pass

    task = process_session.delay(session_id, data.ficha, data.do_transcribe, data.do_upload_images, data.do_summary, data.do_insert_center)
    session_rec.task_id = task.id
    session.commit()

    return StartSessionResponse(message="Processamento iniciado", sessionId=session_id)


@router.post("/{session_id}/cancel")
def cancel_session(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if session_rec.status not in ("PENDING", "PROCESSING", "SUMMARIZING", "SYNCING", "INSERTING"):
        raise HTTPException(status_code=400, detail="Sessão não está em processamento")

    task_id = session_rec.task_id
    session_rec.status = "CANCELLED"
    session.commit()

    if task_id:
        from app.core.celery_app import celery_app
        celery_app.control.revoke(task_id, terminate=False)

    return {"message": "Processamento cancelado"}


@router.post("/{session_id}/summarize")
def trigger_summarize(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if session_rec.status not in ("COMPLETED",):
        raise HTTPException(status_code=400, detail="Sessão precisa estar COMPLETED para gerar resumo")

    session_rec.status = "SUMMARIZING"
    task = summarize_session.delay(session_id)
    session_rec.task_id = task.id
    session.commit()

    return {"message": "Geração de resumo iniciada"}


@router.post("/{session_id}/sync-images")
def trigger_sync_images(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if session_rec.status not in ("COMPLETED",):
        raise HTTPException(status_code=400, detail="Sessão precisa estar COMPLETED para sincronizar imagens")

    ficha = session_rec.ficha or session_id
    session_rec.status = "SYNCING"
    task = sync_session_images.delay(session_id, ficha)
    session_rec.task_id = task.id
    session.commit()

    return {"message": "Sincronização de imagens iniciada"}


@router.get("/{session_id}/export")
def export_report(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    summary_rec = session.exec(select(Summary).where(Summary.session_id == session_id)).first()

    lines = []
    lines.append(f"RELATÓRIO DE ATENDIMENTO — FICHA {session_rec.ficha or session_id}")
    lines.append("=" * 60)
    lines.append("")

    if summary_rec and summary_rec.edited_summary:
        lines.append("RESUMO GERADO POR IA (EDITADO):")
        lines.append("-" * 40)
        lines.append(summary_rec.edited_summary)
        lines.append("")

    raw_content = _redis.get(f"raw_content:{session_id}") or session_rec.raw_content
    if raw_content:
        lines.append("TIMELINE COMPLETA:")
        lines.append("-" * 40)
        lines.append(raw_content)

    content = "\n".join(lines)
    safe_name = _sanitize_filename(session_rec.ficha or session_id)
    filename = f"relatorio_ficha_{safe_name}.txt"

    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{session_id}/summary")
def delete_summary(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    summary_rec = session.exec(select(Summary).where(Summary.session_id == session_id)).first()
    if summary_rec:
        session.delete(summary_rec)
        session.commit()
    return {"message": "Resumo apagado"}


@router.get("/{session_id}/status", response_model=Any)
def get_session_status(session_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    summary_rec = session.exec(select(Summary).where(Summary.session_id == session_id)).first()

    try:
        logs = _redis.lrange(f"pipeline_logs:{session_id}", 0, -1)
    except Exception:
        logs = []

    has_raw_content = bool(
        _redis.exists(f"raw_content:{session_id}") or session_rec.raw_content
    )

    return {
        "sessionId": session_rec.session_id,
        "ficha": session_rec.ficha,
        "status": session_rec.status,
        "hasRawContent": has_raw_content,
        "contactName": session_rec.contact_name,
        "driveFolderUrl": session_rec.drive_folder_url,
        "centerInserted": session_rec.center_inserted,
        "centerDuplicate": session_rec.center_duplicate,
        "errorMessage": session_rec.error_message,
        "summary": {
            "editedSummary": summary_rec.edited_summary if summary_rec else None,
            "originalSummary": summary_rec.original_summary if summary_rec else None,
        } if summary_rec else None,
        "logs": logs,
    }


@router.get("/scheduled-syncs")
def list_scheduled_syncs(
    current_user: CurrentUserDep,
    session: DbSessionDep,
    status: Optional[str] = Query(default=None),
):
    query = select(ScheduledSync)
    if status:
        query = query.where(ScheduledSync.status == status)
    query = query.order_by(col(ScheduledSync.created_at).desc())
    syncs = session.exec(query).all()

    def _fmt(dt):
        return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()

    return [
        {
            "id": s.id,
            "sessionId": s.session_id,
            "ficha": s.ficha or "",
            "contactName": s.contact_name,
            "runAt": _fmt(s.run_at),
            "status": s.status,
            "errorMessage": s.error_message,
            "createdAt": _fmt(s.created_at),
        }
        for s in syncs
    ]


@router.delete("/scheduled-syncs/{sync_id}")
def cancel_scheduled_sync(sync_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    scheduled = session.exec(
        select(ScheduledSync).where(ScheduledSync.id == sync_id)
    ).first()
    if not scheduled:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if scheduled.status != "PENDING":
        raise HTTPException(status_code=400, detail="Tarefa não está pendente")

    from app.core.celery_app import celery_app
    celery_app.control.revoke(scheduled.task_id, terminate=True)
    scheduled.status = "CANCELLED"
    session.commit()
    return {"message": "Tarefa de sincronização cancelada com sucesso"}


@router.post("/scheduled-syncs/{sync_id}/run-now")
def run_scheduled_sync_now(sync_id: str, current_user: CurrentUserDep, session: DbSessionDep):
    scheduled = session.exec(
        select(ScheduledSync).where(ScheduledSync.id == sync_id)
    ).first()
    if not scheduled:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if scheduled.status != "PENDING":
        raise HTTPException(status_code=400, detail="Tarefa não está pendente")

    from app.core.celery_app import celery_app
    celery_app.control.revoke(scheduled.task_id, terminate=True)
    scheduled.status = "CANCELLED"

    task = sync_session_images.delay(scheduled.session_id, scheduled.ficha or "")

    session_rec = session.exec(
        select(SessionRecord).where(SessionRecord.session_id == scheduled.session_id)
    ).first()
    if session_rec and session_rec.status == "COMPLETED":
        session_rec.status = "SYNCING"
        session_rec.task_id = task.id

    session.commit()
    return {"message": "Coleta de imagens iniciada imediatamente"}


class SaveDraftRequest(BaseModel):
    summaryText: str


@router.put("/{session_id}/summary")
def save_draft_summary(session_id: str, data: SaveDraftRequest, current_user: CurrentUserDep, session: DbSessionDep):
    summary_rec = session.exec(select(Summary).where(Summary.session_id == session_id)).first()
    if not summary_rec:
        raise HTTPException(status_code=404, detail="Resumo não encontrado para esta sessão")
    summary_rec.edited_summary = data.summaryText
    session.commit()
    return {"message": "Rascunho do resumo salvo com sucesso"}


@router.get("/{session_id}/report-html", response_class=HTMLResponse)
def report_html(
    session_id: str,
    current_user: CurrentUserDep,
    session: DbSessionDep,
    public_only: bool = Query(default=False),
):
    session_rec = session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    summary_rec = session.exec(select(Summary).where(Summary.session_id == session_id)).first()
    summary_text = (summary_rec.edited_summary or summary_rec.original_summary or "") if summary_rec else ""

    if public_only and summary_text:
        counter = 0
        renumbered = []
        for ln in summary_text.split("\n"):
            if not ln.strip():
                continue
            if "— PÚBLICA —" in ln:
                counter += 1
                ln = re.sub(r'^\d+\.', f'{counter}.', ln, count=1)
                renumbered.append(ln)
        summary_text = "\n".join(renumbered)

    raw_content = _redis.get(f"raw_content:{session_id}")
    ficha = session_rec.ficha or session_id
    now_str = datetime.now(ZoneInfo("America/Cuiaba")).strftime("%d/%m/%Y %H:%M")

    # Dados estruturados do Center (enriquece o relatório)
    raw_center, center_error = _fetch_center_data(ficha)
    center_data = _format_center_data(raw_center)
    center_data.setdefault("numero_ficha", ficha)
    center_data.setdefault("data_emissao", now_str)

    center_notice_html = ""
    if center_error:
        center_notice_html = (
            '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;'
            'padding:10px 16px;margin-bottom:24px;font-size:13px;color:#856404;">'
            f'&#9888; Dados do Center n&atilde;o carregados &mdash; {escape(center_error)}'
            '</div>'
        )

    # Seção de análise IA (HTML puro, inserido sem escaping)
    ai_summary_html = ""
    if summary_text:
        lines_html = "".join(
            f'<p class="summary-line">{escape(ln.strip())}</p>'
            for ln in summary_text.strip().split("\n") if ln.strip()
        )
        if lines_html:
            ai_summary_html = (
                '<div class="section-title">An&aacute;lise do Atendimento (IA)</div>'
                f'<div class="text-box">{lines_html}</div>'
            )

    # Pasta do Drive
    drive_folder_html = ""
    drive_url = session_rec.drive_folder_url
    if drive_url and "mock" not in drive_url:
        drive_folder_html = (
            '<div class="data-row full-width">'
            '<span class="label">Registros Fotogr&aacute;ficos (Drive)</span>'
            f'<span class="value"><a href="{escape(drive_url)}" target="_blank" '
            f'style="color:#3b82f6;text-decoration:underline;">{escape(drive_url)}</a></span>'
            '</div>'
        )

    # Inserir seções raw e preencher campos de dados
    html_content = _REPORT_TEMPLATE.replace("__CENTER_NOTICE__", center_notice_html)
    html_content = html_content.replace("__DRIVE_FOLDER__", drive_folder_html)
    html_content = html_content.replace("__AI_SUMMARY__", ai_summary_html)
    html_content = html_content.replace("__TIMELINE__", "")
    html_content = _fill_template(html_content, center_data)

    return HTMLResponse(content=html_content)


@router.get("/{session_id}/debug-messages")
async def debug_messages(session_id: str, current_user: AdminUserDep):
    messages = await fetch_session_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Nenhuma mensagem encontrada")

    tz = ZoneInfo("America/Cuiaba")
    textos = []
    for msg in messages:
        if msg.get("type") != "TEXT" or not msg.get("text"):
            continue

        raw_ts = msg.get("createdAt") or msg.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            dt = dt.astimezone(tz)
            data_hora = dt.strftime("%d/%m/%Y, %H:%M:%S")
        except Exception:
            data_hora = raw_ts

        direction = msg.get("direction", "")
        if direction == "TO_HUB":
            quem = "operador"
        elif direction == "FROM_HUB":
            quem = "prestador"
        else:
            quem = "desconhecido"

        textos.append({
            "dataHora": data_hora,
            "quem": quem,
            "texto": msg.get("text", ""),
            "_raw_createdAt": raw_ts,
            "_raw_direction": direction,
        })

    texto_para_ia = "\n".join(
        f"[{m['dataHora']}] [{m['quem']}] {m['texto']}" for m in textos
    )

    return JSONResponse({
        "sessionId": session_id,
        "totalMensagens": len(messages),
        "totalMensagensTexto": len(textos),
        "mensagens": textos,
        "textoParaIA": texto_para_ia,
    })
