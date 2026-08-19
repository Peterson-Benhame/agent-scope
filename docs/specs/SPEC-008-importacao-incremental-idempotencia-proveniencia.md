# SPEC-008 — Importação Incremental, Idempotência e Proveniência

## Objetivo

Permitir reexecução frequente sem duplicação e sem reler desnecessariamente todo o histórico.

## ImportState

Para cada arquivo:

```text
path
source
size
modified_at
content_hash
last_offset
last_imported_at
status
```

## Arquivos JSONL em crescimento

Quando:

- path é o mesmo;
- conteúdo anterior permanece;
- tamanho aumentou;

ler a partir de `last_offset`.

## Arquivo substituído

Se hash/prefixo não corresponder:

- invalidar estado incremental;
- reprocessar arquivo;
- usar idempotência para não duplicar registros.

## Proveniência

Registros relevantes devem preservar:

```text
source
source_file
source_line
external_id
```

## Idempotência

Rodar:

```text
agentscope collect
agentscope collect
```

sem alteração nas fontes deve resultar em zero novos registros lógicos.

## Deleção na origem

A V1 não deve apagar automaticamente registros do banco quando um arquivo desaparecer.

Registrar fonte como ausente.

## Critérios de aceite

- [ ] arquivo inalterado é ignorado;
- [ ] JSONL em crescimento importa apenas novas linhas;
- [ ] reprocessamento não duplica;
- [ ] proveniência é preservada;
- [ ] arquivos removidos não causam exclusão automática.
