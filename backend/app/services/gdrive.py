"""
Integração Google Drive — suporta dois métodos de auth, nessa ordem:

1. OAuth user (refresh token) — recomendado. Funciona com qualquer conta Google
   pessoal. Setar GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET e
   GOOGLE_DRIVE_REFRESH_TOKEN no .env (gerados via `oauth_setup.py`).

2. Service Account (legado) — só funciona se a pasta raiz estiver num Drive
   Compartilhado (Google Workspace). Em conta pessoal, upload retorna
   `storageQuotaExceeded`.

Se nenhum dos dois estiver configurado, opera em modo mock.
"""

import os
import time
import random
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_credentials():
    """Retorna credenciais OAuth user, ou de Service Account, ou None (mock)."""
    if (
        settings.GOOGLE_DRIVE_CLIENT_ID
        and settings.GOOGLE_DRIVE_CLIENT_SECRET
        and settings.GOOGLE_DRIVE_REFRESH_TOKEN
    ):
        return UserCredentials(
            token=None,
            refresh_token=settings.GOOGLE_DRIVE_REFRESH_TOKEN,
            client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
            client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE
    ):
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
    return None


def _auth_method() -> str:
    """Identifica qual método de auth está ativo (útil pra logs/debug)."""
    if (
        settings.GOOGLE_DRIVE_CLIENT_ID
        and settings.GOOGLE_DRIVE_CLIENT_SECRET
        and settings.GOOGLE_DRIVE_REFRESH_TOKEN
    ):
        return "oauth-user"
    if settings.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE
    ):
        return "service-account"
    return "mock"


is_mock = _get_credentials() is None


def get_drive_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


def find_or_create_folder(folder_name: str) -> str:
    """Busca ou cria uma pasta com o número da ficha no Google Drive.
    Os flags `supportsAllDrives` e `includeItemsFromAllDrives` são necessários
    pra funcionar com Drives Compartilhados (Workspace)."""
    drive_service = get_drive_service()
    if not drive_service:
        print(f"[GDrive Mock] Pasta simulada para ficha: {folder_name}")
        return f"mock-folder-id-{folder_name}"

    root_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID

    query = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name}' "
        f"and '{root_id}' in parents "
        f"and trashed=false"
    )
    results = (
        drive_service.files()
        .list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        )
        .execute()
    )
    files = results.get("files", [])

    if files:
        return files[0].get("id")

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [root_id],
    }
    file = (
        drive_service.files()
        .create(body=file_metadata, fields="id", supportsAllDrives=True)
        .execute()
    )
    return file.get("id")


def upload_file(folder_id: str, file_path: str, mime_type: str, original_name: str) -> str:
    """Faz upload de um arquivo para a pasta da ficha no Google Drive.
    Retenta automaticamente em caso de rate limit (429) ou erro temporário (500/503)
    com backoff exponencial + jitter."""
    drive_service = get_drive_service()
    if not drive_service:
        print(f"[GDrive Mock] Upload simulado: {original_name}")
        return f"mock-file-id-{os.path.basename(file_path)}"

    file_metadata = {"name": original_name, "parents": [folder_id]}
    max_retries = 5

    for attempt in range(max_retries):
        try:
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=False)
            file = (
                drive_service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return file.get("id")
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"[GDrive] Erro {e.resp.status} em '{original_name}', tentativa {attempt + 1}/{max_retries} — aguardando {wait:.1f}s")
                time.sleep(wait)
            else:
                print(f"[GDrive] Falha definitiva em '{original_name}': {e}")
                raise
