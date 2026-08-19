# SPEC-006 — Normalização e Correlação

## Objetivo

Converter eventos específicos em entidades genéricas e correlacionar Codex com Headroom com nível explícito de confiança.

## Normalização

Adapters devem produzir estruturas normalizadas:

```text
NormalizedSession
NormalizedTurn
NormalizedMessage
NormalizedToolCall
NormalizedTokenUsage
NormalizedOptimization
NormalizedAgentEvidence
NormalizedSkillEvidence
```

## Correlação

Ordem de preferência:

1. session ID exato;
2. turn ID/request ID exato;
3. identificador compartilhado;
4. timestamp + modelo + projeto;
5. janela temporal.

## Confiança

Valores:

```text
exact
high
medium
unknown
```

Regras:

- `exact`: identificador forte compartilhado.
- `high`: conjunto de sinais sem ambiguidade razoável.
- `medium`: associação temporal plausível.
- `unknown`: não associar a uma sessão específica.

## Proibições

Não correlacionar por:

- somente modelo;
- somente PID;
- somente ordem de arquivo;
- somente proximidade de horário sem tolerância definida.

## Requisitos

A correlação deve ser determinística.

Mesmos dados de entrada devem produzir os mesmos vínculos.

## Reconciliação

Quando Headroom fornecer totais e eventos:

- calcular total derivado dos eventos;
- comparar com agregado;
- registrar discrepância;
- não alterar silenciosamente os dados brutos.

## Critérios de aceite

- [ ] modelos específicos são convertidos para entidades genéricas;
- [ ] correlação possui nível de confiança;
- [ ] vínculos exatos são priorizados;
- [ ] correlação fraca não é exibida como exata;
- [ ] discrepâncias são registradas.
