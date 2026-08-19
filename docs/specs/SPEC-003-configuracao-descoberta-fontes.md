# SPEC-003 — Configuração e Descoberta de Fontes

## Objetivo

Permitir que AgentScope descubra as fontes locais com defaults seguros e caminhos configuráveis.

## Defaults Windows

Codex:

```text
%USERPROFILE%\.codex\session_index.jsonl
%USERPROFILE%\.codex\sessions\
%USERPROFILE%\.codex\attachments\
```

Headroom:

```text
%USERPROFILE%\.headroom\proxy_savings.json
%USERPROFILE%\.headroom\session_stats.jsonl
```

## Configuração

Precedência:

1. parâmetro CLI;
2. arquivo local de configuração;
3. variável de ambiente;
4. default da plataforma.

## Requisitos

A configuração deve permitir:

```text
codex_home
headroom_home
database_path
reports_path
safe_mode
timezone
```

## Detecção

`agentscope status` deve informar:

- fonte detectada;
- caminho;
- acessibilidade;
- quantidade de arquivos relevantes;
- última modificação;
- banco configurado.

## Regras

1. Não criar diretório dentro de `.codex` ou `.headroom`.
2. Não exigir que Headroom esteja instalado.
3. Ausência de uma fonte não impede uso das demais.
4. Caminhos inexistentes devem gerar estado `not_found`, não exception global.
5. Não inferir `%USERPROFILE%` quando o usuário informar caminho explícito.

## Cenários

- Codex presente, Headroom ausente.
- Headroom presente, Codex ausente.
- Ambos presentes.
- caminho customizado.
- caminho sem permissão.
- banco em diretório não gravável.

## Critérios de aceite

- [ ] defaults Windows funcionam;
- [ ] caminhos customizados funcionam;
- [ ] fontes independentes podem estar ausentes;
- [ ] status mostra diagnóstico claro;
- [ ] nenhuma fonte é modificada.
