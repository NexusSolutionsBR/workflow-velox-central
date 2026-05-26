"""
Script de debug do pipeline de agentes (Report → QualityReviewer → Formatter).

Constrói uma timeline a partir de mensagens reais (Helena) ou de um JSON local
e roda `generate_summary` imprimindo o resultado final + tempos de cada etapa.

Uso:
  # Timeline real, puxando mensagens via Helena API
  docker compose exec backend python -m app.scripts.debug_agents \\
      --session-id c24bb889-1e39-4e27-9440-0e381bb17058

  # Timeline a partir de um JSON local (mesmo formato que a API retorna)
  docker compose exec backend python -m app.scripts.debug_agents \\
      --from-file /app/exemplo_retorno_velox.json

  # Limitar a N mensagens (útil pra iterar rápido sem pagar por todas)
  docker compose exec backend python -m app.scripts.debug_agents \\
      --session-id c24bb889... --limit 50
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

from app.agents import generate_summary, is_ai_configured
from app.core.config import settings
from app.services.velox import fetch_session_messages


def build_timeline(messages) -> str:
    """Mesma lógica de `tasks.py`, mas sem download de mídias.
    Áudios e imagens entram só com placeholder (nome do arquivo)."""
    lines = []
    for msg in messages:
        msg_type = msg.get("type")
        file_info = msg.get("details", {}).get("file") if isinstance(msg.get("details"), dict) else None
        created_at = msg.get("createdAt", "")

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            dt_str = dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            dt_str = created_at

        if msg_type == "TEXT":
            lines.append(f"[{dt_str}] TEXTO: {msg.get('text', '')}")
        elif msg_type == "AUDIO":
            name = file_info.get("name", "audio") if file_info else "audio"
            lines.append(f"[{dt_str}] ÁUDIO: {name} (transcrição não realizada no debug)")
        elif msg_type == "IMAGE":
            name = file_info.get("name", "imagem") if file_info else "imagem"
            lines.append(f"[{dt_str}] IMAGEM: {name}")
        elif msg_type == "VIDEO":
            name = file_info.get("name", "video") if file_info else "video"
            lines.append(f"[{dt_str}] VÍDEO: {name}")
        else:
            lines.append(f"[{dt_str}] {msg_type}: {msg.get('text', '')}")

    return "\n\n".join(lines)


def load_messages_from_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data[0].get("items", []) if data and isinstance(data[0], dict) and "items" in data[0] else data
    if isinstance(data, dict):
        return data.get("items", [])
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug do pipeline de agentes")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--session-id", help="Puxa mensagens da Helena por sessionId")
    src.add_argument("--from-file", help="Lê mensagens de um JSON local")
    parser.add_argument("--limit", type=int, default=None, help="Limita N mensagens (1ªs)")
    parser.add_argument("--save-output", help="Salva o resumo final num arquivo")
    args = parser.parse_args()

    print("═" * 60)
    print(f"AI_PROVIDER         : {settings.AI_PROVIDER}")
    print(f"AI_CHAT_MODEL       : {settings.AI_CHAT_MODEL}")
    print(f"AI configurada?     : {is_ai_configured()}")
    print("═" * 60)

    if not is_ai_configured():
        print("\n[ERRO] Nenhuma chave de IA configurada (.env).")
        print("Setar uma de: OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY")
        return 2

    # Carrega mensagens
    if args.session_id:
        print(f"\n>>> Buscando mensagens via Helena (sessionId={args.session_id})...")
        t0 = time.monotonic()
        messages = asyncio.run(fetch_session_messages(args.session_id))
        print(f"  recebeu {len(messages)} mensagens em {time.monotonic() - t0:.2f}s")
    else:
        print(f"\n>>> Lendo mensagens de {args.from_file}...")
        messages = load_messages_from_file(args.from_file)
        print(f"  carregou {len(messages)} mensagens do arquivo")

    if not messages:
        print("[ERRO] Nenhuma mensagem disponível.")
        return 3

    if args.limit:
        messages = messages[: args.limit]
        print(f"  limitado a {len(messages)} mensagens (--limit)")

    # Monta timeline
    timeline = build_timeline(messages)
    print(f"\n>>> Timeline montada: {len(timeline)} chars, {len(messages)} eventos")
    print("    (primeiros 300 chars)")
    print("    " + timeline[:300].replace("\n", "\n    "))

    # Roda o pipeline dos 3 agentes
    print("\n" + "═" * 60)
    print(">>> Rodando pipeline de agentes (Report → Reviewer → Formatter)")
    print("═" * 60)
    t0 = time.monotonic()
    summary = generate_summary(timeline)
    elapsed = time.monotonic() - t0

    print("\n" + "═" * 60)
    print(f"OK — pipeline completo em {elapsed:.1f}s")
    print(f"Tamanho do resumo final: {len(summary)} chars")
    print("═" * 60)
    print("\n" + summary)

    if args.save_output:
        with open(args.save_output, "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"\n>>> Resumo salvo em {args.save_output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
