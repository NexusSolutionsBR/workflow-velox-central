"""
Script de debug para a integração com Google Drive (Service Account).

Faz as três operações usadas pelo pipeline:
  1. Carrega a Service Account e mostra o e-mail dela.
  2. find_or_create_folder("debug-<timestamp>") → cria/recupera a pasta.
  3. upload_file(...) com um arquivo de texto pequeno gerado na hora.

No final, imprime os IDs (folder_id, file_id) e a URL pra abrir no Drive.

Uso:
  docker compose exec backend python -m app.scripts.debug_gdrive
"""

import json
import os
import sys
import tempfile
import time

from app.core.config import settings
from app.services import gdrive


def main() -> int:
    sa_path = settings.GOOGLE_SERVICE_ACCOUNT_FILE
    root_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
    auth_method = gdrive._auth_method()

    print("═" * 60)
    print(f"Método de auth       : {auth_method}")
    print(f"Root folder ID       : {root_id}")
    print(f"Modo mock?           : {gdrive.is_mock}")
    print("═" * 60)

    if auth_method == "mock":
        print("\n[ERRO] Nenhum método de auth do Drive configurado.")
        print("OAuth: setar GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, "
              "GOOGLE_DRIVE_REFRESH_TOKEN no .env.")
        print("Service Account: setar GOOGLE_SERVICE_ACCOUNT_FILE com o caminho do JSON.")
        return 2

    if auth_method == "oauth-user":
        print(f"OAuth client_id      : {settings.GOOGLE_DRIVE_CLIENT_ID[:20]}...")
        print(f"Refresh token        : {settings.GOOGLE_DRIVE_REFRESH_TOKEN[:8]}...")
    else:  # service-account
        try:
            with open(sa_path, "r", encoding="utf-8") as f:
                sa_data = json.load(f)
            print(f"SA client_email      : {sa_data.get('client_email')}")
            print(f"SA project_id        : {sa_data.get('project_id')}")
            print(f"⚠️  Confirme que essa SA tem permissão de Editor na pasta {root_id!r}")
            print(f"⚠️  E que a pasta está num Drive Compartilhado (Workspace), "
                  f"senão upload falha com storageQuotaExceeded.")
        except Exception as e:
            print(f"[ERRO] Não consegui ler o JSON da SA: {e}")
            return 3

    # 1) find_or_create_folder
    folder_name = f"debug-{int(time.time())}"
    print(f"\n>>> find_or_create_folder({folder_name!r})")
    try:
        folder_id = gdrive.find_or_create_folder(folder_name)
    except Exception as e:
        print(f"[ERRO] {type(e).__name__}: {e}")
        print("Causas comuns: SA sem acesso à pasta raiz, ou root_id inválido.")
        return 4
    print(f"folder_id            : {folder_id}")
    print(f"abrir no Drive       : https://drive.google.com/drive/folders/{folder_id}")

    # 2) upload_file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(f"Debug upload — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        tmp_path = f.name

    print(f"\n>>> upload_file(folder_id, {tmp_path!r}, 'text/plain', 'debug.txt')")
    try:
        file_id = gdrive.upload_file(folder_id, tmp_path, "text/plain", "debug.txt")
    except Exception as e:
        print(f"[ERRO] {type(e).__name__}: {e}")
        return 5
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    print(f"file_id              : {file_id}")
    print(f"abrir arquivo        : https://drive.google.com/file/d/{file_id}/view")

    print("\n" + "═" * 60)
    print("OK — pasta e arquivo criados. Verifique no Drive antes de fechar.")
    print("(esse script não limpa nada, exclua manualmente quando quiser)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
