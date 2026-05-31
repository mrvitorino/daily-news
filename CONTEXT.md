# Boletim Geral de Notícias — Contexto do Projeto

> Cole este arquivo numa nova conversa com o Claude (chat ou Claude Code) para retomar o projeto com contexto completo.

---

## O que é

**Boletim Geral de Notícias** é um boletim diário com 5 categorias de notícias publicado em:

**https://mrvitorino.github.io/daily-news/**

Atualizado **2 vezes ao dia** via GitHub Actions: **08h e 17h (BRT)**.

---

## Repositório

**GitHub:** `mrvitorino/daily-news` · **Branch:** `main` · **GitHub Pages:** via GitHub Actions

---

## Estrutura de arquivos

```
daily-news/
├── index.html              # Frontend (tema escuro, Inter, 5 categorias)
├── generate_news.py        # Gerador de notícias com Gemini API
├── news-data.json          # Dados gerados a cada edição (commitado automaticamente)
├── CONTEXT.md              # Este arquivo
└── .github/workflows/
    └── daily-news.yml      # Workflow GitHub Actions (2×/dia, 45min timeout)
```

---

## Stack técnica

| Componente | Tecnologia |
|---|---|
| Gerador de notícias | Python 3.12 + Google Gemini 2.5 Flash |
| Busca web | `google_search` tool nativo do Gemini |
| Hospedagem | GitHub Pages |
| CI/CD | GitHub Actions |
| Frontend | HTML/CSS/JS puro (sem frameworks) |

---

## Secret necessário no GitHub

- **`GEMINI_API_KEY`** — Google AI Studio ([aistudio.google.com/apikey](https://aistudio.google.com/apikey))
- Projeto Google Cloud com **faturamento ativado** (Gemini 2.5 Flash: gratuito até 1.500 req/dia com billing ativo)
- Configurar em: `github.com/mrvitorino/daily-news/settings/secrets/actions`

---

## APIs do frontend (sem key, sem custo)

| Dado | API | Endpoint |
|------|-----|---------|
| USD/BRL, EUR/BRL | AwesomeAPI | `economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL` |
| IPCA acum. 12m | BCB série 13522 | `api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/2` |
| Selic meta a.a. | BCB série 432 | `api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/2` |
| Bovespa | Yahoo Finance via proxies | `^BVSP`, PETR4.SA, VALE3.SA, ITUB4.SA, BBDC4.SA, ABEV3.SA |
| S&P 500 | Yahoo Finance via proxies | `^GSPC`, AAPL, MSFT, NVDA, AMZN, GOOGL |
| Euro Stoxx 50 | Yahoo Finance via proxies | `^STOXX50E`, ASML, SAP, SIE.DE, MC.PA, SAN |

**Proxies Yahoo em cascata:** `allorigins.win` → `corsproxy.io` → `thingproxy.freeboard.io`

---

## 5 Categorias e fontes

| Categoria | Cor | Descrição |
|-----------|-----|-----------|
| Política | Azul `#4f8ef7` | Congresso, STF, governo Lula, eleições 2026 |
| Economia | Verde `#3ecf6e` | Mercado, inflação, Selic, emprego, agronegócio |
| Cultura | Dourado `#e8b84b` | Música, arte, literatura, teatro, festivais |
| Tecnologia | Roxo `#a78bfa` | IA, startups, big tech, cibersegurança |
| Entretenimento | Rosa `#f472b6` | Netflix, Amazon, HBO Max, Apple TV+, Disney+ |

### Fontes aceitas
Agência Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadão, Valor Econômico,
ICL Notícias, Intercept Brasil, Revista Fórum, Brasil de Fato, Carta Capital,
CNN Brasil, Metrópoles, Reuters Brasil, El País Brasil, Nexo Jornal, Bloomberg Línea,
Agência Pública, IstoÉ, Exame, InfoMoney, Opera Mundi, Band News, Correio Braziliense,
R7 Notícias, The Verge, Wired, TechCrunch, Ars Technica, Canaltech, TecMundo,
Variety, Hollywood Reporter, Screen Rant, Rolling Stone Brasil.

### Fontes proibidas
Jovem Pan, Brasil Paralelo, Terça Livre, Pleno News, O Antagonista, extrema-direita.

---

## Arquitetura do generate_news.py

### Fluxo por categoria (3 passos)

```
Passo 1: gsearch()  — Gemini + google_search → blocos ##INICIO##...##FIM##
              ↓
         _parse_blocos() — regex duplo (delimitadores → fallback linha a linha)
              ↓
Passo 2: gjson()    — Gemini SEM ferramentas + response_mime_type=json
                      Schema mínimo: titulo, fonte, importancia, url (sem texto livre)
              ↓
Passo 3: gtext()    — Gemini SEM ferramentas, SEM JSON
                      Prompt pede 4 parágrafos numerados 1) 2) 3) 4)
                      Parse por sentençases completas (nunca corta no meio)
```

### Restrições críticas da API Gemini
- `google_search` + `response_mime_type=json` = **400 INVALID_ARGUMENT** (proibido)
- Por isso: busca e formatação JSON são chamadas separadas
- Corpo/resumo NUNCA entram no schema JSON (corrompem com aspas jornalísticas)

### Funções principais
```python
gsearch(client, prompt, max_tokens)   # Gemini + google_search
gjson(client, prompt, schema, max_tokens)  # Gemini + JSON schema (sem tools)
gtext(client, prompt, max_tokens, temp)    # Gemini texto livre (sem tools)
_parse_blocos(txt, categoria)         # Parser duplo: ##INICIO## + fallback linha a linha
p1_buscar(client, categoria, instrucoes, n, today_str)  # Passo 1
p2_meta(client, noticias_raw, categoria)                # Passo 2
p3_corpo(client, noticia)                               # Passo 3
gerar_editorial(client, noticias, today_str)            # Editorial final
```

### Problemas resolvidos e como

| Problema | Causa | Solução |
|----------|-------|---------|
| JSON corrompido com aspas | Texto jornalístico com `"` dentro do schema | Corpo/resumo nunca entram no JSON intermediário |
| `response_mime_type` + `google_search` | API proíbe combinação | Passos separados: busca sem JSON, format sem busca |
| Texto truncado | `max_output_tokens` insuficiente | Passo 3: `max_tokens=2000`, mínimo 300 palavras no prompt |
| Resumo = título repetido | Gemini copiava o título | Prompt: "NAO copie o titulo"; strip de prefixos `RESUMO:`, `Titulo:` |
| N/A nas notícias | Gemini inventava entradas vazias | Filtro explícito + prompt "NUNCA escreva N/A" |
| Entretenimento vazio | Busca genérica sem resultados | Prompt específico por streaming (Netflix, Amazon, HBO Max...) |
| URLs = vertexaisearch | URLs internas do Gemini | Filtro: descarta URLs com "vertexaisearch" ou "grounding-api" |
| Zero blocos ##INICIO## | Gemini ignora delimitadores | Parser fallback linha a linha com TITULO>>, FONTE>> |
| IPCA/SELIC = NaN | AwesomeAPI não tem esses endpoints | Trocado para BCB API oficial (séries 13522 e 432) |
| Ações Bovespa falhavam | brapi.dev instável | Substituído por Yahoo Finance com 3 proxies em cascata |
| PIB com NaN | IBGE retorna decimais pt-BR (`0,8`) | Removido; substituído por IPCA + Selic |

---

## Estrutura do news-data.json

```json
{
  "resumo_editorial": "3 frases sobre o panorama do dia",
  "noticias": [{
    "titulo": "string",
    "fonte": "string",
    "categoria": "Politica|Economia|Cultura|Tecnologia|Entretenimento",
    "importancia": 8,
    "url": "https://... ou string vazia",
    "resumo": "2 frases (não repete o título)",
    "corpo": "3 parágrafos separados por \\n\\n"
  }],
  "por_categoria": {"Politica": 8, "Economia": 8, ...},
  "generated_at": "2026-05-31T08:00:00",
  "edition_label": "Edicao Matutina (08h)",
  "date_display": "DOMINGO, 31 DE MAIO DE 2026"
}
```

---

## Design do frontend (index.html)

- **Nome:** Boletim Geral de Notícias
- **Tema:** escuro (`#0d0d0f`)
- **Fonte:** Inter (sem serifa)
- **Indicadores:** USD/BRL, EUR/BRL, IPCA, Selic + 3 bolsas com top 5 ações cada
- **Navegação:** barra sticky de categorias com contadores por categoria
- **Layout notícias:** hero (1ª) → grid 2 col (2ª e 3ª) → lista numerada (restantes)
- **Expansão:** botão "Ler notícia completa ▾" abre painel inline com corpo em `<p>` + link fonte
- **stripMd():** função JS que limpa markdown residual (`**bold**`, `*italic*`, etc.) em tempo real

---

## Problemas em aberto (a resolver no Claude Code)

1. **Textos ainda truncados** em alguns casos — o Gemini às vezes não respeita `max_output_tokens=2000` e corta no meio de parágrafo. Investigar se o parse por `1) 2) 3) 4)` está capturando corretamente ou se está caindo no fallback de sentençases que corta.

2. **Links quebrados** — algumas URLs retornadas pelo Gemini levam a páginas 404. Precisaria validar URLs antes de salvar (HEAD request ou regex de domínio válido).

3. **Categorias com poucas notícias** — Política e Economia às vezes retornam só 1-2 notícias. O parser fallback pode não estar recuperando bem quando o Gemini não usa ##INICIO##.

4. **Panorama do dia truncado** — `gerar_editorial` com `max_tokens=250` pode estar insuficiente para 3 frases completas.

---

## Como rodar localmente (para debug no Claude Code)

```bash
# Instalar dependências
pip install google-genai

# Exportar API key
export GEMINI_API_KEY=sua_chave_aqui

# Rodar gerador completo
python generate_news.py

# Testar só uma categoria (editar temporariamente CATEGORIAS no script)
# Abrir a página
python -m http.server 8000
# Acessar: http://localhost:8000
```

---

## Token GitHub (para push via API)

Token clássico com escopos `repo` + `workflow`.
**Não armazene o token aqui.** Cole na conversa quando precisar de push via Claude.

---

## Histórico de arquitetura (decisões que NÃO voltam atrás)

| Decisão | Motivo permanente |
|---------|------------------|
| Gemini em vez de Claude API | Claude API custa ~$1.72/execução (web_search = $10/1000 buscas); Gemini é gratuito |
| Zero JSON com texto livre | Todo JSON intermediário com texto jornalístico corrompe inevitavelmente |
| 3 passos separados | Restrição da API: google_search + response_mime_type são mutuamente exclusivos |
| Parse por sentençases completas | Divide texto sem jamais cortar no meio de uma frase |
| BCB API para macro | Única API BR oficial sem CORS e sem key para IPCA e Selic |
| Yahoo Finance com 3 proxies | CORS bloqueia chamada direta; allorigins instável sozinho |
