# SPEC-001 — Visão Geral e Arquitetura

## Problema

Dados de uso do Codex, Headroom e futuros agentes ficam distribuídos em arquivos locais e formatos específicos de fornecedor.

Sem uma camada analítica própria, não é possível responder de forma consistente:

- quanto foi utilizado;
- quanto foi economizado;
- quais modelos/agentes/skills/tools participaram;
- quais projetos concentram maior consumo;
- como custo e eficiência evoluem ao longo do tempo.

## Objetivo

Definir a arquitetura da V1 do AgentScope como uma ferramenta local, read-only em relação às fontes, capaz de coletar, normalizar, persistir, analisar e reportar dados históricos.

## Arquitetura

```text
Sources
  ├── Codex
  └── Headroom
        ↓
Collectors
        ↓
Normalizer
        ↓
Domain Model
        ↓
SQLite
        ↓
Analytics
        ↓
Reports / Exports / CLI
```

## Componentes

### Sources

Arquivos e endpoints que representam a evidência original.

### Collectors

Adaptadores específicos de fornecedor.

Responsabilidades:

- localizar;
- ler;
- interpretar;
- preservar metadados de origem.

Não devem conter regras analíticas.

### Normalizer

Transforma estruturas específicas em eventos/entidades genéricas.

### Domain

Representa conceitos independentes de fornecedor.

### Storage

Persistência local reconstruível.

### Analytics

Agregações de uso, custo, eficiência e atividade.

### Reporting

CSV, JSON e HTML.

### CLI

Interface operacional da V1.

## Regras arquiteturais

1. `collectors/codex` pode conhecer o formato Codex.
2. `collectors/headroom` pode conhecer o formato Headroom.
3. `domain`, `storage`, `analytics` e `reporting` não devem depender diretamente de classes específicas de Codex/Headroom.
4. Nenhum collector modifica arquivos de origem.
5. Nenhuma análise depende de rede para funcionar.
6. O proxy Headroom pode estar desligado durante análise histórica.
7. Não criar servidor HTTP na V1.
8. Não criar abstração de plugin dinâmica na V1.
9. Não criar extensão VS Code nesta fase.

## Estrutura de diretórios

```text
agentscope/
├── src/agentscope/
│   ├── cli/
│   ├── collectors/
│   │   ├── codex/
│   │   └── headroom/
│   ├── normalization/
│   ├── domain/
│   ├── storage/
│   ├── analytics/
│   ├── reporting/
│   └── config/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
├── data/
├── reports/
├── docs/
└── pyproject.toml
```

## Fora de escopo

- recomendação de agente;
- seleção de modelo;
- roteamento;
- alteração de prompt;
- controle do Headroom;
- alteração do Codex;
- extensão VS Code;
- dashboard em tempo real;
- sincronização em nuvem.

## Critérios de aceite

- [ ] arquitetura separa fonte, coleta, normalização, persistência, analytics e reporting;
- [ ] código específico de fornecedor fica isolado em collectors;
- [ ] fontes são tratadas como read-only;
- [ ] SQLite é reconstruível;
- [ ] funcionamento histórico não depende do proxy Headroom ativo;
- [ ] nenhuma API HTTP é criada;
- [ ] nenhuma funcionalidade futura altera o escopo da V1.
