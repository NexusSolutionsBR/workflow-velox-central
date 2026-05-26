"""
Gera o GOOGLE_DRIVE_REFRESH_TOKEN via fluxo OAuth manual.

Não precisa de DNS público nem expor portas do container — funciona com
"copy/paste" do código retornado pelo Google. Você roda o script, abre a URL
no seu browser, autoriza, e cola a URL final (ou só o `code=`) de volta no
terminal.

Pré-requisito:
  - Credencial OAuth tipo "Desktop app" criada no Google Cloud Console
  - client_id e client_secret em mãos (ou já no .env)

Uso:
  # passando como argumentos
  docker compose exec backend python -m app.scripts.oauth_setup \\
      --client-id 123.apps.googleusercontent.com --client-secret GOCSPX-...

  # ou lendo do .env (GOOGLE_DRIVE_CLIENT_ID / GOOGLE_DRIVE_CLIENT_SECRET)
  docker compose exec backend python -m app.scripts.oauth_setup
"""

import argparse
import sys
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import Flow
from app.core.config import settings


SCOPES = ["https://www.googleapis.com/auth/drive"]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # fluxo "OOB" — sem servidor local


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera refresh token do Google Drive (OAuth)")
    parser.add_argument("--client-id", default=settings.GOOGLE_DRIVE_CLIENT_ID)
    parser.add_argument("--client-secret", default=settings.GOOGLE_DRIVE_CLIENT_SECRET)
    args = parser.parse_args()

    if not args.client_id or not args.client_secret:
        print("[ERRO] client_id ou client_secret não fornecidos.")
        print("Passe via --client-id / --client-secret ou setando")
        print("GOOGLE_DRIVE_CLIENT_ID e GOOGLE_DRIVE_CLIENT_SECRET no .env.")
        return 2

    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI, "http://localhost"],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",       # garante refresh_token na resposta
        prompt="consent",            # força consent → refresh_token sempre vem
        include_granted_scopes="true",
    )

    print("═" * 70)
    print("PASSO 1 — Abra esta URL no seu navegador (no host, não no container):")
    print("═" * 70)
    print()
    print(auth_url)
    print()
    print("═" * 70)
    print("PASSO 2 — Faça login com a conta Google que vai 'dona' dos arquivos")
    print("          e clique em 'Permitir' em todas as telas.")
    print()
    print("PASSO 3 — Ao final o Google vai mostrar uma página com um código longo")
    print("          (algo tipo 4/0AeanS...). Copie esse código e cole abaixo.")
    print()
    print("          ⚠️ Se em vez de mostrar um código o navegador redirecionar")
    print("             para uma URL `http://localhost/?code=...`, copie a URL")
    print("             inteira da barra de endereço (vai falhar carregar — é OK).")
    print("═" * 70)
    print()

    user_input = input("Código (ou URL completa): ").strip()
    if not user_input:
        print("[ERRO] entrada vazia.")
        return 3

    if user_input.startswith("http"):
        parsed = parse_qs(urlparse(user_input).query)
        code = parsed.get("code", [None])[0]
        if not code:
            print("[ERRO] não achei o parâmetro `code` na URL.")
            return 4
    else:
        code = user_input

    print("\n>>> Trocando o code por tokens...")
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        print(f"[ERRO] {type(e).__name__}: {e}")
        return 5

    creds = flow.credentials
    if not creds.refresh_token:
        print("[ERRO] Google não retornou refresh_token. Causas comuns:")
        print("  - Conta já tinha autorizado antes (revogue em")
        print("    https://myaccount.google.com/permissions e tente de novo)")
        print("  - Faltou prompt=consent (esse script já manda)")
        return 6

    print()
    print("═" * 70)
    print("✅ SUCESSO — Adicione estas linhas no seu .env:")
    print("═" * 70)
    print()
    print(f"GOOGLE_DRIVE_CLIENT_ID={args.client_id}")
    print(f"GOOGLE_DRIVE_CLIENT_SECRET={args.client_secret}")
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print("═" * 70)
    print("Depois rode: docker compose up -d --force-recreate backend celery_worker")
    print("E valide com: docker compose exec backend python -m app.scripts.debug_gdrive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
