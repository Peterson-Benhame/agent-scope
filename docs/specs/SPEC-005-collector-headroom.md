# SPEC-005 — Collector Headroom

## Objetivo

Importar métricas persistidas do Headroom sem depender do proxy ativo.

## Fontes

Primárias:

```text
proxy_savings.json
session_stats.jsonl
```

Opcionais quando proxy estiver ativo:

```text
/stats
/stats-history
```

A coleta via endpoint é complementar.

## Dados de proxy_savings

Extrair quando disponíveis:

- lifetime requests;
- tokens_saved;
- compression_savings_usd;
- cache_read_tokens;
- cache_savings_usd;
- total_input_tokens;
- input cost;
- history por timestamp;
- projetos;
- modelos;
- métricas de cache;
- waste signals.

## Dados de session_stats

Quando presentes:

- sessão;
- agente;
- modelo;
- compressões;
- savings;
- timestamps.

## Histórico JSONL de savings

Suportar eventos contendo:

```text
before
after
saved
cost_usd
model
client
source
pid
timestamp
```

## Regras

1. Dados agregados e eventos individuais não devem ser somados duas vezes.
2. Agregados servem para validação/reconciliação.
3. Eventos individuais são preferidos para analytics temporal.
4. Ausência de `session_stats.jsonl` não é erro fatal.
5. Métricas de Headroom devem ser classificadas como observadas pelo optimizer, não como cobrança OpenAI.

## Critérios de aceite

- [ ] proxy_savings é importado;
- [ ] histórico temporal é importado;
- [ ] modelos e projetos são reconhecidos;
- [ ] savings por compressão e cache permanecem separados;
- [ ] ausência de proxy ativo não impede análise;
- [ ] agregados não causam dupla contagem.
