"""
Celery Worker Tasks — Pipeline de processamento de sessões.

Tasks disponíveis:
  process_session      — Busca mensagens, transcreve áudios, faz upload de imagens
  summarize_session    — Gera resumo via agentes de IA (acionado manualmente)
  sync_session_images  — Re-busca mensagens e envia imagens novas ao Drive
"""

import os
import re
import httpx
import redis as redis_lib
from collections import deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlmodel import Session, select
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import engine
from app.models.domain import SessionRecord, MediaFile, Summary, ScheduledSync
from app.services.velox import fetch_session_messages
from app.services.gdrive import find_or_create_folder, upload_file
from app.services.center_service import (
    get_existing_occurrences as center_get_existing,
    find_description_duplicates,
    parse_summary_to_occurrences,
    insert_occurrence as center_insert_occurrence,
)
from app.agents import transcribe_audio, generate_summary
import asyncio

_redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
_LOG_TTL = 86400       # logs: 24h
_CONTENT_TTL = 604800  # raw_content: 7 dias


def _log(session_id: str, message: str):
    print(message)
    try:
        key = f"pipeline_logs:{session_id}"
        _redis.rpush(key, message)
        _redis.expire(key, _LOG_TTL)
    except Exception:
        pass


def _is_cancelled(session_id: str) -> bool:
    with Session(engine) as s:
        rec = s.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
        return rec is not None and rec.status == "CANCELLED"


def _set_status(session_id: str, status: str):
    with Session(engine) as s:
        rec = s.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
        if rec:
            rec.status = status
            s.commit()


async def _download_file(url: str, dest_path: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        return True
    except Exception as e:
        print(f"[Download] Falha ao baixar {url}: {e}")
        return False


async def _upload_images_from_messages(session_id: str, ficha: str, messages: list):
    """Faz upload das imagens ainda não enviadas, com filtro de intervalo.
    Permite até GDRIVE_IMAGE_MAX_PER_INTERVAL imagens a cada GDRIVE_IMAGE_INTERVAL_MINUTES minutos.
    Renomeia cada arquivo para YYYYMMDD_HHMMSS_FICHA_NNN.ext para organização no Drive."""
    tmp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tmp"))
    os.makedirs(tmp_dir, exist_ok=True)

    folder_id = find_or_create_folder(ficha)
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    with Session(engine) as db_session:
        rec = db_session.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
        if rec:
            rec.drive_folder_url = folder_url
            db_session.commit()
    total_images = sum(1 for m in messages if m.get("type") == "IMAGE")

    interval_secs = settings.GDRIVE_IMAGE_INTERVAL_MINUTES * 60
    max_per_interval = settings.GDRIVE_IMAGE_MAX_PER_INTERVAL
    upload_window: deque = deque(maxlen=max_per_interval)

    safe_ficha = re.sub(r"[^\w]", "", ficha or "semficha")

    image_idx = 0
    uploaded = 0
    skipped_interval = 0

    with Session(engine) as db_session:
        for i, msg in enumerate(messages, 1):
            if msg.get("type") != "IMAGE":
                continue
            file_info = msg.get("details", {}).get("file")
            if not file_info or not file_info.get("publicUrlDownload"):
                continue

            image_idx += 1
            file_id = file_info.get("id")
            ext = file_info.get("extension", ".jpg")
            created_at = msg.get("createdAt") or msg.get("timestamp", "")

            try:
                img_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if img_dt.tzinfo is None:
                    img_dt = img_dt.replace(tzinfo=ZoneInfo("UTC"))
                img_dt_local = img_dt.astimezone(ZoneInfo("America/Sao_Paulo"))
            except Exception:
                img_dt = None
                img_dt_local = None

            # Verifica se já foi enviada
            existing = db_session.exec(
                select(MediaFile).where(MediaFile.file_id == file_id)
            ).first()
            if existing:
                _log(session_id, f"[Imagens] {image_idx}/{total_images}: já enviada, pulando")
                continue

            # Filtro de intervalo — janela deslizante
            if img_dt and len(upload_window) >= max_per_interval:
                delta = (img_dt - upload_window[0]).total_seconds()
                if delta < interval_secs:
                    skipped_interval += 1
                    _log(session_id,
                         f"[Imagens] {image_idx}/{total_images}: fora da janela de {settings.GDRIVE_IMAGE_INTERVAL_MINUTES}min, pulando")
                    continue

            # Nome organizado com data de envio
            if img_dt_local:
                drive_name = f"{img_dt_local.strftime('%Y%m%d_%H%M%S')}_{safe_ficha}_{image_idx:03d}{ext}"
            else:
                drive_name = file_info.get("name", f"{file_id}{ext}")

            dest_path = os.path.join(tmp_dir, f"{file_id}{ext}")
            _log(session_id, f"[Imagens] {image_idx}/{total_images}: baixando → {drive_name}")

            if await _download_file(file_info["publicUrlDownload"], dest_path):
                mime_type = file_info.get("mimeType", "image/jpeg")
                _log(session_id, f"[Imagens] {image_idx}/{total_images}: subindo ao Drive ({drive_name})")
                drive_id = upload_file(folder_id, dest_path, mime_type, drive_name)
                db_session.add(MediaFile(
                    session_id=session_id,
                    file_id=file_id,
                    type="IMAGE",
                    url=drive_id,
                    status="UPLOADED" if drive_id else "FAILED",
                ))
                db_session.commit()
                if drive_id:
                    upload_window.append(img_dt)
                    uploaded += 1
                _log(session_id, f"[Imagens] {image_idx}/{total_images}: OK (drive_id={drive_id})")
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            else:
                _log(session_id, f"[Imagens] {image_idx}/{total_images}: FALHA no download")

    resumo = f"[Imagens] Concluído: {uploaded} enviadas, {total_images - uploaded - skipped_interval} já existiam"
    if skipped_interval:
        resumo += f", {skipped_interval} fora do intervalo de {settings.GDRIVE_IMAGE_INTERVAL_MINUTES}min"
    _log(session_id, resumo)


# ══════════════════════════════════════════════════════════════
# TASK 1 — Processar sessão (busca + mídias, sem IA)
# ══════════════════════════════════════════════════════════════

@celery_app.task(name="app.services.tasks.process_session")
def process_session(session_id: str, ficha: str, do_transcribe: bool = True, do_upload_images: bool = True, do_summary: bool = False, do_insert_center: bool = False):
    asyncio.run(_async_process_session(session_id, ficha, do_transcribe, do_upload_images, do_summary, do_insert_center))


async def _async_process_session(session_id: str, ficha: str, do_transcribe: bool, do_upload_images: bool, do_summary: bool, do_insert_center: bool = False):
    _log(session_id, f"[Pipeline] Iniciando para sessionId={session_id}, ficha={ficha}")
    _log(session_id, f"[Pipeline] Opções: transcrever={do_transcribe}, imagens={do_upload_images}, resumo={do_summary}, center={do_insert_center}")

    try:
        _log(session_id, "[Pipeline] [1/3] Buscando mensagens do Velox...")
        messages = await fetch_session_messages(session_id)
        if not messages:
            raise Exception("Nenhuma mensagem encontrada para o sessionId informado")

        # Garante que as mensagens estejam em ordem cronológica (mais antigas primeiro)
        messages.sort(key=lambda x: x.get("createdAt", ""))

        total_msgs = len(messages)
        total_audios = sum(1 for m in messages if m.get("type") == "AUDIO")
        total_images = sum(1 for m in messages if m.get("type") == "IMAGE")
        total_texts = sum(1 for m in messages if m.get("type") == "TEXT")
        _log(session_id,
             f"[Pipeline] {total_msgs} mensagens — "
             f"texto: {total_texts}, áudio: {total_audios}, imagem: {total_images}")
        if messages:
            _log(session_id, f"[Pipeline] Debug createdAt: {messages[0].get('createdAt', 'N/A')!r}")

        if _is_cancelled(session_id):
            return

        tmp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../tmp"))
        os.makedirs(tmp_dir, exist_ok=True)

        chronological_content = ""
        ai_content = ""
        audio_idx = 0

        # Determinar índice da última mensagem do bot (origin=BOT)
        last_bot_idx = -1
        for idx, m in enumerate(messages):
            if (m.get("origin") or "").upper() == "BOT":
                last_bot_idx = idx

        if last_bot_idx >= 0:
            _log(session_id,
                 f"[Pipeline] Filtro BOT: {last_bot_idx + 1} mensagem(ns) do bot detectadas — "
                 f"análise da IA iniciará a partir da msg {last_bot_idx + 2}/{total_msgs}")
        else:
            _log(session_id, "[Pipeline] Nenhuma mensagem de bot detectada — IA analisará a timeline completa")

        _log(session_id, "[Pipeline] [2/3] Processando mídias...")

        with Session(engine) as db_session:
            for i, msg in enumerate(messages, 1):
                if i % 20 == 0 and _is_cancelled(session_id):
                    _log(session_id, "[Pipeline] Cancelado pelo usuário.")
                    return

                msg_type = msg.get("type")
                file_info = msg.get("details", {}).get("file")
                created_at = msg.get("createdAt") or msg.get("timestamp", "")

                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    dt = dt.astimezone(ZoneInfo("America/Sao_Paulo"))
                    dt_str = dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    dt_str = created_at or "??"

                direction = msg.get("direction", "")
                if direction == "TO_HUB":
                    quem = "operador"
                elif direction == "FROM_HUB":
                    quem = "prestador"
                else:
                    quem = ""

                quem_prefix = f"[{quem}] " if quem else ""
                msg_text = ""

                if msg_type == "TEXT":
                    msg_text = f"[{dt_str}] {quem_prefix}{msg.get('text', '')}"

                elif msg_type == "AUDIO" and file_info and file_info.get("publicUrlDownload"):
                    audio_idx += 1
                    ext = file_info.get("extension", ".mp3")
                    file_id = file_info.get("id", "audio")
                    dest_path = os.path.join(tmp_dir, f"{file_id}{ext}")

                    if do_transcribe:
                        _log(session_id,
                             f"[Pipeline] msg {i}/{total_msgs} — "
                             f"áudio {audio_idx}/{total_audios}: baixando")
                        if await _download_file(file_info["publicUrlDownload"], dest_path):
                            transcription = transcribe_audio(dest_path)
                            msg_text = f"[{dt_str}] {quem_prefix}ÁUDIO (Transcrito): {transcription}"
                            _log(session_id,
                                 f"[Pipeline] msg {i}/{total_msgs} — "
                                 f"áudio {audio_idx}/{total_audios}: OK ({len(transcription)} chars)")
                            try:
                                os.remove(dest_path)
                            except OSError:
                                pass
                        else:
                            msg_text = f"[{dt_str}] {quem_prefix}ÁUDIO: (Falha ao baixar)"
                            _log(session_id,
                                 f"[Pipeline] msg {i}/{total_msgs} — "
                                 f"áudio {audio_idx}/{total_audios}: FALHA no download")
                    else:
                        msg_text = f"[{dt_str}] {quem_prefix}ÁUDIO: (transcrição desativada)"

                elif msg_type == "IMAGE" and file_info:
                    msg_text = f"[{dt_str}] IMAGEM: {file_info.get('name', file_info.get('id', ''))}"

                elif msg_type == "VIDEO":
                    name = file_info.get("name", "video") if file_info else ""
                    msg_text = f"[{dt_str}] VÍDEO: {name}"

                elif msg_type == "LOCATION":
                    loc = (msg.get("details") or {}).get("location") or {}
                    lat = loc.get("latitude")
                    lng = loc.get("longitude")
                    if lat is not None and lng is not None:
                        maps_url = f"https://www.google.com/maps?q={lat},{lng}"
                        addr = loc.get("address") or loc.get("name") or ""
                        addr_part = f" ({addr})" if addr else ""
                        msg_text = f"[{dt_str}] {quem_prefix}LOCALIZAÇÃO{addr_part}: {lat}, {lng} → {maps_url}"
                    else:
                        msg_text = f"[{dt_str}] {quem_prefix}LOCALIZAÇÃO: (coordenadas não disponíveis)"

                else:
                    msg_text = f"[{dt_str}] {quem_prefix}{msg_type}: {msg.get('text', '')}"

                if msg_text:
                    chronological_content += msg_text + "\n\n"
                    if (i - 1) > last_bot_idx:
                        ai_content += msg_text + "\n\n"

            # ── Salvar conteúdo bruto no Redis e no banco ──────────────
            _log(session_id, f"[Pipeline] [3/3] Timeline montada ({len(chronological_content)} chars) — salvando")
            try:
                _redis.set(f"raw_content:{session_id}", chronological_content, ex=_CONTENT_TTL)
                if ai_content:
                    _redis.set(f"ai_content:{session_id}", ai_content, ex=_CONTENT_TTL)
                    _log(session_id,
                         f"[Pipeline] Conteúdo para IA: {len(ai_content)} chars "
                         f"(pós-bot, {len(ai_content.strip().splitlines())} linhas)")
            except Exception as e:
                _log(session_id, f"[Pipeline] Aviso: não foi possível salvar raw_content no Redis: {e}")

            # Extrai nome do contato (primeiro FROM_HUB com nome identificável)
            contact_name = None
            for m in messages:
                if m.get("direction") == "FROM_HUB":
                    contact_name = (
                        m.get("senderName")
                        or m.get("contactName")
                        or (m.get("contact") or {}).get("name")
                        or (m.get("sender") or {}).get("name")
                    )
                    if contact_name:
                        break

            # Persiste raw_content e contact_name no banco (permanente)
            with Session(engine) as db_session:
                rec = db_session.exec(
                    select(SessionRecord).where(SessionRecord.session_id == session_id)
                ).first()
                if rec:
                    rec.raw_content = chronological_content
                    if contact_name:
                        rec.contact_name = contact_name
                    db_session.commit()

        # ── Resumo automático (opcional) — roda ANTES de marcar COMPLETED ──
        if do_summary:
            _log(session_id, "[Pipeline] Gerando resumo com IA...")
            try:
                content_for_summary = ai_content if ai_content else chronological_content
                summary_text = generate_summary(content_for_summary)
                with Session(engine) as db_session:
                    existing = db_session.exec(
                        select(Summary).where(Summary.session_id == session_id)
                    ).first()
                    if existing:
                        existing.original_summary = summary_text
                        existing.edited_summary = summary_text
                    else:
                        db_session.add(Summary(
                            session_id=session_id,
                            original_summary=summary_text,
                            edited_summary=summary_text,
                        ))
                    db_session.commit()
                _log(session_id, f"[Pipeline] Resumo gerado ({len(summary_text)} chars)")
            except Exception as e:
                _log(session_id, f"[Pipeline] Erro ao gerar resumo: {e}")

        # ── Inserção no Center (opcional) ──────────────────────────
        if do_insert_center and not _is_cancelled(session_id):
            _set_status(session_id, "INSERTING")
            _log(session_id, "[Center] Verificando ocorrências existentes na ficha...")
            try:
                summary_text_for_center = ""
                with Session(engine) as db_session:
                    sum_rec = db_session.exec(
                        select(Summary).where(Summary.session_id == session_id)
                    ).first()
                    if sum_rec:
                        summary_text_for_center = sum_rec.edited_summary or sum_rec.original_summary or ""

                drive_folder_url = ""
                with Session(engine) as db_session:
                    sess_rec = db_session.exec(
                        select(SessionRecord).where(SessionRecord.session_id == session_id)
                    ).first()
                    if sess_rec:
                        drive_folder_url = sess_rec.drive_folder_url or ""

                to_insert = parse_summary_to_occurrences(summary_text_for_center)
                if drive_folder_url:
                    to_insert.append({"descricao": f"LINK GOOGLE DRIVE: {drive_folder_url}"})

                existing = await center_get_existing(ficha)
                duplicates = find_description_duplicates(existing, to_insert)

                if duplicates:
                    _log(session_id, f"[Center] {len(duplicates)} descrição(ões) já cadastrada(s) na ficha — serão ignoradas pelo Center.")

                total_ocorrencias = len(to_insert)
                if drive_folder_url:
                    _log(session_id, f"[Center] Inserindo {total_ocorrencias} ocorrência(s) + link do Google Drive...")
                else:
                    _log(session_id, f"[Center] Inserindo {total_ocorrencias} ocorrência(s)...")
                result = await center_insert_occurrence(session_id, ficha, summary_text_for_center, drive_folder_url)
                total_inserido = result.get("total_inserido", 0) if isinstance(result, dict) else 0
                total_ignorado = result.get("total_ignoradas_por_duplicidade", 0) if isinstance(result, dict) else 0

                with Session(engine) as db_session:
                    rec = db_session.exec(
                        select(SessionRecord).where(SessionRecord.session_id == session_id)
                    ).first()
                    if rec:
                        rec.center_inserted = total_inserido > 0
                        rec.center_duplicate = total_inserido == 0 and total_ignorado > 0
                        db_session.commit()

                if total_inserido > 0:
                    _log(session_id, f"[Center] {total_inserido} ocorrência(s) inserida(s) com sucesso!")
                if total_ignorado > 0:
                    _log(session_id, f"[Center] {total_ignorado} ocorrência(s) ignorada(s) por duplicidade.")
                if total_inserido == 0 and total_ignorado == 0:
                    _log(session_id, "[Center] Nenhuma ocorrência inserida.")
            except Exception as e:
                _log(session_id, f"[Center] ERRO ao inserir: {e}")

        with Session(engine) as db_session:
            session_rec = db_session.exec(
                select(SessionRecord).where(SessionRecord.session_id == session_id)
            ).first()
            if session_rec and session_rec.status != "CANCELLED":
                session_rec.status = "COMPLETED"
            db_session.commit()

        if not do_summary and not do_insert_center:
            _log(session_id, "[Pipeline] Concluído! Use o botão 'Resumir Relatório' para gerar o resumo com IA.")
        else:
            _log(session_id, "[Pipeline] Concluído!")

        # Upload de imagens (roda após marcar COMPLETED para não bloquear o status)
        if do_upload_images:
            _log(session_id, "[Pipeline] Iniciando upload de imagens ao Drive...")
            await _upload_images_from_messages(session_id, ficha, messages)

            # Cancelar syncs pendentes anteriores para esta sessão (evitar duplicatas)
            with Session(engine) as db_session:
                existing_pending = db_session.exec(
                    select(ScheduledSync)
                    .where(ScheduledSync.session_id == session_id)
                    .where(ScheduledSync.status == "PENDING")
                ).all()
                for s in existing_pending:
                    try:
                        celery_app.control.revoke(s.task_id, terminate=True)
                    except Exception:
                        pass
                    s.status = "CANCELLED"
                db_session.commit()

            # Agendar re-checagem automática após AUTO_SYNC_DELAY_SECONDS
            delay = settings.AUTO_SYNC_DELAY_SECONDS
            run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            scheduled_task = sync_session_images.apply_async(
                args=[session_id, ficha],
                countdown=delay,
            )
            with Session(engine) as db_session:
                db_session.add(ScheduledSync(
                    session_id=session_id,
                    ficha=ficha,
                    contact_name=contact_name,
                    task_id=scheduled_task.id,
                    run_at=run_at,
                    status="PENDING",
                ))
                db_session.commit()
            _log(session_id,
                 f"[Pipeline] Sincronização automática agendada para "
                 f"{run_at.strftime('%d/%m/%Y %H:%M:%S')} UTC ({delay}s)")

    except Exception as e:
        _log(session_id, f"[Pipeline] ERRO: {e}")
        with Session(engine) as s:
            rec = s.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
            if rec and rec.status != "CANCELLED":
                rec.status = "ERROR"
                rec.error_message = str(e)
                s.commit()


# ══════════════════════════════════════════════════════════════
# TASK 2 — Gerar resumo com IA (acionado manualmente)
# ══════════════════════════════════════════════════════════════

@celery_app.task(name="app.services.tasks.summarize_session")
def summarize_session(session_id: str):
    _log(session_id, "[Resumo] Iniciando geração de resumo com IA...")
    try:
        ai_content = _redis.get(f"ai_content:{session_id}")
        raw_content = _redis.get(f"raw_content:{session_id}")
        if not raw_content:
            with Session(engine) as db_s:
                rec = db_s.exec(select(SessionRecord).where(SessionRecord.session_id == session_id)).first()
                if rec:
                    raw_content = rec.raw_content
        content_for_ai = ai_content or raw_content
        if not content_for_ai:
            raise Exception("Conteúdo bruto não encontrado. Execute o pipeline completo primeiro.")

        if ai_content:
            _log(session_id,
                 f"[Resumo] Usando conteúdo pós-bot ({len(ai_content)} chars) — enviando para os agentes")
        else:
            _log(session_id,
                 f"[Resumo] Conteúdo carregado ({len(raw_content)} chars) — enviando para os agentes")
        summary_text = generate_summary(content_for_ai)
        _log(session_id, f"[Resumo] Gerado com sucesso ({len(summary_text)} chars)")

        with Session(engine) as db_session:
            existing = db_session.exec(
                select(Summary).where(Summary.session_id == session_id)
            ).first()
            if existing:
                existing.original_summary = summary_text
                existing.edited_summary = summary_text
            else:
                db_session.add(Summary(
                    session_id=session_id,
                    original_summary=summary_text,
                    edited_summary=summary_text,
                ))
            rec = db_session.exec(
                select(SessionRecord).where(SessionRecord.session_id == session_id)
            ).first()
            if rec:
                rec.status = "COMPLETED"
            db_session.commit()

        _log(session_id, "[Resumo] Concluído!")

    except Exception as e:
        _log(session_id, f"[Resumo] ERRO: {e}")
        _set_status(session_id, "COMPLETED")  # volta pra COMPLETED pra não travar a UI


# ══════════════════════════════════════════════════════════════
# TASK 3 — Sincronizar novas imagens (acionado manualmente)
# ══════════════════════════════════════════════════════════════

@celery_app.task(name="app.services.tasks.sync_session_images")
def sync_session_images(session_id: str, ficha: str):
    asyncio.run(_async_sync_images(session_id, ficha))


async def _async_sync_images(session_id: str, ficha: str):
    _log(session_id, "[Sync] Buscando mensagens atualizadas da sessão...")
    sync_ok = False
    error_text = None
    try:
        messages = await fetch_session_messages(session_id)
        if not messages:
            _log(session_id, "[Sync] Nenhuma mensagem encontrada.")
            sync_ok = True
            return

        total_images = sum(1 for m in messages if m.get("type") == "IMAGE")
        _log(session_id, f"[Sync] {len(messages)} mensagens — {total_images} imagens encontradas")
        await _upload_images_from_messages(session_id, ficha, messages)
        sync_ok = True

    except Exception as e:
        error_text = str(e)
        _log(session_id, f"[Sync] ERRO: {e}")
    finally:
        # Sessão volta para COMPLETED independente do resultado do sync
        # (dados do atendimento estão íntegros; só o upload de imagens falhou)
        _set_status(session_id, "COMPLETED")
        scheduled_status = "COMPLETED" if sync_ok else "FAILED"
        with Session(engine) as db_session:
            pending = db_session.exec(
                select(ScheduledSync)
                .where(ScheduledSync.session_id == session_id)
                .where(ScheduledSync.status == "PENDING")
            ).all()
            for s in pending:
                s.status = scheduled_status
                # Persiste o motivo da falha — logs do Redis expiram em 24h
                s.error_message = error_text if not sync_ok else None
            db_session.commit()
        if not sync_ok:
            _log(session_id, "[Sync] Sincronização falhou — verifique os logs acima. A sessão foi mantida como COMPLETED.")
