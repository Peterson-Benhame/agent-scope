# SPEC-017 — Integração Ponta a Ponta e Aceite da V1

## Objetivo

Validar que todos os componentes trabalham juntos sobre um ambiente local real sem modificar as fontes.

## Fluxo de aceite

```text
detect
  ↓
collect Codex
  ↓
collect Headroom
  ↓
normalize
  ↓
correlate
  ↓
persist
  ↓
analyze
  ↓
export
  ↓
report
```

## Cenário principal

Dado:

- histórico Codex existente;
- histórico Headroom existente;
- banco vazio.

Quando:

```text
agentscope collect
agentscope analyze
agentscope export
agentscope report
```

Então:

- sessões são importadas;
- projetos são reconhecidos;
- modelos são reconhecidos;
- tokens são calculados;
- cache é calculado;
- agents/skills/tools aparecem conforme evidência;
- Headroom aparece como optimizer;
- savings são apresentados;
- custos desconhecidos permanecem NULL;
- relatório HTML é criado;
- fontes originais permanecem inalteradas.

## Reexecução

Executar novamente sem mudança:

- não duplica sessões;
- não duplica tokens;
- não duplica tool calls;
- não duplica savings.

## Incremental

Adicionar novas linhas a um rollout:

- apenas novos eventos são importados.

## Ausência do Headroom

Com apenas Codex:

- relatório funciona;
- seção optimizer informa ausência de dados.

## Ausência do Codex

Com apenas Headroom:

- métricas globais de optimizer são importadas;
- correlações de sessão ficam desconhecidas quando necessário.

## Aceite funcional final

- [ ] detectar históricos locais do Codex;
- [ ] importar rollout JSONL;
- [ ] importar métricas Headroom;
- [ ] normalizar dados;
- [ ] persistir SQLite;
- [ ] importação idempotente;
- [ ] atualização incremental;
- [ ] projetos identificados;
- [ ] modelos identificados;
- [ ] agentes identificados com evidência;
- [ ] skills diferenciadas por status;
- [ ] tools contabilizadas;
- [ ] tokens e cache calculados;
- [ ] savings calculados;
- [ ] custos classificados corretamente;
- [ ] CSV gerado;
- [ ] JSON gerado;
- [ ] HTML gerado;
- [ ] safe mode padrão;
- [ ] nenhuma fonte alterada;
- [ ] funcionamento totalmente local.

## Fora de escopo após aceite

Mesmo após a V1, continuam fora desta release:

- VS Code extension;
- roteamento;
- recomendação;
- scoring de qualidade;
- Agent Efficiency Score;
- controle automático de orçamento;
- monitoramento em tempo real;
- upload/sync remoto.
