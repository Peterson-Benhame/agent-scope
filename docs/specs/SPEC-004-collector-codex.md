# SPEC-004 — Collector Codex

## Objetivo

Ler o histórico local do Codex e converter eventos brutos em registros normalizáveis.

## Fontes

```text
session_index.jsonl
sessions/**/rollout-*.jsonl
attachments/**
```

## Eventos mínimos suportados

### session_meta

Extrair:

- session ID;
- timestamp;
- cwd;
- originator;
- cli_version;
- source;
- thread_source;
- model_provider;
- context window quando disponível.

### turn_context

Extrair:

- turn ID;
- cwd;
- model;
- reasoning effort;
- timezone;
- collaboration mode.

### response_item/message

Extrair:

- role;
- phase;
- timestamp;
- conteúdo;
- turn ID quando disponível.

### event_msg/user_message

Extrair a mensagem do usuário.

### token_count

Extrair:

- input_tokens;
- cached_input_tokens;
- cache_write_input_tokens;
- output_tokens;
- reasoning_output_tokens;
- total_tokens;
- model_context_window.

### tool calls

Suportar registros equivalentes a:

- custom_tool_call;
- custom_tool_call_output;
- function/tool calls futuros quando identificáveis.

### agentes

Detectar somente com evidência explícita:

- spawn_agent;
- followup_task;
- send_message;
- metadata de agente;
- mensagens de colaboração.

### skills

Distinguir:

- listadas como disponíveis;
- lidas/carregadas;
- explicitamente anunciadas/usadas.

## Attachments

Quando uma mensagem referenciar:

```text
.codex\attachments\<id>\<arquivo>
```

registrar vínculo com a mensagem/sessão.

Não duplicar automaticamente o conteúdo inteiro no relatório seguro.

## Reasoning

Campos com `encrypted_content` devem ser registrados apenas como existência/metadado.

Nunca tentar descriptografar.

## Encoding

Collector deve tolerar:

- UTF-8;
- caracteres escapados;
- mojibake no conteúdo legado.

Não corrigir silenciosamente texto original no armazenamento de evidência.

## Critérios de aceite

- [ ] session_meta é extraído;
- [ ] mensagens user/assistant são identificadas;
- [ ] tool calls são identificados;
- [ ] token_count é extraído;
- [ ] attachments são relacionados;
- [ ] agentes só são marcados quando há evidência;
- [ ] skills possuem estados distintos;
- [ ] encrypted reasoning não é exposto.
