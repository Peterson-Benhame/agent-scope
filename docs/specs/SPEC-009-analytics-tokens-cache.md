# SPEC-009 — Analytics de Tokens e Cache

## Objetivo

Produzir métricas confiáveis de uso de tokens e reutilização por cache.

## Métricas básicas

Por sessão, projeto, modelo e período:

```text
input_tokens
cached_input_tokens
cache_write_input_tokens
output_tokens
reasoning_output_tokens
total_tokens
```

## Métricas derivadas

```text
tokens_per_session
cached_input_ratio
output_ratio
reasoning_ratio
sessions_per_day
tokens_per_day
tokens_per_project
tokens_per_model
```

## Cache

Não somar `cached_input_tokens` como tokens novos.

Exibir separadamente:

- tokens enviados;
- tokens lidos de cache;
- cache write;
- tokens gerados.

## Agregação

Suportar:

- por dia;
- por semana;
- por projeto;
- por modelo;
- por sessão.

## Regra de precisão

Se eventos de token estiverem incompletos:

- marcar agregação como parcial;
- não preencher com zero.

## Critérios de aceite

- [ ] métricas por sessão funcionam;
- [ ] métricas por projeto funcionam;
- [ ] métricas por modelo funcionam;
- [ ] cache é separado de input novo;
- [ ] períodos parciais são identificados.
