# SPEC-002 — Modelo de Domínio e Dados

## Problema

Codex e Headroom usam estruturas e terminologias diferentes. Sem um modelo comum, qualquer relatório ficará acoplado aos formatos atuais.

## Objetivo

Definir as entidades normalizadas da V1.

## Entidades

### Source

Origem dos dados.

Campos mínimos:

```text
id
name
type
version
```

### Project

Workspace/projeto associado à execução.

```text
id
name
path
```

### Session

Execução conversacional.

```text
id
source_id
external_session_id
project_id
started_at
ended_at
originator
provider
model_id
cli_version
raw_file_path
```

### Turn

Unidade lógica de interação.

```text
id
session_id
external_turn_id
started_at
ended_at
```

### Message

Mensagem normalizada.

```text
id
session_id
turn_id
role
phase
timestamp
content
content_type
source_file
source_line
```

### Model

```text
id
provider
name
```

### Agent

```text
id
name
type
```

Tipos iniciais:

- root
- subagent
- named

### SessionAgent

```text
session_id
agent_id
parent_agent_id
started_at
ended_at
evidence_type
```

### Skill

```text
id
name
source
version
```

### SessionSkill

```text
session_id
skill_id
usage_type
first_seen_at
evidence_type
```

Valores de `usage_type`:

- available
- loaded
- invoked

### Tool

```text
id
name
provider
category
```

### ToolCall

```text
id
session_id
turn_id
tool_id
external_call_id
timestamp
duration_ms
status
input_size
output_size
source_file
source_line
```

### TokenUsage

```text
id
session_id
turn_id
timestamp
model_id
input_tokens
cached_input_tokens
cache_write_input_tokens
output_tokens
reasoning_output_tokens
total_tokens
context_window
```

### Optimizer

```text
id
name
version
```

Headroom deve ser `Optimizer`, não `Agent`.

### Optimization

```text
id
optimizer_id
session_id
timestamp
model_id
original_tokens
optimized_tokens
tokens_saved
compression_percent
cache_read_tokens
compression_savings_usd
cache_savings_usd
correlation_confidence
```

### Cost

```text
id
session_id
model_id
period_start
period_end
estimated_raw_cost_usd
observed_cost_usd
estimated_cost_after_optimization_usd
compression_savings_usd
cache_savings_usd
total_savings_usd
pricing_source
pricing_version
```

### ImportState

```text
id
source
path
size
modified_at
content_hash
last_offset
last_imported_at
status
```

### ImportError

```text
id
source
file
line
error_type
error_message
timestamp
```

## Regras

1. Identificador externo deve ser preservado.
2. Valores monetários desconhecidos são `NULL`, nunca `0`.
3. Texto original pode ser armazenado, mas relatórios seguros não o expõem por padrão.
4. `available` não pode ser promovido automaticamente para `invoked`.
5. `Agent`, `Skill`, `Tool`, `Model` e `Optimizer` são conceitos distintos.
6. Toda relação inferida deve possuir `evidence_type` ou confiança.

## Critérios de aceite

- [ ] todas as entidades acima possuem representação no domínio;
- [ ] nenhuma entidade central possui prefixo `Codex` ou `Headroom`;
- [ ] Headroom é modelado como optimizer;
- [ ] custos desconhecidos suportam NULL;
- [ ] skill disponível e skill invocada são distinguíveis;
- [ ] proveniência pode ser ligada ao registro original.
