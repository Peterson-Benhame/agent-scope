# SPEC-011 — Analytics de Agentes, Skills e Tools

## Objetivo

Identificar e analisar componentes que participaram das sessões sem gerar falsos positivos.

## Agentes

Detectar somente por evidência:

- spawn;
- metadata;
- eventos de colaboração;
- relação parent/child explícita.

Métricas:

```text
sessions_by_agent
agent_invocations
subagents_created
tool_calls_by_agent_when_correlatable
tokens_by_agent_when_correlatable
```

Se tokens não puderem ser atribuídos a um agente com segurança, deixar sem atribuição.

## Skills

Estados:

```text
available
loaded
invoked
```

Exemplos de evidência:

- `available`: listado no catálogo.
- `loaded`: arquivo SKILL.md lido.
- `invoked`: anúncio explícito ou evento inequívoco de uso.

Métricas:

```text
sessions_with_skill_available
sessions_with_skill_loaded
sessions_with_skill_invoked
```

## Tools

Categorias iniciais:

```text
shell
filesystem
github
browser
mcp
agent_collaboration
other
```

Métricas:

```text
tool_calls
success_rate
failure_rate
average_duration
input_size
output_size
calls_per_session
```

## MCP

MCP é Tool/Provider, não Agent.

## Headroom

Headroom permanece Optimizer.

## Critérios de aceite

- [ ] agentes dependem de evidência;
- [ ] skills têm estados distintos;
- [ ] tools possuem categorias;
- [ ] MCP não é tratado como agent;
- [ ] Headroom não aparece no ranking de agentes;
- [ ] atribuições incertas permanecem não atribuídas.
