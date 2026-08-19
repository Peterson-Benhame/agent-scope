# SPEC-014 — Privacidade, Segurança e Sanitização

## Objetivo

Reduzir risco de exposição de prompts, código, credenciais e informações locais.

## Princípio

Local-first.

Nenhum dado deve ser enviado externamente pelo AgentScope V1.

## Dados sensíveis possíveis

- prompts;
- respostas;
- código;
- logs;
- caminhos;
- nomes de projeto;
- attachments;
- credenciais;
- tokens;
- strings de conexão.

## Safe mode

Default obrigatório.

### O que pode aparecer

- IDs;
- contagens;
- timestamps;
- modelo;
- projeto sanitizado;
- agente;
- skill;
- tool;
- métricas.

### O que não deve aparecer por padrão

- texto integral;
- argumentos completos de tools;
- outputs completos;
- authorization headers;
- account IDs;
- connection strings.

## Sanitização

Aplicar mascaramento em exportações.

Não modificar o dado bruto importado.

## Banco

O banco é local e pode conter conteúdo completo se configurado.

Documentar que é dado sensível.

## Logs do AgentScope

Não registrar conteúdo integral de mensagens por padrão.

## Critérios de aceite

- [ ] safe mode é default;
- [ ] headers sensíveis não aparecem em relatório;
- [ ] full-content exige ação explícita;
- [ ] logs internos não vazam prompts;
- [ ] nenhuma chamada de rede é necessária.
