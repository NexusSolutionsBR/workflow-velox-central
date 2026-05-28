import re
import json
import httpx
from datetime import datetime
from app.core.config import settings

# Formato do relatório: "N. DD/MM/YYYY, HH:MM:SS — TIPO — DESCRIÇÃO"
_LINE_PATTERN = re.compile(
    r'^\d+\.\s+(\d{2}/\d{2}/\d{4}),\s+(\d{2}:\d{2}:\d{2})\s+—\s+(PÚBLICA|INTERNA)\s+—\s+(.+)$',
    re.MULTILINE,
)


def parse_summary_to_occurrences(summary_text: str) -> list[dict]:
    """Converte cada linha do relatório em uma entrada de ocorrência para o Center."""
    occurrencias = []
    for match in _LINE_PATTERN.finditer(summary_text):
        date_str, time_str, tipo, desc = match.groups()
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")
        except ValueError:
            continue
        occurrencias.append({
            "datahora": dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "tipo": tipo,
            "descricao": desc.strip(),
        })
    return occurrencias


def _base_params(identificador: str, ficha: str) -> dict:
    params = {
        "acao": "resultado",
        "identificador": identificador,
        "fichaparametro": ficha,
    }
    if settings.CENTER_USUARIO_PARAMETRO:
        params["usuarioparametro"] = settings.CENTER_USUARIO_PARAMETRO
    return params


async def get_existing_occurrences(ficha: str) -> list[dict]:
    """Retorna lista de ocorrências não-automáticas já cadastradas na ficha no Center."""
    identificador = settings.CENTER_IDENTIFICADOR_OCORRENCIAS
    if not identificador:
        return []  # modo mock: sem ocorrências existentes

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(
            settings.CENTER_CONSULTA_URL,
            params=_base_params(identificador, ficha),
        )
        if not res.is_success:
            try:
                detail = res.json()
            except Exception:
                detail = res.text
            raise Exception(f"Erro {res.status_code} do Center: {detail}")
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, list):
            return [o for o in data if (o.get("tipo") or "").upper() != "AUTOMÁTICO"]
        if isinstance(data, dict) and data:
            if (o := data) and (o.get("tipo") or "").upper() != "AUTOMÁTICO":
                return [o]
        return []


def find_description_duplicates(existing: list[dict], to_insert: list[dict]) -> list[str]:
    """Retorna descrições que já existem no Center (comparação case-insensitive, sem espaços extras)."""
    existing_descs = {(o.get("descricao") or "").strip().upper() for o in existing}
    return [
        o["descricao"] for o in to_insert
        if o["descricao"].strip().upper() in existing_descs
    ]


async def insert_occurrence(session_id: str, ficha: str, summary_text: str = "", drive_folder_url: str = "") -> dict:
    """Insere ocorrências no Center convertendo cada linha do relatório."""
    occurrencias = parse_summary_to_occurrences(summary_text)

    if drive_folder_url:
        occurrencias.append({
            "datahora": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "tipo": "PÚBLICA",
            "descricao": f"LINK GOOGLE DRIVE: {drive_folder_url}",
        })

    identificador = settings.CENTER_IDENTIFICADOR_INSERCAO

    if not identificador:
        print(f"[Center Mock] Inserindo {len(occurrencias)} ocorrência(s) — ficha={ficha}, sessionId={session_id}")
        return {"mock": True, "total": len(occurrencias)}

    if not occurrencias:
        raise Exception(
            "Nenhuma ocorrência extraída do resumo — verifique se o relatório foi gerado antes de inserir no Center"
        )

    form_data = _base_params(identificador, ficha)
    form_data["ocorrenciasparametro"] = json.dumps(occurrencias, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            settings.CENTER_CONSULTA_URL,
            data=form_data,
        )
        if not res.is_success:
            try:
                detail = res.json()
            except Exception:
                detail = res.text
            raise Exception(f"Erro {res.status_code} do Center: {detail}")
        result = res.json() or {}
        return result or {}
