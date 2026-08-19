# SPEC-013 — CLI e Workflow Operacional

## Objetivo

Fornecer uma interface simples para coleta, diagnóstico, análise e geração de relatórios.

## Comandos

### agentscope collect

Responsável por:

- detectar fontes;
- importar alterações;
- normalizar;
- persistir;
- reportar erros parciais.

Opções previstas:

```text
--codex-home
--headroom-home
--database
--source
--full-rescan
```

### agentscope status

Mostrar:

- fontes;
- banco;
- última importação;
- quantidade de sessões;
- erros;
- arquivos pendentes.

### agentscope analyze

Executar/atualizar agregações.

Filtros:

```text
--from
--to
--project
--model
```

### agentscope report

Gerar HTML.

Opções:

```text
--from
--to
--output
--safe
```

### agentscope export

Gerar CSV/JSON.

## Exit codes

```text
0 = sucesso
1 = sucesso parcial
2 = erro de configuração
3 = erro de banco
4 = erro inesperado
```

## Regras

1. Comandos devem ser não destrutivos.
2. `--full-rescan` reprocessa, mas não apaga fonte.
3. Mensagens devem diferenciar warnings de failures.
4. Saída estruturada futura pode ser adicionada, mas não é requisito V1.

## Critérios de aceite

- [ ] todos os comandos existem;
- [ ] status é diagnóstico útil;
- [ ] filtros de período funcionam;
- [ ] exit codes são consistentes;
- [ ] nenhum comando altera Codex/Headroom.
