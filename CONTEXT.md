# Boletim Geral de Notícias — Contexto do Projeto

> Cole este arquivo numa nova conversa com o Claude para retomar o projeto com contexto completo.

---

## O que é

**Boletim Geral de Notícias** é um boletim diário com 5 categorias de notícias publicado automaticamente em:

**https://mrvitorino.github.io/daily-news/**

Atualizado **2 vezes ao dia** via GitHub Actions: **08h e 17h (BRT)**.

---

## Repositório

**GitHub:** `mrvitorino/daily-news` · **Branch:** `main` · **GitHub Pages:** via GitHub Actions

---

## Arquitetura

```
daily-news/
├── index.html          # Frontend da revista (tema escuro, Inter)
├── generate_news.py    # Gerador de notícias com Gemini
├── news-data.json      # Dados gerados (commitado a cada edição)
├── CONTEXT.md          # Este arquivo
└── .github/workflows/daily-news.yml
```

### Fluxo de geração (generate_news.py)

**4 funções de busca temática independentes** (cada uma faz 3 sub-buscas):
- `buscar_politica` → até 20 notícias de política
- `buscar_economia` → até 20 notícias de economia
- `buscar_cultura`  → até 20 notícias de cultura
- `buscar_tecnologia` → até 20 notícias de tecnologia
- `buscar_entretenimento` → até 20 itens de streaming/cinema

**3 passos por categoria** (zero JSON intermediário — resolve erros de parse):
1. **Passo A** — `gemini_search()` com `google_search` tool → retorna blocos de texto com delimitadores `##INICIO## ... ##FIM##`
2. **Passo B** — `parse_blocos()` com regex extrai campos (TITULO>>, FONTE>>, etc.) sem nenhum `json.loads`
3. **Passo C** — `gerar_texto()` sem ferramentas → texto com `RESUMO>>`, `PARAGRAFO1>>`, `PARAGRAFO2>>`, `PARAGRAFO3>>`

**Serialização final:** só `json.dump()` nativo do Python — o Gemini nunca produz JSON.

### Por que zero JSON intermediário
O Gemini com `google_search` não aceita `response_mime_type="application/json"` (400 INVALID_ARGUMENT).
Sem a ferramenta, o JSON schema ainda corromperia com aspas em títulos/resumos jornalísticos.
Solução: delimitadores inventados (`##INICIO##`, `TITULO>>`) que nunca aparecem em notícias.

---

## Secret necessário

- `GEMINI_API_KEY` — Google AI Studio ([aistudio.google.com/apikey](https://aistudio.google.com/apikey))
- Projeto Google Cloud com **faturamento ativado** (Gemini 2.5 Flash: gratuito até 1.500 req/dia)

---

## APIs do frontend (sem key, sem custo)

| Dado | API |
|------|-----|
| USD/BRL, EUR/BRL | `economia.awesomeapi.com.br` |
| IPCA acum. 12m | BCB série 13522 |
| Selic meta a.a. | BCB série 432 |
| Bovespa + ações BR | Yahoo Finance via proxies (`^BVSP`, PETR4.SA, VALE3.SA, ITUB4.SA, BBDC4.SA, ABEV3.SA) |
| S&P 500 + ações US | Yahoo Finance (`^GSPC`, AAPL, MSFT, NVDA, AMZN, GOOGL) |
| Euro Stoxx 50 | Yahoo Finance (`^STOXX50E`, ASML, SAP, SIE.DE, MC.PA, SAN) |

**Proxies Yahoo em cascata:** allorigins.win → corsproxy.io → thingproxy.freeboard.io

---

## Categorias e fontes

### 5 categorias
| Categoria | Cor | Máx. notícias |
|-----------|-----|--------------|
| Política | Azul `#4f8ef7` | 20 |
| Economia | Verde `#3ecf6e` | 20 |
| Cultura | Dourado `#e8b84b` | 20 |
| Tecnologia | Roxo `#a78bfa` | 20 |
| Entretenimento | Rosa `#f472b6` | 20 |

### Fontes aceitas
Agência Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadão, Valor Econômico,
ICL Notícias, Intercept Brasil, Revista Fórum, Brasil de Fato, Carta Capital,
CNN Brasil, Metrópoles, Reuters Brasil, El País Brasil, Nexo Jornal, Bloomberg Línea,
Agência Pública, Piauí, Época, IstoÉ, Exame, InfoMoney, Opera Mundi, Band News,
Correio Braziliense, AFP Brasil, R7 Notícias, The Verge, Wired, TechCrunch,
Ars Technica, Canaltech, TecMundo, Olhar Digital, Variety, Hollywood Reporter,
Deadline, Screen Rant, Rolling Stone Brasil, Billboard Brasil.

### Fontes proibidas
Jovem Pan, Brasil Paralelo, Terça Livre, Pleno News, O Antagonista, e qualquer veículo de extrema-direita.

---

## Estrutura do news-data.json

```json
{
  "resumo_editorial": "string",
  "noticias": [{
    "titulo": "string",
    "fonte": "string",
    "categoria": "Politica|Economia|Cultura|Tecnologia|Entretenimento",
    "url": "string (vazio se não encontrado)",
    "importancia": 1-10,
    "resumo": "string — 2 frases",
    "corpo": "string — 3 parágrafos separados por \\n\\n"
  }],
  "por_categoria": {"Politica": N, "Economia": N, ...},
  "generated_at": "2026-05-30T17:00:00",
  "edition_label": "Edicao Vespertina (17h)",
  "date_display": "SÁBADO, 30 DE MAIO DE 2026"
}
```

---

## Design do frontend

- **Nome:** Boletim Geral de Notícias
- **Tema:** escuro `#0d0d0f`
- **Fonte:** Inter (sem serifa)
- **Layout notícias:** hero → grid 2 col → lista numerada
- **Expansão:** botão "Ler notícia completa ▾" abre painel inline com parágrafos + link "Abrir fonte original"
- **Navegação:** barra sticky de categorias com contadores

---

## Histórico de decisões técnicas

| Decisão | Motivo |
|---------|--------|
| Zero JSON intermediário | Gemini corrompe JSON com texto jornalístico (aspas em títulos) |
| Delimitadores `##INICIO##`/`TITULO>>` | Nunca aparecem em notícias reais |
| Buscas por tema separadas | Uma busca de 10 notícias retornava 2-3 e completava com N/A |
| Passo C sem ferramentas | `google_search` + `response_mime_type` = 400 INVALID_ARGUMENT |
| BCB para IPCA/SELIC | AwesomeAPI não tem esses endpoints |
| brapi.dev removido | Falhava; substituído por Yahoo Finance com 3 proxies |
| PIB substituído por IPCA+SELIC | API IBGE retorna decimais pt-BR causando NaN |
| 2× por dia (era 3×) | Volume de conteúdo aumentou (5 categorias × 20 notícias) |

---

## Token GitHub para Claude fazer push

Token clássico com escopos `repo` + `workflow`.
**Não armazene o token aqui.** Cole na conversa quando precisar de alterações via Claude.
