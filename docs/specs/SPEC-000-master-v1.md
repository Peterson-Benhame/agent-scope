# AgentScope — Especificação Técnica V1

**Status:** Proposta aprovada para especificação  
**Data:** 2026-08-18  
**Escopo:** Observabilidade e análise histórica de execuções de agentes, modelos, skills, tools/MCPs e otimizadores.  
**Primeiras fontes:** OpenAI Codex e Headroom.

---

## 1. Visão geral

AgentScope é uma ferramenta local e independente de fornecedor para coletar, normalizar, armazenar e analisar dados de execução de agentes de desenvolvimento e ferramentas relacionadas.

A V1 será exclusivamente analítica. Ela não interfere em prompts, não escolhe modelos, não roteia agentes, não modifica execuções e não aplica otimizações.

O Codex será a primeira fonte de dados. O Headroom será a primeira fonte de dados de otimização.

O núcleo deve permanecer genérico para permitir novas fontes no futuro.

Fluxo:

```text
Fontes locais
    ↓
Collector
    ↓
Normalizer
    ↓
SQLite
    ↓
Analytics
    ↓
Relatórios
```

---

## 2. Objetivos da V1

A V1 deve responder, com dados históricos:

- quantas sessões foram executadas;
- quantos prompts e respostas ocorreram;
- quais projetos consumiram mais recursos;
- quais modelos foram utilizados;
- quais agentes e subagentes participaram;
- quais skills foram carregadas ou utilizadas;
- quais ferramentas e MCPs foram chamados;
- quantos tokens foram submetidos, reutilizados por cache e gerados;
- quanto contexto foi comprimido;
- quanto foi economizado pelo Headroom;
- qual foi o custo estimado bruto;
- qual foi o custo estimado após otimizações;
- como consumo, custo e economia evoluíram por período;
- quais sessões apresentaram maior custo, duração ou volume de ferramentas.

---

## 3. Não objetivos da V1

A V1 não deve:

- recomendar automaticamente agente;
- recomendar automaticamente modelo;
- trocar modelo;
- alterar prompts;
- interferir no Codex;
- controlar Headroom;
- implementar roteamento;
- executar agentes;
- modificar arquivos de sessão;
- modificar dados originais;
- depender de serviço em nuvem;
- exigir servidor HTTP;
- implementar extensão do VS Code.

A futura extensão do VS Code consumirá os dados produzidos pelo núcleo.

---

## 4. Conceitos do domínio

### 4.1 Source

Sistema que fornece dados brutos.

Exemplos iniciais:

- `codex`
- `headroom`

### 4.2 Session

Uma execução conversacional identificável de um agente.

Exemplo Codex:

```text
01a0170d-5941-7311-8127-90f1a0846d1f
```

### 4.3 Turn

Uma unidade de interação dentro de uma sessão.

### 4.4 Message

Mensagem registrada durante a sessão.

Papéis possíveis:

- user
- assistant
- developer
- system

### 4.5 Agent

Entidade que executa trabalho ou recebe uma tarefa delegada.

Exemplos:

- root
- researcher
- reviewer
- tester
- subagent

### 4.6 Skill

Conjunto de instruções reutilizáveis carregado ou utilizado durante uma execução.

Exemplos:

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `ponytail:ponytail`

### 4.7 Tool

Capacidade invocável pelo agente.

Exemplos:

- shell
- GitHub
- Supabase MCP
- browser
- file tools

### 4.8 Model

Modelo responsável pela inferência.

Exemplos:

- `gpt-5.6-terra`
- `gpt-5.6-luna`

### 4.9 Optimizer

Componente que altera eficiência, tamanho do contexto, cache ou custo sem ser o agente responsável pela tarefa.

Exemplo inicial:

- Headroom

O Headroom não deve ser modelado como Agent.

### 4.10 Project

Projeto ou workspace associado à sessão.

---

## 5. Fontes da V1

### 5.1 Codex

Locais iniciais:

```text
%USERPROFILE%\.codex\session_index.jsonl
%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl
%USERPROFILE%\.codex\attachments\**
```

Os arquivos `rollout-*.jsonl` podem conter:

- metadata da sessão;
- origem;
- workspace;
- provider;
- modelo;
- mensagens;
- instruções;
- AGENTS.md;
- tool calls;
- tool outputs;
- token counts;
- cache;
- eventos;
- subagentes;
- timestamps.

Conteúdo de reasoning criptografado não deve ser descriptografado nem inferido.

### 5.2 Headroom

Locais conhecidos/investigados:

```text
%USERPROFILE%\.headroom\proxy_savings.json
%USERPROFILE%\.headroom\session_stats.jsonl
```

Quando disponíveis, também podem ser coletadas métricas expostas pelo proxy local:

```text
GET /stats
GET /stats-history
```

A V1 deve continuar funcionando sem o proxy ativo usando apenas os arquivos persistidos.

---

## 6. Arquitetura

```text
agentscope/
├── src/
│   └── agentscope/
│       ├── cli/
│       ├── collectors/
│       │   ├── codex/
│       │   └── headroom/
│       ├── normalization/
│       ├── domain/
│       ├── storage/
│       ├── analytics/
│       ├── reporting/
│       └── config/
├── tests/
├── reports/
├── data/
├── docs/
└── pyproject.toml
```

Responsabilidades:

### Collectors

Ler dados brutos sem alterar a origem.

### Normalization

Converter formatos específicos de fornecedor para o modelo interno.

### Domain

Representar conceitos genéricos como Session, Agent, Tool, Model e Cost.

### Storage

Persistência local em SQLite.

### Analytics

Executar agregações e métricas.

### Reporting

Exportar dados e gerar relatório HTML.

### CLI

Fornecer interface operacional da V1.

---

## 7. Estratégia de persistência

A V1 utilizará SQLite.

Arquivo sugerido:

```text
data/agentscope.db
```

Motivos:

- zero infraestrutura externa;
- adequado a análise local;
- consultas SQL simples;
- leitura futura pela extensão do VS Code;
- permite reprocessamento e histórico;
- permite índices e relacionamentos;
- facilita exportação.

Os arquivos originais continuam sendo a fonte primária.

O banco é uma projeção analítica reconstruível.

---

## 8. Modelo de dados inicial

### sources

```text
id
name
type
version
```

### projects

```text
id
name
path
```

### sessions

```text
id
source_id
external_session_id
project_id
started_at
ended_at
originator
provider
model_id
cli_version
raw_file_path
```

### turns

```text
id
session_id
external_turn_id
started_at
ended_at
```

### messages

```text
id
session_id
turn_id
role
phase
timestamp
content
content_type
```

### models

```text
id
provider
name
```

### agents

```text
id
name
type
```

### session_agents

```text
session_id
agent_id
started_at
ended_at
parent_agent_id
```

### skills

```text
id
name
source
version
```

### session_skills

```text
session_id
skill_id
usage_type
first_seen_at
```

`usage_type` deverá distinguir, quando possível:

- available
- loaded
- invoked

Não inferir `invoked` apenas porque a skill estava listada.

### tools

```text
id
name
provider
category
```

### tool_calls

```text
id
session_id
turn_id
tool_id
timestamp
duration_ms
status
input_size
output_size
```

### token_usage

```text
id
session_id
turn_id
timestamp
model_id
input_tokens
cached_input_tokens
cache_write_input_tokens
output_tokens
reasoning_output_tokens
total_tokens
context_window
```

### optimizers

```text
id
name
version
```

### optimizations

```text
id
optimizer_id
session_id
timestamp
model_id
original_tokens
optimized_tokens
tokens_saved
compression_percent
cache_read_tokens
compression_savings_usd
cache_savings_usd
```

### costs

```text
id
session_id
model_id
period_start
period_end
estimated_raw_cost_usd
observed_cost_usd
estimated_cost_after_optimization_usd
compression_savings_usd
cache_savings_usd
total_savings_usd
pricing_source
pricing_version
```

---

## 9. Política de custo

AgentScope não deve apresentar estimativa como cobrança real.

Os valores devem ser classificados.

### Estimated Raw Cost

Quanto a execução teria custado segundo a tabela de preços conhecida, sem considerar otimizações.

### Observed Cost

Valor explicitamente observado em uma fonte confiável, quando existir.

### Estimated Cost After Optimization

Estimativa após aplicar dados conhecidos de cache/compressão.

### Savings

Separar:

```text
compression_savings_usd
cache_savings_usd
total_savings_usd
```

Toda métrica monetária deve registrar:

```text
pricing_source
pricing_version
```

Quando o preço não puder ser determinado com segurança, o custo deve permanecer `NULL`, não zero.

---

## 10. Política de correlação

Codex e Headroom possuem dados independentes.

A correlação deve priorizar identificadores fortes:

1. session ID;
2. turn ID/request ID;
3. timestamp;
4. modelo;
5. projeto;
6. janela temporal.

Uma associação baseada apenas em horário deve possuir indicador de confiança.

Exemplo:

```text
correlation_confidence = exact | high | medium | unknown
```

Nunca apresentar correlação probabilística como exata.

---

## 11. Importação incremental

O Collector deve evitar reprocessar todos os arquivos a cada execução.

Cada fonte importada deve registrar:

```text
path
size
modified_at
content_hash
last_imported_at
```

Se o arquivo não mudou, ele pode ser ignorado.

Se um `rollout.jsonl` ainda estiver sendo escrito, novas linhas devem ser importáveis sem duplicar registros anteriores.

---

## 12. Idempotência

Executar:

```text
agentscope collect
```

duas vezes sobre o mesmo conjunto de arquivos não deve duplicar sessões, mensagens, tool calls ou métricas.

Identificadores externos devem ser utilizados sempre que disponíveis.

---

## 13. CLI V1

Comandos previstos:

```text
agentscope collect
agentscope status
agentscope analyze
agentscope report
agentscope export
```

### collect

Coleta e normaliza novas informações.

### status

Exibe:

- fontes detectadas;
- quantidade de arquivos;
- última importação;
- banco utilizado;
- erros de parsing.

### analyze

Calcula métricas agregadas.

### report

Gera relatório HTML.

### export

Exporta datasets em CSV e JSON.

---

## 14. Datasets de exportação

A V1 deve conseguir gerar pelo menos:

```text
reports/sessions.csv
reports/token_usage.csv
reports/costs.csv
reports/agents.csv
reports/skills.csv
reports/tool_calls.csv
reports/optimizations.csv
reports/usage_by_project.csv
reports/usage_by_model.csv
reports/usage_by_day.csv
```

Além de JSON equivalente para integrações futuras.

---

## 15. Relatório HTML V1

Seções mínimas:

### Resumo

- período;
- sessões;
- turns;
- mensagens;
- tool calls;
- tokens;
- custo;
- economia.

### Tokens

- input;
- cached input;
- output;
- reasoning;
- total;
- tokens economizados.

### Custos

- custo bruto estimado;
- custo observado;
- economia por compressão;
- economia por cache;
- economia total.

### Modelos

- uso por modelo;
- custo por modelo;
- tokens por modelo.

### Projetos

- sessões por projeto;
- tokens por projeto;
- custo por projeto.

### Agents

- agentes detectados;
- sessões;
- quantidade de execuções;
- tokens associados quando possível.

### Skills

- skills disponíveis;
- skills carregadas;
- skills invocadas quando comprovado.

### Tools

- quantidade de chamadas;
- status;
- duração;
- volume de entrada/saída.

### Optimizers

Para Headroom:

- requests;
- tokens antes;
- tokens depois;
- tokens economizados;
- compressão percentual;
- cache reads;
- savings.

### Tendência temporal

- sessões por dia;
- tokens por dia;
- custo por dia;
- economia por dia.

---

## 16. Métricas derivadas

Métricas permitidas na V1:

```text
tokens_per_session
cost_per_session
tool_calls_per_session
cache_ratio
compression_ratio
savings_ratio
sessions_per_project
tokens_per_project
tokens_per_model
cost_per_model
```

Ainda não criar um único "Agent Efficiency Score".

Essa métrica exigirá critérios de qualidade que a V1 não possui.

---

## 17. Qualidade e evidência

Cada métrica deve poder ser rastreada até a fonte original.

Quando possível, registros normalizados devem manter:

```text
source_file
source_line
external_id
```

O relatório poderá futuramente oferecer drill-down.

Princípio:

```text
Relatório
  ↓
registro normalizado
  ↓
evento original
```

---

## 18. Privacidade

Os dados analisados podem conter:

- prompts;
- respostas;
- caminhos locais;
- código;
- logs;
- nomes de projetos;
- conteúdo de attachments.

A V1 será local.

Não enviar dados para serviços externos.

O relatório padrão não precisa incluir o texto integral de prompts e respostas.

Datasets contendo conteúdo textual devem ser opcionais.

Segredos encontrados não devem ser copiados para relatórios por padrão.

---

## 19. Tratamento de dados sensíveis

O Collector não deve modificar a fonte.

O Reporting deve possuir duas categorias:

```text
metadata-safe
full-content
```

`metadata-safe` será o padrão.

O modo seguro deve evitar:

- corpo integral de prompts;
- tool inputs completos;
- tool outputs completos;
- credenciais;
- tokens;
- strings de conexão.

---

## 20. Erros e arquivos incompatíveis

Um arquivo corrompido não deve interromper toda a importação.

Registrar:

```text
source
file
line
error_type
error_message
timestamp
```

O status final deverá diferenciar:

- importação completa;
- importação parcial;
- falha.

---

## 21. Compatibilidade de versões

O schema do Codex pode mudar.

Collectors específicos de fonte não devem vazar detalhes para o domínio.

Exemplo:

```text
Codex rollout vA
      ↓
CodexCollector
      ↓
NormalizedSession
```

O mesmo conceito se aplica ao Headroom.

Campos desconhecidos devem ser ignorados ou armazenados como metadata, sem quebrar o pipeline quando possível.

---

## 22. Testes

A V1 deve possuir testes para:

- parsing de session_meta;
- parsing de mensagens;
- parsing de token_count;
- parsing de tool calls;
- detecção de agent/subagent;
- detecção de skills;
- parsing de Headroom savings;
- correlação;
- idempotência;
- importação incremental;
- custo desconhecido;
- arquivo JSONL parcialmente inválido;
- arquivo em crescimento;
- exportação;
- geração do relatório.

Fixtures devem ser sanitizadas.

Não utilizar históricos pessoais reais nos testes versionados.

---

## 23. Stack

### Linguagem

Python 3.11+

### CLI

Typer

### Banco

SQLite

### ORM / acesso

Preferência inicial: `sqlite3` da biblioteca padrão.

Adicionar ORM somente se a complexidade justificar.

### Relatórios

HTML gerado localmente.

### Testes

pytest

### Configuração

TOML ou configuração simples via ambiente/CLI.

---

## 24. Extensão futura do VS Code

A extensão não faz parte da V1.

A arquitetura deve permitir que futuramente ela consuma:

```text
SQLite
ou
JSON
ou
CLI estruturado
```

Não criar API HTTP antecipadamente.

A decisão de integração será tomada quando a extensão for especificada.

---

## 25. Evoluções futuras possíveis

Fora de escopo, mas suportadas conceitualmente:

- Claude Code;
- GitHub Copilot;
- outros agentes;
- outros proxies/otimizadores;
- extensão VS Code;
- comparação entre agentes;
- comparação entre modelos;
- análise de retrabalho;
- qualidade por tarefa;
- recomendação de modelo;
- recomendação de agente;
- roteamento;
- alertas;
- budgets;
- dashboards em tempo real.

Essas possibilidades não justificam complexidade adicional na V1.

---

## 26. Critérios de aceite

A V1 estará funcional quando:

- [ ] detectar históricos locais do Codex;
- [ ] importar sessões `rollout-*.jsonl`;
- [ ] importar métricas persistidas do Headroom;
- [ ] normalizar sessões, modelos, agentes, skills, tools, tokens e otimizações;
- [ ] persistir os dados em SQLite;
- [ ] executar importação idempotente;
- [ ] suportar atualização incremental;
- [ ] identificar projetos;
- [ ] identificar modelos;
- [ ] identificar agentes/subagentes quando houver evidência;
- [ ] diferenciar skill disponível de skill comprovadamente utilizada;
- [ ] extrair token usage;
- [ ] extrair cache usage;
- [ ] extrair savings do Headroom;
- [ ] representar custos estimados sem tratá-los como cobrança real;
- [ ] exportar CSV;
- [ ] exportar JSON;
- [ ] gerar relatório HTML;
- [ ] oferecer visão por projeto;
- [ ] oferecer visão por modelo;
- [ ] oferecer visão por período;
- [ ] oferecer visão de agentes;
- [ ] oferecer visão de skills;
- [ ] oferecer visão de tools;
- [ ] oferecer visão de Headroom;
- [ ] não modificar arquivos do Codex;
- [ ] não modificar arquivos do Headroom;
- [ ] funcionar sem serviço de nuvem;
- [ ] manter dados localmente.

---

## 27. Princípios do projeto

1. Fonte original é autoridade.
2. Dados normalizados são reconstruíveis.
3. Não confundir estimativa com cobrança.
4. Não confundir disponibilidade de skill com utilização.
5. Não confundir optimizer com agent.
6. Não inferir correlação exata sem identificador confiável.
7. Não depender de uma única ferramenta.
8. Não construir funcionalidades futuras antes da necessidade.
9. Privacidade local por padrão.
10. Toda métrica relevante deve ser auditável.
