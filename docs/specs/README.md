# AgentScope — Índice de SPECs da V1

## Objetivo

Este conjunto de SPECs decompõe a V1 do AgentScope em unidades de desenvolvimento independentes, rastreáveis e testáveis.

AgentScope é uma ferramenta local de observabilidade e análise histórica de execuções de agentes, modelos, skills, tools/MCPs e otimizadores.

Na V1:

- Codex é a primeira fonte de sessões e execução;
- Headroom é a primeira fonte de otimização;
- SQLite é o armazenamento analítico;
- CSV, JSON e HTML são as saídas;
- não há extensão VS Code ainda;
- não há recomendação, roteamento ou alteração automática de agentes/modelos.

## Ordem recomendada

| Ordem | SPEC | Tema |
|---|---|---|
| 1 | SPEC-001 | Arquitetura e princípios |
| 2 | SPEC-002 | Modelo de domínio e dados |
| 3 | SPEC-003 | Configuração e descoberta de fontes |
| 4 | SPEC-004 | Collector Codex |
| 5 | SPEC-005 | Collector Headroom |
| 6 | SPEC-006 | Normalização e correlação |
| 7 | SPEC-007 | Persistência SQLite |
| 8 | SPEC-008 | Importação incremental, idempotência e proveniência |
| 9 | SPEC-009 | Analytics de tokens e cache |
| 10 | SPEC-010 | Analytics de custos e savings |
| 11 | SPEC-011 | Analytics de agentes, skills e tools |
| 12 | SPEC-012 | Exportações e relatório HTML |
| 13 | SPEC-013 | CLI e workflow operacional |
| 14 | SPEC-014 | Privacidade, segurança e sanitização |
| 15 | SPEC-015 | Resiliência, erros e compatibilidade |
| 16 | SPEC-016 | Testes e quality gates |
| 17 | SPEC-017 | Integração ponta a ponta e aceite da V1 |

## Dependências principais

```text
SPEC-001
  ↓
SPEC-002
  ↓
SPEC-003
  ├── SPEC-004
  └── SPEC-005
        ↓
      SPEC-006
        ↓
      SPEC-007
        ↓
      SPEC-008
        ↓
  ┌─────┼─────┐
  ↓     ↓     ↓
009   010   011
  └─────┼─────┘
        ↓
      012
        ↓
      013
        ↓
  014 + 015 + 016
        ↓
      017
```

## Princípios globais

1. Fonte original é a autoridade.
2. Banco analítico é reconstruível.
3. Estimativa não deve ser apresentada como cobrança real.
4. Skill disponível não significa skill utilizada.
5. Optimizer não é Agent.
6. Correlação probabilística não deve ser apresentada como exata.
7. Dados ficam locais por padrão.
8. Nenhuma fonte original deve ser modificada.
9. Métricas relevantes devem ser auditáveis.
10. A V1 deve evitar complexidade criada apenas para necessidades futuras.

## Stack definida

- Python 3.11+
- Typer
- SQLite via `sqlite3`
- pytest
- HTML local
- CSV/JSON
