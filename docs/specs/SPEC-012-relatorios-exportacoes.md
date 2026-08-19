# SPEC-012 — Exportações e Relatório HTML

## Objetivo

Transformar dados normalizados em artefatos legíveis e reutilizáveis.

## Exportações CSV

Gerar:

```text
sessions.csv
token_usage.csv
costs.csv
agents.csv
skills.csv
tool_calls.csv
optimizations.csv
usage_by_project.csv
usage_by_model.csv
usage_by_day.csv
```

## JSON

Gerar os mesmos datasets em JSON.

## Safe mode

Default:

```text
metadata-safe
```

Não incluir:

- prompt integral;
- resposta integral;
- tool input completo;
- tool output completo;
- segredos detectáveis.

Modo opcional:

```text
full-content
```

deve exigir parâmetro explícito.

## Relatório HTML

Seções mínimas:

1. Resumo executivo
2. Uso de tokens
3. Cache
4. Custos
5. Savings
6. Modelos
7. Projetos
8. Agentes
9. Skills
10. Tools/MCPs
11. Optimizers
12. Tendência temporal
13. Qualidade dos dados/discrepâncias

## Visualizações

Gráficos mínimos:

- tokens por dia;
- custo por dia;
- savings por dia;
- distribuição por modelo;
- distribuição por projeto.

## Drill-down

Na V1, links podem apontar para IDs no próprio relatório.

Não expor caminho sensível completo quando safe mode estiver ativo.

## Critérios de aceite

- [ ] CSV é gerado;
- [ ] JSON é gerado;
- [ ] HTML é gerado;
- [ ] safe mode é padrão;
- [ ] relatório distingue estimado/observado;
- [ ] relatório mostra qualidade de correlação e lacunas.
