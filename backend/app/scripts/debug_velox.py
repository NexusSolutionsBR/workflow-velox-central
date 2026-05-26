"""
Script de debug para a API do Velox/Helena.

Faz uma única chamada (síncrona) usando exatamente a mesma URL, headers e
parâmetros que `app/services/velox.py` usaria, e imprime:
  - URL final + status code
  - headers da resposta
  - tamanho do payload
  - shape detectado (lista crua, dict com `items`, etc.)
  - primeira mensagem (se houver) com chaves de topo
  - se há próximo cursor

Uso:
  docker compose exec backend python -m app.scripts.debug_velox <sessionId>
  docker compose exec backend python -m app.scripts.debug_velox <sessionId> --cursor <cursor>
"""

import argparse
import json
import sys
import httpx
from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug da API da Helena")
    parser.add_argument("session_id", help="sessionId a consultar")
    parser.add_argument("--page", type=int, default=None, help="PageNumber (default: 1)")
    parser.add_argument("--page-size", type=int, default=None, help="PageSize 1-100 (default: 15)")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="imprime o JSON cru completo no final",
    )
    args = parser.parse_args()

    url = settings.HELENA_API_URL
    key = settings.HELENA_API_KEY

    def mask(token: str) -> str:
        if not token:
            return "(vazio)"
        if len(token) <= 12:
            return f"{token[:2]}...{token[-2:]} (len={len(token)})"
        return f"{token[:8]}...{token[-4:]} (len={len(token)})"

    print("═" * 60)
    print(f"URL configurada : {url}")
    print(f"Token (preview) : {mask(key) if key else 'NÃO (HELENA_API_KEY vazio)'}")
    print(f"sessionId       : {args.session_id}")
    if args.page:
        print(f"page            : {args.page}")
    print("═" * 60)

    if not key:
        print("\n[ERRO] HELENA_API_KEY não está setado no ambiente do container.")
        print("Confira o .env e reinicie o backend (`docker compose restart backend`).")
        return 2

    if key == "your_helena_api_key_here":
        print("\n[ERRO] HELENA_API_KEY ainda está com o placeholder do .env.example.")
        print("Coloque o token real no .env e rode `docker compose restart backend`.")
        return 2

    params = {"SessionId": args.session_id}
    if args.page:
        params["PageNumber"] = args.page
    if args.page_size:
        params["PageSize"] = args.page_size

    headers = {"Authorization": f"Bearer {key}"}

    try:
        with httpx.Client(timeout=30) as client:
            req = client.build_request("GET", url, params=params, headers=headers)
            print("\n>>> REQUEST")
            print(f"  {req.method} {req.url}")
            for hk, hv in req.headers.items():
                if hk.lower() == "authorization":
                    scheme, _, tok = hv.partition(" ")
                    hv = f"{scheme} {mask(tok)}"
                print(f"  {hk}: {hv}")
            print()
            response = client.send(req)
    except httpx.RequestError as e:
        print(f"\n[ERRO de rede] {type(e).__name__}: {e}")
        print("Causas comuns:")
        print("  - DNS não resolve (URL errada ou container sem internet)")
        print("  - Firewall bloqueando saída")
        return 3

    print(f"\nStatus       : {response.status_code} {response.reason_phrase}")
    print(f"URL final    : {response.url}")
    print(f"Tamanho      : {len(response.content)} bytes")
    print("\nHeaders:")
    for k, v in response.headers.items():
        print(f"  {k}: {v}")

    if response.status_code >= 400:
        print(f"\n[Body de erro]\n{response.text[:1000]}")
        return 4

    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"\n[Resposta não é JSON]\n{response.text[:500]}")
        return 5

    print("\n" + "═" * 60)
    print("Shape detectado:")
    if isinstance(data, list):
        print(f"  → lista crua com {len(data)} item(ns)")
        items = data
    elif isinstance(data, dict):
        print(f"  → dict com chaves: {list(data.keys())}")
        items = data.get("items") or []
        print(f"  → items: {len(items)}")
        print("  → paginação:")
        for k in ("pageNumber", "pageSize", "totalItems", "totalPages", "hasMorePages"):
            if k in data:
                print(f"      {k}: {data[k]!r}")
    else:
        print(f"  → tipo inesperado: {type(data).__name__}")
        items = []

    if items:
        first = items[0]
        print("\nPrimeira mensagem:")
        if isinstance(first, dict):
            print(f"  chaves de topo: {list(first.keys())}")
            print(f"  type           : {first.get('type')!r}")
            print(f"  createdAt      : {first.get('createdAt')!r}")
            text = first.get("text")
            if text:
                preview = text[:120] + ("..." if len(text) > 120 else "")
                print(f"  text (preview) : {preview!r}")
            details = first.get("details")
            if isinstance(details, dict) and details.get("file"):
                fileinfo = details["file"]
                print(f"  details.file   : {list(fileinfo.keys())}")
                print(f"    extension      : {fileinfo.get('extension')!r}")
                print(f"    mimeType       : {fileinfo.get('mimeType')!r}")
                print(f"    publicUrlDownload presente: "
                      f"{'sim' if fileinfo.get('publicUrlDownload') else 'não'}")
        else:
            print(f"  (não é dict): {first!r}")

    if args.raw:
        print("\n" + "═" * 60)
        print("JSON cru completo:")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])

    print("\n" + "═" * 60)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
