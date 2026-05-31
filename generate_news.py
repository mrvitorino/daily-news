#!/usr/bin/env python3
"""
generate_news.py — Boletim Geral de Noticias
Migrado para Claude API (claude-sonnet-4-6) com web_search nativo.
Uma chamada por categoria retorna JSON estruturado diretamente.
"""

import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    BRASILIA = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA = timezone(timedelta(hours=-3))

import anthropic

OUTPUT   = "news-data.json"
MODEL    = "claude-sonnet-4-6"
MAX_NEWS = 20   # por categoria

WEEKDAYS_PT = {
    "Monday":"segunda-feira","Tuesday":"terca-feira","Wednesday":"quarta-feira",
    "Thursday":"quinta-feira","Friday":"sexta-feira","Saturday":"sabado","Sunday":"domingo"
}
MONTHS_PT = {
    1:"janeiro",2:"fevereiro",3:"marco",4:"abril",5:"maio",6:"junho",
    7:"julho",8:"agosto",9:"setembro",10:"outubro",11:"novembro",12:"dezembro"
}

def format_date_pt(dt):
    wd = WEEKDAYS_PT.get(dt.strftime("%A"), dt.strftime("%A"))
    mo = MONTHS_PT.get(dt.month, str(dt.month))
    return f"{wd}, {dt.day} de {mo} de {dt.year}"

def get_edition_label(h):
    return "Edicao Matutina (08h)" if h < 12 else "Edicao Vespertina (17h)"

FONTES_OK = (
    "Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao, Valor Economico, "
    "ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato, Carta Capital, "
    "CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal, Bloomberg Linea, "
    "Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney, Opera Mundi, Band News, "
    "Correio Braziliense, AFP Brasil, R7 Noticias, The Verge, Wired, TechCrunch, "
    "Ars Technica, MIT Technology Review, Canaltech, TecMundo, Olhar Digital, "
    "Variety, Hollywood Reporter, Deadline, Screen Rant, Rolling Stone Brasil, "
    "Billboard Brasil, IGN, Polygon"
)
FONTES_NO = "Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista"

# ── SCHEMA JSON ──────────────────────────────────────────────────────────────
# Retornado pelo Claude diretamente em uma unica chamada com web_search
SCHEMA = """{
  "resumo_categoria": "2-3 frases sobre o panorama da categoria",
  "noticias": [
    {
      "titulo": "titulo claro e direto da noticia",
      "fonte": "nome do veiculo de comunicacao",
      "resumo": "2 frases descrevendo o fato e sua importancia",
      "corpo": "3 paragrafos completos separados por \\n\\n. Cada paragrafo minimo 60 palavras.",
      "url": "URL direta do artigo ou string vazia",
      "importancia": 8
    }
  ]
}"""

# ── BUSCA POR CATEGORIA ───────────────────────────────────────────────────────
def buscar_categoria(client, categoria, instrucoes_busca, today_str, max_n=MAX_NEWS):
    print(f"[..] Buscando: {categoria} ({max_n} noticias)...")

    prompt = f"""Hoje e {today_str}. Voce e um editor jornalistico experiente.

Use a ferramenta de busca web para encontrar as {max_n} noticias mais relevantes
sobre {instrucoes_busca} publicadas nas ultimas 48 horas.

FONTES ACEITAS: {FONTES_OK}
FONTES PROIBIDAS: {FONTES_NO}

Para cada noticia encontrada:
- Busque o artigo completo para escrever um corpo rico e detalhado
- O campo "corpo" deve ter 3 paragrafos completos separados por linha em branco (\\n\\n)
- Cada paragrafo deve ter minimo 60 palavras
- NAO use markdown (sem asteriscos, sem #, sem negrito)
- Use apenas aspas simples se precisar de aspas
- Se a URL real do artigo estiver disponivel nos resultados da busca, inclua-a

Retorne SOMENTE o seguinte JSON, sem texto antes ou depois:
{SCHEMA}

Substitua os exemplos pelos dados reais. Retorne exatamente {max_n} noticias.
Se nao encontrar {max_n} noticias, retorne quantas encontrar (minimo 3).
NUNCA invente noticias. NUNCA retorne campos com valor "N/A"."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extrai o texto da resposta (blocos type=text apos tool_use)
    texto = ""
    for block in resp.content:
        if block.type == "text":
            texto += block.text

    print(f"   Resposta: {len(texto)} chars")

    # Parse JSON — o Claude retorna JSON limpo diretamente
    texto = texto.strip()
    # Remove possiveis fences de codigo
    texto = re.sub(r'^```(?:json)?\s*', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\s*```\s*$', '', texto, flags=re.MULTILINE)

    s = texto.find('{')
    e = texto.rfind('}')
    if s == -1 or e == -1:
        raise RuntimeError(f"JSON nao encontrado na resposta de {categoria}")

    data = json.loads(texto[s:e+1])
    noticias = data.get("noticias", [])

    # Filtra invalidas e normaliza
    validas = []
    for n in noticias:
        titulo = n.get("titulo", "").strip()
        if not titulo or len(titulo) < 8:
            continue
        if any(x in titulo.lower() for x in ["n/a", "nao foi", "nao encontr", "exemplo"]):
            print(f"   [SKIP] {titulo[:50]}")
            continue
        # Garante categoria correta
        n["categoria"] = categoria
        # Normaliza url
        url = n.get("url", "")
        if not isinstance(url, str) or not url.startswith("http"):
            n["url"] = ""
        # Garante importancia numerica
        try:
            n["importancia"] = min(10, max(1, int(n.get("importancia", 5))))
        except Exception:
            n["importancia"] = 5
        # Remove markdown residual do corpo e resumo
        n["corpo"]  = _strip_md(n.get("corpo", ""))
        n["resumo"] = _strip_md(n.get("resumo", ""))
        validas.append(n)

    print(f"   {len(validas)} noticias validas")
    return validas, data.get("resumo_categoria", "")


def _strip_md(txt):
    """Remove markdown residual."""
    if not txt:
        return ""
    txt = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', txt)
    txt = re.sub(r'#{1,6}\s+', '', txt)
    txt = re.sub(r'`([^`]+)`', r'\1', txt)
    txt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
    txt = re.sub(r'(?i)\*{0,2}fonte\s*:\s*[^|\n*]+(\|[^\n*]+)?\*{0,2}', '', txt)
    txt = re.sub(r'(?i)\*{0,2}categoria\s*:\s*[^\n*]+\*{0,2}', '', txt)
    return txt.strip()


# ── EDITORIAL GERAL ───────────────────────────────────────────────────────────
def gerar_editorial(client, noticias, today_str):
    titulos = "\n".join(
        f"- {n['titulo']}"
        for n in noticias
        if n["categoria"] in ["Politica", "Economia"]
    )[:800]

    prompt = (
        f"Com base nestas noticias brasileiras de hoje ({today_str}):\n{titulos}\n\n"
        "Escreva um resumo editorial de 3 frases completas sobre o panorama do dia no Brasil. "
        "Texto corrido, sem markdown, sem aspas duplas, em portugues brasileiro formal."
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        txt = resp.content[0].text.strip()
        return _strip_md(txt)
    except Exception as e:
        print(f"   [WARN] editorial: {e}")
        return "O cenario politico e economico brasileiro segue movimentado com diversas pautas em destaque."


# ── CONFIGURACAO DAS CATEGORIAS ───────────────────────────────────────────────
CATEGORIAS = [
    (
        "Politica",
        "politica brasileira: Congresso Nacional, STF, governo federal, eleicoes 2026, "
        "partidos politicos, ministerios, politicas publicas, relacoes entre Executivo e Legislativo"
    ),
    (
        "Economia",
        "economia brasileira: mercado financeiro, bolsa de valores, inflacao, taxa de juros Selic, "
        "cambio, emprego, PIB, agronegocio, industria, comercio exterior, politica economica"
    ),
    (
        "Cultura",
        "cultura no Brasil e no mundo: musica (shows, lancamentos de albuns, artistas), "
        "literatura (livros, autores), teatro, artes visuais, exposicoes, festivais culturais, "
        "gastronomia, moda, patrimonio historico, premios culturais"
    ),
    (
        "Tecnologia",
        "tecnologia no Brasil e no mundo: inteligencia artificial, startups, big tech "
        "(Apple, Google, Microsoft, Meta, Amazon), inovacao, ciberseguranca, regulacao digital, "
        "novos dispositivos, ciencia e pesquisa, espacial, biotecnologia"
    ),
    (
        "Entretenimento",
        "entretenimento: lancamentos e novidades em streaming (Netflix, Amazon Prime Video, "
        "HBO Max/Max, Apple TV+, Disney+), filmes em cartaz nos cinemas, series mais assistidas, "
        "renovacoes e cancelamentos, criticas, premiacoes como Oscar e Emmy, celebridades"
    ),
]


# ── ORQUESTRADOR ─────────────────────────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY nao encontrada.")
    print(f"[OK] API key Anthropic ({len(api_key)} chars)")

    client    = anthropic.Anthropic(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    todas         = []
    por_categoria = {}
    resumos_cat   = {}

    for categoria, instrucoes in CATEGORIAS:
        try:
            noticias, resumo_cat = buscar_categoria(
                client, categoria, instrucoes, today_str
            )
            todas.extend(noticias)
            por_categoria[categoria] = len(noticias)
            resumos_cat[categoria]   = resumo_cat
            time.sleep(3)  # pausa entre categorias
        except Exception as e:
            print(f"   [ERRO] {categoria}: {e}", file=sys.stderr)
            traceback.print_exc()
            por_categoria[categoria] = 0
            time.sleep(5)

    total = len(todas)
    print(f"\n[OK] Total: {total} noticias")
    for cat, n in por_categoria.items():
        print(f"   {cat}: {n}")

    if total < 5:
        raise RuntimeError(f"Apenas {total} noticias — insuficiente.")

    editorial = gerar_editorial(client, todas, today_str)

    return {
        "resumo_editorial": editorial,
        "resumos_categoria": resumos_cat,
        "noticias":          todas,
        "por_categoria":     por_categoria,
        "generated_at":      now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label":     get_edition_label(now_br.hour),
        "date_display":      today_str.upper(),
    }


def main():
    print("=" * 52)
    print("BOLETIM GERAL DE NOTICIAS — Gerador (Claude)")
    print("=" * 52)

    for attempt in range(1, 3):
        try:
            print(f"\n[Tentativa {attempt}/2]")
            data = fetch_news()
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] Salvo em {OUTPUT} ({len(data['noticias'])} noticias)")
            return
        except Exception as e:
            print(f"\n[ERRO] {e}", file=sys.stderr)
            traceback.print_exc()
            if attempt < 2:
                print("Aguardando 20s...", file=sys.stderr)
                time.sleep(20)
            else:
                sys.exit(1)


if __name__ == "__main__":
    main()
