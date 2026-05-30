# Panorama Brasil — Contexto do Projeto

> Cole este arquivo numa nova conversa com o Claude para retomar o projeto com contexto completo.

---

## O que é

**Panorama Brasil** é um boletim diário de notícias sobre política e economia brasileira publicado automaticamente em:

**https://mrvitorino.github.io/daily-news/**

Atualizado 3 vezes ao dia via GitHub Actions: **08h, 12h e 17h (BRT)**.

---

## Repositório

**GitHub:** `mrvitorino/daily-news`
**Branch:** `main`
**GitHub Pages:** ativado via GitHub Actions

---

## Arquitetura

```
daily-news/
├── index.html          # Página da revista (tema escuro, Inter sem serifa)
├── generate_news.py    # Script Python que gera news-data.json
├── news-data.json      # Dados gerados a cada edição (commitado automaticamente)
├── CONTEXT.md          # Este arquivo
└── .github/
    └── workflows/
        └── daily-news.yml  # Workflow GitHub Actions (3×/dia)
```

### Fluxo de geração
1. GitHub Actions acorda nos horários programados
2. `generate_news.py` roda em 2 passos:
   - **Passo A:** chama Gemini 2.5 Flash **com** `google_search` → retorna texto livre com as notícias
   - **Passo B:** chama Gemini 2.5 Flash **sem** ferramentas → converte texto em JSON estruturado com `response_mime_type="application/json"`
   - Separação obrigatória: a API Gemini não permite `google_search` + `response_mime_type` simultaneamente
3. `news-data.json` é commitado no repositório
4. GitHub Pages publica automaticamente

---

## APIs e Secrets

### Secret necessário no GitHub
- `GEMINI_API_KEY` — chave do Google AI Studio ([aistudio.google.com/apikey](https://aistudio.google.com/apikey))
- O projeto Google Cloud associado deve ter **faturamento ativado** (o modelo `gemini-2.5-flash` é gratuito até 1.500 req/dia com billing ativo)

### APIs usadas no frontend (sem key, sem custo)
| Dado | API | URL |
|------|-----|-----|
| USD/BRL, EUR/BRL | AwesomeAPI | `economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL` |
| IPCA acum. 12m | Banco Central (série 13522) | `api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/2` |
| Taxa Selic | Banco Central (série 432) | `api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/2` |
| Bovespa + ações BR | Yahoo Finance via proxies | `^BVSP`, `PETR4.SA`, `VALE3.SA`, `ITUB4.SA`, `BBDC4.SA`, `ABEV3.SA` |
| S&P 500 + ações US | Yahoo Finance via proxies | `^GSPC`, `AAPL`, `MSFT`, `NVDA`, `AMZN`, `GOOGL` |
| Euro Stoxx 50 + ações EU | Yahoo Finance via proxies | `^STOXX50E`, `ASML`, `SAP`, `SIE.DE`, `MC.PA`, `SAN` |

### Proxies Yahoo Finance (em cascata)
1. `api.allorigins.win`
2. `corsproxy.io`
3. `thingproxy.freeboard.io`

---

## Fontes de notícias

### Fontes aceitas (priorizadas)
Agência Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadão, Valor Econômico,
ICL Notícias, Intercept Brasil, Revista Fórum, Brasil de Fato, Carta Capital,
CNN Brasil, Band News, Metrópoles, Reuters Brasil, AFP Brasil, El País Brasil,
Agência Pública, Piauí, Época, IstoÉ, Exame, InfoMoney, Bloomberg Línea,
Nexo Jornal, The Intercept Brasil, Correio Braziliense, Opera Mundi, Outras Palavras

### Fontes explicitamente proibidas
Jovem Pan, Brasil Paralelo, Terça Livre, Pleno News, O Antagonista,
Gazeta do Povo (seção de opinião), Oeste, Cruzsoé, e qualquer veículo
de orientação editorial de extrema-direita.

---

## Estrutura do news-data.json

```json
{
  "resumo_editorial": "string — panorama do dia em 2-3 frases",
  "noticias": [
    {
      "titulo": "string",
      "fonte": "string",
      "categoria": "Política | Economia | Internacional",
      "resumo": "string — 2-3 frases",
      "corpo": "string — 3-4 parágrafos separados por \\n\\n",
      "url": "string — URL do artigo ou vazio",
      "importancia": 1-10
    }
  ],
  "generated_at": "2026-05-30T17:00:00",
  "edition_label": "Edição Vespertina (17h)",
  "date_display": "SÁBADO, 30 DE MAIO DE 2026"
}
```

---

## Design do frontend

- **Tema:** escuro (`#0d0d0f` background)
- **Fonte:** Inter (sem serifa)
- **Cores de texto:** `--text: #f0f0f8`, `--text2: #c8c8de`, `--text3: #8888a8`
- **Acento:** azul `#4f8ef7`
- **Layout notícias:** hero (1ª notícia grande) → grid 2 colunas (2ª e 3ª) → lista numerada (restantes)
- **Expansão:** cada notícia tem botão "Ler notícia completa ▾" que expande o `corpo` inline

---

## Histórico de decisões técnicas relevantes

| Decisão | Motivo |
|---------|--------|
| Gemini em 2 passos (busca + formatação) | API proíbe `google_search` + `response_mime_type` simultaneamente |
| BCB API para IPCA/SELIC | AwesomeAPI não tem esses endpoints; BCB é oficial e sem CORS |
| Yahoo Finance com 3 proxies | CORS bloqueia chamada direta; allorigins instável |
| brapi.dev removido | Falhava com frequência para ações BR; substituído por Yahoo |
| PIB removido | API IBGE com formato de número pt-BR (`0,8`) causava NaN; substituído por IPCA+SELIC |
| Corpo em passo separado | JSON com 10 notícias + corpo longo (~43k chars) corrompía o parse |
| Separador `\|` no corpo | Quebras de linha literais dentro de JSON causavam erros de parse |

---

## Como fazer alterações

### Adicionar/remover fontes
Edite o prompt em `generate_news.py`, função `search_noticias()`.

### Mudar horários de atualização
Edite os `cron` em `.github/workflows/daily-news.yml`. Lembre: horários em UTC (BRT = UTC-3).

### Alterar design
Edite `index.html`. As variáveis CSS ficam no bloco `:root { }` no topo do `<style>`.

### Adicionar novos indicadores de mercado
Em `index.html`, adicione um card em `.macro-row` e a função de fetch correspondente em `<script>`.

### Testar localmente
```bash
# Instalar dependências
pip install google-genai

# Exportar API key
export GEMINI_API_KEY=sua_chave_aqui

# Rodar gerador
python generate_news.py

# Abrir index.html no browser (precisa de servidor local para fetch funcionar)
python -m http.server 8000
# Acesse: http://localhost:8000
```

### Rodar workflow manualmente
GitHub → Actions → "Gerar e Publicar Boletim Diário" → Run workflow

---

## Token GitHub para Claude fazer push

O token clássico com escopo `repo` + `workflow` foi usado para publicar arquivos via API.
**Não armazene o token aqui.** Cole-o na conversa quando precisar fazer alterações via Claude.
