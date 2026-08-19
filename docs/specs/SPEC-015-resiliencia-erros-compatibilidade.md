# SPEC-015 — Resiliência, Erros e Compatibilidade

## Objetivo

Manter coleta útil mesmo quando fontes são incompletas, corrompidas ou mudam de formato.

## Parsing JSONL

Processar linha a linha.

Linha inválida:

- registrar ImportError;
- continuar o arquivo quando seguro.

## Arquivo truncado

Última linha incompleta em arquivo ainda em escrita:

- não tratar como falha definitiva;
- aguardar próxima coleta.

## Campos desconhecidos

Ignorar ou preservar como metadata.

Não interromper importação.

## Mudança de schema

Collector deve registrar:

```text
source_version
parser_version
```

## Compatibilidade

V1 deve ser testada contra fixtures representando:

- Codex atual observado;
- variação com campos adicionais;
- ausência de campos opcionais;
- Headroom com/sem history;
- Headroom sem session_stats.

## Erros

Categorias:

```text
configuration
source_not_found
permission
parse
database
correlation
reporting
unknown
```

## Critérios de aceite

- [ ] linha corrompida não derruba toda a coleta;
- [ ] linha final parcial é tolerada;
- [ ] campos novos não quebram parser;
- [ ] erros são persistidos;
- [ ] status mostra falhas parciais.
