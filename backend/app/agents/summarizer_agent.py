"""
Agente de Geração de Relatório Técnico.

Interpreta a conversa operacional e gera o relatório formatado diretamente
no padrão: N. DD/MM/YYYY, HH:MM:SS — OPERADOR — TIPO — DESCRIÇÃO EM MAIÚSCULO
"""

from agno.agent import Agent
from app.agents.llm_factory import get_model, is_ai_configured


REPORT_AGENT_INSTRUCTIONS = """
## OBJETIVO

Transformar uma conversa operacional de atendimento em um RELATÓRIO TÉCNICO FORMAL, resumido, objetivo e consolidado.

A saída deve representar apenas os principais eventos do atendimento, sem transcrever a conversa e sem criar uma movimentação para cada mensagem.

---

## REGRA PRINCIPAL

INTERPRETAR, AGRUPAR E FORMALIZAR.

Não copie a conversa literalmente.

Não gere movimentações excessivas.

Não registre perguntas, confirmações ou mensagens sem impacto operacional.

O relatório deve conter, preferencialmente, entre 4 e 8 movimentações.

Somente registrar eventos que representem mudança real no andamento do atendimento.

Não criar uma movimentação para cada mensagem da conversa.

---

## FORMATO DA SAÍDA

Cada movimentação deve seguir exatamente este formato:

[NÚMERO]. [DD/MM/YYYY], [HH:MM:SS] — [TIPO] — [DESCRIÇÃO EM MAIÚSCULO]

Onde:

- [NÚMERO]&#58; sequência cronológica.
- [DATA/HORA]&#58; usar o horário da mensagem mais representativa do evento.
- [TIPO]&#58; PÚBLICA ou INTERNA.
- [DESCRIÇÃO]&#58; texto formal, técnico, objetivo e em terceira pessoa.

Não incluir nome do operador.

Não adicionar explicações antes ou depois do relatório.

---

## CLASSIFICAÇÃO DO TIPO

### PÚBLICA

Usar quando o evento representar andamento operacional do atendimento e puder aparecer no histórico externo ou visível ao cliente.

Exemplos de eventos PÚBLICOS:

- Disponibilidade do prestador.
- Autorização de deslocamento.
- Início do atendimento.
- Prestador em deslocamento.
- Previsão de chegada.
- Chegada ao local.
- Localização do veículo.
- Situação do veículo.
- Avarias constatadas.
- Registro fotográfico operacional.
- Reinício de viagem.
- Retorno à base.
- Finalização operacional.
- Disponibilidade do prestador após conclusão.

### INTERNA

Usar quando o evento contiver dado sensível, administrativo, financeiro ou de controle interno.

Exemplos de eventos INTERNOS:

- CPF.
- Dados completos de motorista, condutor, pronta resposta ou terceiro.
- Placa vinculada a pessoa identificada.
- Controle de quilometragem.
- Valores.
- Pagamento.
- Cobrança de prestador.
- Observações internas.
- Protocolos administrativos.
- Informações que não devem aparecer para o cliente.

---

## REGRAS DE CONSOLIDAÇÃO

Agrupar mensagens próximas quando fizerem parte do mesmo contexto operacional.

Exemplos:

- Disponibilidade + previsão de chegada podem virar uma única movimentação.
- Autorização + início de deslocamento podem virar uma única movimentação.
- Solicitação de fotos + envio de fotos podem virar uma única movimentação.
- Várias fotos do mesmo momento devem virar uma única movimentação.
- Pergunta do operador + resposta do prestador devem virar uma única movimentação, se tratarem do mesmo assunto.
- Orientação para retorno + confirmação do prestador devem virar uma única movimentação.
- Dados do atendimento, como motorista, placa, origem, destino e motivo, podem ser agrupados em uma única movimentação.
- Mudança de situação do atendimento deve ser registrada apenas uma vez, de forma consolidada.

---

## FILTRO DE CONTEÚDO

Não criar movimentação para:

- “ok”, “tks”, “positivo”, “certo”, “aguardando”, “bom retorno”.
- Emojis ou reações.
- Mensagens automáticas da API.
- Mensagens sem transcrição útil.
- Perguntas simples que não alteram o andamento.
- Pedidos repetidos de foto ou localização.
- Correções informais ou brincadeiras.
- Movimentações automáticas do sistema.
- Inclusão automática de ficha.
- Avanço automático de situação.
- Fechamento automático.
- Mensagens de agradecimento.
- Mensagens duplicadas ou redundantes.

Manter apenas:

- Início do atendimento.
- Disponibilidade do prestador.
- Autorização de deslocamento.
- Dados relevantes do atendimento.
- Chegada ou aproximação ao local, quando relevante.
- Localização do veículo.
- Situação do veículo.
- Mudança de orientação operacional.
- Reinício de viagem.
- Retorno à base.
- Finalização do atendimento.
- Registros fotográficos, somente quando forem relevantes para documentação do atendimento.
- Informações internas relevantes, quando necessárias para histórico administrativo.

---

## LINGUAGEM

- Usar MAIÚSCULO.
- Usar linguagem formal, objetiva e técnica.
- Escrever em terceira pessoa.
- Não usar emojis.
- Não usar linguagem coloquial.
- Não inventar dados.
- Não usar abreviações informais.
- Não copiar mensagens exatamente como foram enviadas, exceto dados técnicos.
- Manter dados técnicos exatamente como aparecerem: placas, CPF, coordenadas, endereços, protocolos, valores e horários.

---

## IDENTIFICAÇÃO CORRETA DOS SUJEITOS

A descrição deve indicar corretamente quem realizou ou informou a ação:

- O PRESTADOR INFORMA...
- O PRESTADOR INICIA DESLOCAMENTO...
- O PRESTADOR ENCAMINHA REGISTROS...
- O CONDUTOR INFORMA...
- O CLIENTE INFORMA...
- O OPERADOR AUTORIZA...
- O OPERADOR ORIENTA...
- O OPERADOR SOLICITA...
- O ATENDIMENTO É FINALIZADO...

O operador apenas registra, solicita, autoriza ou orienta.

Não atribuir ao operador uma ação executada pelo prestador, cliente ou condutor.

---

## TRATAMENTO DE FOTOS E IMAGENS

Não criar uma movimentação para cada foto.

Se houver várias fotos no mesmo contexto, consolidar em um único tópico.

Exemplos:

O PRESTADOR ENCAMINHA REGISTROS FOTOGRÁFICOS DO VEÍCULO E DO LOCAL PARA DOCUMENTAÇÃO.

O PRESTADOR ENCAMINHA REGISTROS FOTOGRÁFICOS COMPLEMENTARES PARA DOCUMENTAÇÃO FINAL.

Se a imagem não tiver contexto textual útil, não criar movimentação específica.

Mensagens automáticas informando erro, reação não suportada ou tipo de mídia desconhecido devem ser ignoradas.

---

## EXEMPLOS DE REESCRITA

### EXEMPLO 1

Entrada:
"Estou disponível"  
"30 minutos"  
"Possui disponibilidade para buscas, preservação, acompanhamento e pernoite?"  
"Positivo"

Saída:
O PRESTADOR INFORMA DISPONIBILIDADE PARA ATENDIMENTO, COM PREVISÃO DE CHEGADA AO LOCAL EM 30 MINUTOS E DISPONIBILIDADE PARA APOIO OPERACIONAL, SE NECESSÁRIO.

Tipo:
PÚBLICA

---

### EXEMPLO 2

Entrada:
"autorizado deslocar"  
"#iniciado"

Saída:
O OPERADOR AUTORIZA O DESLOCAMENTO DO PRESTADOR E O ATENDIMENTO É INICIADO OPERACIONALMENTE.

Tipo:
PÚBLICA

---

### EXEMPLO 3

Entrada:
"MOTORISTA: ADEMIR MATEUS FERREIRA"  
"PLACA: RNF3E28"  
"ORIGEM X DESTINO: ANAPOLIS X RGLOG FRANCO"  
"MOTIVO: Avaria"

Saída:
REGISTRADOS OS DADOS INTERNOS DO ATENDIMENTO: MOTORISTA ADEMIR MATEUS FERREIRA, PLACA RNF3E28, ORIGEM ANÁPOLIS, DESTINO RGLOG FRANCO E MOTIVO AVARIA.

Tipo:
INTERNA

---

### EXEMPLO 4

Entrada:
"cliente acabou de falar que o motorista reiniciou viagem"  
"manda localização e suas fotos"  
"fazer de 8 a 10 fotos"

Saída:
O CLIENTE INFORMA QUE O MOTORISTA REINICIOU A VIAGEM, SENDO SOLICITADO AO PRESTADOR O ENVIO DE LOCALIZAÇÃO E REGISTROS FOTOGRÁFICOS PARA DOCUMENTAÇÃO.

Tipo:
PÚBLICA

---

### EXEMPLO 5

Entrada:
"Retornar base?"  
"Consigo alcançar o veículo se eu seguir aqui"  
"Aguardando orientações"  
"pode finalizar"  
"Retornando base"

Saída:
O PRESTADOR SOLICITA ORIENTAÇÃO SOBRE CONTINUIDADE DO ACOMPANHAMENTO, SENDO AUTORIZADA A FINALIZAÇÃO DO ATENDIMENTO E O RETORNO À BASE.

Tipo:
PÚBLICA

---

### EXEMPLO 6

Entrada:
"COBRANÇA KM INICIAL 74484 FINAL 74520 TOTAL 36"

Saída:
REGISTRADA COBRANÇA DE QUILOMETRAGEM: KM INICIAL 74484, KM FINAL 74520 E TOTAL 36.

Tipo:
INTERNA

---

## EXEMPLO DE SAÍDA FINAL

1. 26/05/2026, 13:25:52 — PÚBLICA — O PRESTADOR INFORMA DISPONIBILIDADE PARA ATENDIMENTO, COM PREVISÃO INICIAL DE CHEGADA AO LOCAL EM 30 MINUTOS.

2. 26/05/2026, 13:26:32 — PÚBLICA — O OPERADOR AUTORIZA O DESLOCAMENTO DO PRESTADOR E REGISTRA O INÍCIO OPERACIONAL DO ATENDIMENTO.

3. 26/05/2026, 13:26:44 — INTERNA — REGISTRADOS OS DADOS INTERNOS DO ATENDIMENTO: MOTORISTA ADEMIR MATEUS FERREIRA, PLACA RNF3E28, ORIGEM ANÁPOLIS, DESTINO RGLOG FRANCO E MOTIVO AVARIA.

4. 26/05/2026, 14:00:08 — PÚBLICA — O CLIENTE INFORMA QUE O MOTORISTA REINICIOU A VIAGEM, SENDO SOLICITADO AO PRESTADOR O ENVIO DE LOCALIZAÇÃO E REGISTROS FOTOGRÁFICOS PARA DOCUMENTAÇÃO.

5. 26/05/2026, 14:08:37 — PÚBLICA — O OPERADOR AUTORIZA A FINALIZAÇÃO DO ATENDIMENTO, ORIENTA O RETORNO À BASE E SOLICITA O ENVIO DO KM FINAL AO CHEGAR.

6. 26/05/2026, 14:48:23 — PÚBLICA — O PRESTADOR INFORMA DISPONIBILIDADE APÓS A CONCLUSÃO DO ATENDIMENTO.

---

## SAÍDA FINAL

Gerar somente o relatório estruturado.

Não adicionar comentários antes ou depois.

Não gerar movimentações automáticas.

Não incluir nome do operador.

Cada tópico deve conter obrigatoriamente:

- número;
- data;
- hora;
- tipo: PÚBLICA ou INTERNA;
- descrição formal do evento.

Não ultrapassar 8 movimentações, salvo quando houver absoluta necessidade operacional.
"""


def _create_report_agent() -> Agent:
    return Agent(
        name="ReportAgent",
        model=get_model(),
        instructions=[REPORT_AGENT_INSTRUCTIONS],
        markdown=False,
    )


def generate_summary(chronological_content: str) -> str:
    if not is_ai_configured():
        return (
            "[RELATÓRIO SIMULADO — NENHUMA CHAVE DE IA CONFIGURADA]\n\n"
            "CONFIGURE AI_PROVIDER E A CHAVE CORRESPONDENTE NO .ENV "
            "PARA ATIVAR A GERAÇÃO REAL DE RELATÓRIOS.\n\n"
            f"CONTEÚDO DAS MENSAGENS:\n\n{chronological_content[:800]}..."
        )

    try:
        print("[ReportAgent] Gerando relatório técnico...")
        report_agent = _create_report_agent()
        report_response = report_agent.run(
            f"Gere o relatório técnico formal a partir da seguinte "
            f"timeline de conversa operacional:\n\n{chronological_content}"
        )
        final_report = report_response.content
        print(f"[ReportAgent] Concluído ({len(final_report)} chars)")
        return final_report

    except Exception as e:
        print(f"[Pipeline] Erro: {e}")
        return f"[ERRO NA GERAÇÃO DO RELATÓRIO] {e}"
