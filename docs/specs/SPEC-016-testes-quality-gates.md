# SPEC-016 — Testes e Quality Gates

## Objetivo

Definir cobertura comportamental mínima e gates para considerar a V1 confiável.

## Estratégia

pytest.

Estrutura:

```text
tests/
├── fixtures/
├── unit/
└── integration/
```

## Fixtures

Devem ser sanitizadas e sintéticas.

Não versionar históricos pessoais reais.

## Testes unitários mínimos

### Codex collector

- session_meta;
- turn_context;
- user message;
- assistant message;
- tool call;
- token_count;
- attachment reference;
- encrypted reasoning.

### Headroom collector

- proxy_savings;
- history;
- model breakdown;
- project breakdown;
- savings event.

### Normalização

- model;
- project;
- session;
- agent evidence;
- skill evidence;
- correlation confidence.

### Storage

- migrations;
- constraints;
- idempotência;
- transaction rollback.

### Analytics

- tokens;
- cache;
- cost NULL;
- savings;
- aggregations.

### Reporting

- safe mode;
- CSV;
- JSON;
- HTML.

## Testes de integração

1. importar fixtures Codex;
2. importar fixtures Headroom;
3. correlacionar;
4. persistir;
5. analisar;
6. exportar;
7. gerar HTML.

## Quality gates

Antes de release:

```text
pytest
ruff/check equivalente se adotado
type check se adotado
smoke CLI
fresh database import
repeat import idempotency
safe report scan
```

## Critérios de aceite

- [ ] todos os parsers críticos possuem teste;
- [ ] fluxo ponta a ponta possui teste;
- [ ] idempotência é testada;
- [ ] safe mode é testado;
- [ ] fixtures não possuem dados pessoais reais;
- [ ] release não ocorre com testes falhando.
