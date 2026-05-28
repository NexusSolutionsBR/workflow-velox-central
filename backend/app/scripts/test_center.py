"""
Teste de integração com a API Center.

Etapas:
  1. Consulta ocorrências existentes da ficha de teste (105575)
  2. Mostra as ocorrências que serão inseridas (baseadas na ficha 105509 do banco)
  3. Insere as ocorrências na ficha de teste
  4. Consulta novamente para confirmar a inserção

Uso:
  docker compose exec backend python -m app.scripts.test_center
"""

import asyncio
import json
from app.core.config import settings
from app.services.center_service import check_duplicate, insert_occurrence, parse_summary_to_occurrences

FICHA_TESTE = "105575"

# Resumo real da ficha 105509 — usado como dado de teste
SUMMARY_105509 = """\
1. 27/05/2026, 06:12:22 — PÚBLICA — O OPERADOR INICIA O ATENDIMENTO OPERACIONAL.

2. 27/05/2026, 06:32:15 — PÚBLICA — O PRESTADOR INFORMA LOCALIZAÇÃO INICIAL (-6.5616827011108, -47.473827362061) E ENCAMINHA REGISTROS FOTOGRÁFICOS DO LOCAL PARA DOCUMENTAÇÃO.

3. 27/05/2026, 07:07:55 — PÚBLICA — O PRESTADOR LOCALIZA O VEÍCULO NO POSTO FISCAL, REGISTRA FOTOS, INFORMA QUE O CONDUTOR APRESENTA SINAIS DE EMBRIAGUEZ, RESISTE A ENTREGAR DOCUMENTAÇÃO E REALIZOU MANOBRA CONSIDERADA "CEGA"; É SUGERIDO CONTATO COM A PRF PARA INTERVENÇÃO.

4. 27/05/2026, 07:11:20 — PÚBLICA — O PRESTADOR ENCAMINHA REGISTROS FOTOGRÁFICOS E VÍDEOS DO CONDUTOR, DO VEÍCULO E DA CARGA, INCLUINDO OITIVA EVIDENCIADA EM VÍDEO, PARA DOCUMENTAÇÃO OPERACIONAL.

5. 27/05/2026, 08:00:13 — PÚBLICA — O OPERADOR ORIENTA MANTER A PRESERVAÇÃO DO LOCAL E DETERMINA QUE, AO REINICIAR A VIAGEM, O PRESTADOR ACOMPANHE O CONDUTOR POR 10 KM ANTES DE DISPENSAR AGENTE.

6. 27/05/2026, 13:03:17 — PÚBLICA — O PRESTADOR REGISTRA E ENCAMINHA VÍDEO DO VEÍCULO SEM O CONDUTOR PARA COMPROVAÇÃO, ATENDENDO SOLICITAÇÃO DO OPERADOR.

7. 27/05/2026, 13:31:20 — PÚBLICA — O PRESTADOR INFORMA O RETORNO DO CONDUTOR, INICIA O ACOMPANHAMENTO CONFORME ORIENTAÇÃO, ENCAMINHA LOCALIZAÇÃO (-6.4882626533508, -47.384967803955) E REGISTROS FOTOGRÁFICOS APÓS O ACOMPANHAMENTO.

8. 27/05/2026, 13:35:44 — PÚBLICA — O OPERADOR FINALIZA O ATENDIMENTO OPERACIONAL (PROTOCOLO 105509).\
"""


def _section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def _print_response(data):
    if data is None:
        print("  → Nenhum dado retornado (None)")
    elif isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"  → {data}")


async def main():
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║         TESTE DE INTEGRAÇÃO — CENTER API                 ║")
    print(f"║         Ficha de teste: {FICHA_TESTE:<35}║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ── Configuração ────────────────────────────────────────────
    _section("CONFIGURAÇÃO")
    print(f"  URL:                   {settings.CENTER_CONSULTA_URL}")
    print(f"  IDENTIFICADOR_FICHA:   {'✓ configurado' if settings.CENTER_IDENTIFICADOR_FICHA else '✗ não configurado'}")
    print(f"  IDENTIFICADOR_OCORR:   {'✓ configurado' if settings.CENTER_IDENTIFICADOR_OCORRENCIAS else '✗ não configurado (mock)'}")
    print(f"  IDENTIFICADOR_INSERCAO:{'✓ configurado' if settings.CENTER_IDENTIFICADOR_INSERCAO else '✗ não configurado (mock)'}")
    print(f"  USUARIO_PARAMETRO:     {settings.CENTER_USUARIO_PARAMETRO or '(vazio)'}")

    # ── Etapa 1: Consultar ocorrências existentes ────────────────
    _section("ETAPA 1 — Consultar ocorrências existentes da ficha 105575")
    print(f"  Buscando ocorrências para ficha={FICHA_TESTE}...")
    existente = await check_duplicate(FICHA_TESTE)
    if existente:
        print(f"  → Ocorrências encontradas:")
        _print_response(existente)
    else:
        print("  → Nenhuma ocorrência encontrada (ficha limpa ou mock ativo)")

    # ── Etapa 2: Parse do resumo ─────────────────────────────────
    _section("ETAPA 2 — Ocorrências que serão inseridas (fonte: ficha 105509)")
    occurrencias = parse_summary_to_occurrences(SUMMARY_105509)
    print(f"  {len(occurrencias)} ocorrência(s) extraída(s) do resumo:\n")
    for i, o in enumerate(occurrencias, 1):
        print(f"  [{i}] {o['datahora']}  [{o['tipo']}]")
        print(f"       {o['descricao'][:90]}{'...' if len(o['descricao']) > 90 else ''}")
        print()

    if not occurrencias:
        print("  ✗ Nenhuma ocorrência extraída — verifique o formato do resumo.")
        return

    confirm = input(f"\n  Confirma inserção de {len(occurrencias)} ocorrência(s) na ficha {FICHA_TESTE}? [s/N] ").strip().lower()
    if confirm != 's':
        print("  Inserção cancelada.")
        return

    # ── Etapa 3: Inserir ocorrências ─────────────────────────────
    _section("ETAPA 3 — Inserindo ocorrências na ficha 105575")
    print(f"  Inserindo {len(occurrencias)} ocorrência(s)...")
    try:
        resultado = await insert_occurrence(
            session_id="teste-script",
            ficha=FICHA_TESTE,
            summary_text=SUMMARY_105509,
        )
        print("  ✓ Inserção concluída. Resposta da API:")
        _print_response(resultado)
    except Exception as e:
        print(f"  ✗ ERRO na inserção: {e}")
        return

    # ── Etapa 4: Confirmar consulta após inserção ────────────────
    _section("ETAPA 4 — Consultando ocorrências após inserção")
    print(f"  Verificando ficha={FICHA_TESTE} novamente...")
    apos = await check_duplicate(FICHA_TESTE)
    if apos:
        print("  → Ocorrências após inserção:")
        _print_response(apos)
    else:
        print("  → Nenhum dado retornado (verificar manualmente no Center)")

    print("\n  Teste concluído.\n")


if __name__ == "__main__":
    asyncio.run(main())
