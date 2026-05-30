# PANORAMA — Boletim Diário Brasil

Página de revista com as principais notícias de **política e economia** do Brasil. Atualizada automaticamente **3 vezes ao dia** via GitHub Actions + Anthropic API.

## 🕐 Horários de atualização

| Edição           | Horário (BRT) |
|------------------|---------------|
| Matutina         | 08h00         |
| Meio-Dia         | 12h00         |
| Vespertina       | 17h00         |

## 📰 Fontes monitoradas

- ICL Notícias
- Intercept Brasil
- Revista Fórum
- Folha de S.Paulo
- Agência Brasil

## ⚙️ Configuração (passo a passo)

### 1. Adicionar secret da API

No GitHub: **Settings → Secrets and variables → Actions → New repository secret**

- Nome: `ANTHROPIC_API_KEY`
- Valor: sua chave da API Anthropic (obtenha em [console.anthropic.com](https://console.anthropic.com))

### 2. Ativar GitHub Pages

No GitHub: **Settings → Pages**

- Source: **GitHub Actions**
- Salvar

### 3. Rodar manualmente pela primeira vez

No GitHub: **Actions → Gerar e Publicar Boletim Diário → Run workflow**

Após a primeira execução, a página estará disponível em:
```
https://mrvitorino.github.io/daily-news/
```

## 📁 Estrutura

```
daily-news/
├── index.html          # Página da revista
├── generate_news.py    # Script Python que gera news-data.json
├── news-data.json      # Dados gerados (atualizado a cada edição)
└── .github/
    └── workflows/
        └── daily-news.yml  # Workflow do GitHub Actions
```

## 🔄 Como funciona

1. GitHub Actions acorda nos horários programados
2. Roda `generate_news.py` que chama a API da Anthropic com busca web
3. A API busca notícias nas fontes configuradas e retorna JSON estruturado
4. O `news-data.json` é commitado no repositório
5. A página é publicada no GitHub Pages
6. Ao abrir a página, o `index.html` lê o `news-data.json` e renderiza a revista

## 💰 Custo estimado

Cada geração usa ~1 chamada à API Anthropic com web search. Com 3 edições/dia:
- ~90 chamadas/mês
- Custo estimado: **< $1/mês** com o plano padrão da Anthropic
