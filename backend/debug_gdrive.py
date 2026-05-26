"""
Script de debug do Google Drive — rode dentro do container backend:
  docker compose exec backend python debug_gdrive.py
"""

import os, sys, tempfile
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("DEBUG GOOGLE DRIVE")
print("=" * 60)

# ── 1. Variáveis de ambiente ─────────────────────────────────
sa_file    = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
root_id    = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")
client_id  = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
client_sec = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
refresh    = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")

print("\n[1] Variáveis de ambiente:")
print(f"  GOOGLE_SERVICE_ACCOUNT_FILE  = {sa_file!r}")
print(f"  GOOGLE_DRIVE_ROOT_FOLDER_ID  = {root_id!r}")
print(f"  GOOGLE_DRIVE_CLIENT_ID       = {'SET' if client_id else 'NÃO SET'}")
print(f"  GOOGLE_DRIVE_CLIENT_SECRET   = {'SET' if client_sec else 'NÃO SET'}")
print(f"  GOOGLE_DRIVE_REFRESH_TOKEN   = {'SET' if refresh else 'NÃO SET'}")

# ── 2. Existência do arquivo de service account ──────────────
print("\n[2] Arquivo service-account.json:")
if sa_file:
    if os.path.exists(sa_file):
        size = os.path.getsize(sa_file)
        print(f"  OK — encontrado em {sa_file!r} ({size} bytes)")
    else:
        print(f"  ERRO — arquivo NÃO encontrado em {sa_file!r}")
        print("  Dica: verifique se o arquivo está em backend/app/service-account.json")
else:
    print("  GOOGLE_SERVICE_ACCOUNT_FILE não definido")

# ── 3. Determinar método de auth ─────────────────────────────
print("\n[3] Método de autenticação:")
if client_id and client_sec and refresh:
    auth_method = "oauth-user"
elif sa_file and os.path.exists(sa_file):
    auth_method = "service-account"
else:
    auth_method = "mock"
print(f"  → {auth_method}")

if auth_method == "mock":
    print("  ATENÇÃO: nenhuma credencial válida — operando em modo mock.")
    print("  Nada será gravado no Google Drive de verdade.")
    sys.exit(0)

# ── 4. Importar dependências ─────────────────────────────────
print("\n[4] Importando bibliotecas Google:")
try:
    from google.oauth2.credentials import Credentials as UserCredentials
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    print("  OK")
except ImportError as e:
    print(f"  ERRO de import: {e}")
    sys.exit(1)

# ── 5. Obter credenciais ─────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/drive"]
print("\n[5] Criando credenciais:")
try:
    if auth_method == "oauth-user":
        creds = UserCredentials(
            token=None,
            refresh_token=refresh,
            client_id=client_id,
            client_secret=client_sec,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        print("  OAuth user credentials criadas")
    else:
        creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        print(f"  Service account carregado: {creds.service_account_email}")
except Exception as e:
    print(f"  ERRO: {e}")
    sys.exit(1)

# ── 6. Conectar à API ────────────────────────────────────────
print("\n[6] Conectando à Drive API v3:")
try:
    drive = build("drive", "v3", credentials=creds)
    about = drive.about().get(fields="user").execute()
    user = about.get("user", {})
    print(f"  Conectado como: {user.get('displayName', '?')} <{user.get('emailAddress', '?')}>")
except HttpError as e:
    print(f"  ERRO HTTP {e.status_code}: {e.error_details}")
    sys.exit(1)
except Exception as e:
    print(f"  ERRO: {e}")
    sys.exit(1)

# ── 7. Listar pasta raiz ─────────────────────────────────────
print(f"\n[7] Listando pasta raiz ({root_id}):")
try:
    res = drive.files().list(
        q=f"'{root_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    files = res.get("files", [])
    if files:
        for f in files:
            print(f"  - {f['name']} ({f['mimeType']}) id={f['id']}")
    else:
        print("  Pasta vazia (ou sem acesso ao conteúdo)")
except HttpError as e:
    print(f"  ERRO HTTP {e.status_code}: {e.error_details}")
except Exception as e:
    print(f"  ERRO: {e}")

# ── 8. Criar pasta de teste ──────────────────────────────────
print("\n[8] Criando pasta de teste 'debug-velox-test':")
folder_id = None
try:
    meta = {
        "name": "debug-velox-test",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [root_id],
    }
    folder = drive.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    folder_id = folder.get("id")
    print(f"  Pasta criada: id={folder_id}")
except HttpError as e:
    print(f"  ERRO HTTP {e.status_code}: {e.error_details}")
except Exception as e:
    print(f"  ERRO: {e}")

# ── 9. Upload de arquivo de teste ────────────────────────────
if folder_id:
    print("\n[9] Upload de arquivo de teste:")
    try:
        from googleapiclient.http import MediaFileUpload
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write("Arquivo de teste debug Velox\n")
            tmp_path = tmp.name

        file_meta = {"name": "debug-test.txt", "parents": [folder_id]}
        media = MediaFileUpload(tmp_path, mimetype="text/plain")
        uploaded = drive.files().create(
            body=file_meta, media_body=media, fields="id", supportsAllDrives=True
        ).execute()
        print(f"  Upload OK: id={uploaded.get('id')}")
        os.unlink(tmp_path)
    except HttpError as e:
        print(f"  ERRO HTTP {e.status_code}: {e.error_details}")
    except Exception as e:
        print(f"  ERRO: {e}")

    # ── 10. Limpar pasta de teste ────────────────────────────
    print("\n[10] Removendo pasta de teste:")
    try:
        drive.files().delete(fileId=folder_id, supportsAllDrives=True).execute()
        print("  Pasta removida com sucesso")
    except Exception as e:
        print(f"  Não foi possível remover: {e} (remova manualmente se necessário)")

print("\n" + "=" * 60)
print("DEBUG CONCLUÍDO")
print("=" * 60)
