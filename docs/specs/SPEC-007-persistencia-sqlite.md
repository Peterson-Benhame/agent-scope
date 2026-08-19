# SPEC-007 — Persistência SQLite

## Objetivo

Persistir projeções analíticas locais de forma simples, auditável e reconstruível.

## Banco

Default:

```text
data/agentscope.db
```

## Requisitos

- SQLite;
- migrations versionadas;
- foreign keys habilitadas;
- transações por unidade de importação;
- índices para consultas analíticas principais.

## Tabelas

Implementar entidades definidas na SPEC-002.

## Índices mínimos

```text
sessions.external_session_id
sessions.started_at
sessions.project_id
turns.session_id
messages.session_id
messages.turn_id
tool_calls.session_id
token_usage.session_id
token_usage.timestamp
optimizations.session_id
optimizations.timestamp
costs.session_id
```

## Chaves únicas

Quando possível:

```text
(source_id, external_session_id)
(session_id, external_turn_id)
(session_id, external_call_id)
```

## Migrações

Tabela:

```text
schema_migrations
```

Campos:

```text
version
applied_at
description
```

## Regras

1. Não armazenar senha/chave de API deliberadamente.
2. Conteúdo textual pode ser armazenado localmente, mas não exportado em safe mode.
3. Falha de uma sessão deve permitir rollback daquela unidade.
4. Banco pode ser apagado e reconstruído sem perda da fonte original.

## Critérios de aceite

- [ ] schema completo é criado;
- [ ] migrations são aplicadas;
- [ ] foreign keys funcionam;
- [ ] duplicatas lógicas são impedidas;
- [ ] reconstrução do banco é possível.
