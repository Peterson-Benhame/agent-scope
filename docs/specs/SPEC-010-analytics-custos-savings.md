# SPEC-010 — Analytics de Custos e Savings

## Objetivo

Calcular e apresentar custo e economia sem confundir estimativa com cobrança real.

## Categorias

### Estimated Raw Cost

Estimativa teórica sem otimização.

### Observed Cost

Valor explicitamente fornecido por uma fonte.

### Estimated Cost After Optimization

Estimativa após cache/compressão quando os dados permitirem.

### Savings

Separar:

```text
compression_savings_usd
cache_savings_usd
total_savings_usd
```

## Pricing

Tabela de preço deve possuir:

```text
provider
model
input_price
cached_input_price
output_price
reasoning_price_if_applicable
currency
effective_from
effective_to
source
version
```

## Regra crítica

Preço desconhecido:

```text
NULL
```

Nunca:

```text
0
```

## Headroom

Savings fornecidos pelo Headroom podem ser classificados como:

```text
optimizer_observed
```

Não chamar automaticamente de "valor efetivamente cobrado a menos".

## Relatórios

Mostrar claramente:

```text
Estimado
Observado
Economia estimada
Economia reportada pelo optimizer
```

## Critérios de aceite

- [ ] custo desconhecido permanece NULL;
- [ ] pricing possui versão/fonte;
- [ ] compressão e cache são separados;
- [ ] estimado e observado não são misturados;
- [ ] agregações por projeto/modelo/período funcionam.
