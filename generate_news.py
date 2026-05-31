#!/usr/bin/env python3
"""
generate_news.py — Boletim Geral de Noticias
Arquitetura otimizada para custo:

Passo 1 (Sonnet + web_search): UMA chamada busca TODAS as categorias de uma vez
         → retorna lista JSON com titulo/fonte/categoria/url/importancia
         → ~5-8 buscas web = $0.05

Passo 2 (Haiku, sem busca): escreve resumo+corpo para cada noticia individualmente
         → muito mais barato ($0.80 input / $4.00 output por 1M tokens)

Custo estimado: ~$0.23/execucao, ~$14/mes (2x por dia)
vs anterior:    ~$1.72/execucao (5 chamadas Sonnet+search = 25 buscas)
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

OUTPUT        = "news-data.json"
MODEL_SEARCH  = "claude-sonnet-4-6"    # Sonnet: busca web (1 chamada)
MODEL_WRITER  = "claude-haiku-3-5"     # Haiku: escreve corpos (barato)
NEWS_PER_CAT  = 8                       # noticias por categoria

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

def _strip_md(txt):
    if not txt: return ""
    txt = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', txt)
    txt = re.sub(r'#{1,6}\s+', '', txt)
    txt = re.sub(r'`([^`]+)`', r'\1', txt)
    txt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
    txt = re.sub(r'(?i)\*{0,2}fonte\s*:\s*[^|\n*]+(\|[^\n*]+)?\*{0,2}', '', txt)
    return txt.strip()

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 1 — UMA chamada Sonnet+search para TODAS as categorias
# ─────────────────────────────────────────────────────────────────────────────
def buscar_todas(client, today_str):
    print("[..] Passo 1: buscando noticias de todas as categorias (Sonnet + web_search)...")

    n = NEWS_PER_CAT

    prompt = f"""Hoje e {today_str}. Voce e um editor de um boletim de noticias abrangente.

Use a ferramenta de busca para encontrar as noticias mais relevantes das ultimas 48h
nas 5 categorias abaixo. Faca buscas especificas para cada categoria.

CATEGORIAS E QUANTIDADE:
- Politica ({n}): politica brasileira, Congresso, STF, governo Lula, eleicoes 2026
- Economia ({n}): economia brasileira, mercado, inflacao, juros, emprego, agronegocio
- Cultura ({n}): musica, arte, literatura, teatro, cinema, festivais no Brasil
- Tecnologia ({n}): IA, startups, big tech, inovacao, ciberseguranca no Brasil e mundo
- Entretenimento ({n}): Netflix, Amazon, HBO Max, Apple TV+, Disney+, filmes em cartaz

FONTES ACEITAS: Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao,
Valor Economico, ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato,
Carta Capital, CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal,
Bloomberg Linea, Agencia Publica, IstoE, Exame, InfoMoney, The Verge, Wired,
TechCrunch, Canaltech, TecMundo, Variety, Hollywood Reporter, Screen Rant.
PROIBIDO: Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista.

Retorne SOMENTE este JSON, sem texto adicional:
{{
  "noticias": [
    {{
      "titulo": "titulo da noticia",
      "fonte": "nome do veiculo",
      "categoria": "Politica|Economia|Cultura|Tecnologia|Entretenimento",
      "importancia": 8,
      "url": "https://url-do-artigo-ou-string-vazia"
    }}
  ]
}}

Retorne exatamente {n*5} noticias ({n} por categoria).
Imputancia e inteiro de 1 a 10. URL deve ser do artigo original ou string vazia."""

    for tentativa in range(3):
        try:
            resp = client.messages.create(
                model=MODEL_SEARCH,
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            break
        except anthropic.RateLimitError as e:
            espera = 70 * (tentativa + 1)
            print(f"   [429] Rate limit — aguardando {espera}s...", file=sys.stderr)
            time.sleep(espera)
            if tentativa == 2:
                raise

    # Extrai texto da resposta
    texto = "".join(b.text for b in resp.content if b.type == "text")
    print(f"   Resposta: {len(texto)} chars")

    # Parse JSON
    texto = re.sub(r'^```(?:json)?\s*', '', texto.strip(), flags=re.MULTILINE)
    texto = re.sub(r'\s*```\s*$', '', texto, flags=re.MULTILINE)
    s = texto.find('{')
    e = texto.rfind('}')
    if s == -1 or e == -1:
        raise RuntimeError("JSON nao encontrado na resposta de busca")

    data = json.loads(texto[s:e+1])
    noticias_raw = data.get("noticias", [])

    # Valida e normaliza
    noticias = []
    for n in noticias_raw:
        titulo = n.get("titulo", "").strip()
        if not titulo or len(titulo) < 8:
            continue
        if any(x in titulo.lower() for x in ["n/a", "nao foi", "exemplo", "[titulo"]):
            continue
        cat = n.get("categoria", "")
        if cat not in ["Politica", "Economia", "Cultura", "Tecnologia", "Entretenimento"]:
            continue
        url = n.get("url", "")
        if not isinstance(url, str) or "vertexaisearch" in url or not url.startswith("http"):
            url = ""
        try:
            imp = min(10, max(1, int(n.get("importancia", 5))))
        except Exception:
            imp = 5
        noticias.append({
            "titulo":      titulo,
            "fonte":       n.get("fonte", "Redacao").strip() or "Redacao",
            "categoria":   cat,
            "importancia": imp,
            "url":         url,
        })

    # Conta por categoria
    contagem = {}
    for n in noticias:
        contagem[n["categoria"]] = contagem.get(n["categoria"], 0) + 1
    print(f"   Noticias validas: {len(noticias)} — {contagem}")
    return noticias


# ─────────────────────────────────────────────────────────────────────────────
# PASSO 2 — Haiku escreve resumo+corpo (sem busca, muito barato)
# ─────────────────────────────────────────────────────────────────────────────
def escrever_corpo(client, noticia):
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    cat    = noticia["categoria"]

    prompt = (
        f"Escreva um artigo jornalistico em portugues brasileiro sobre:\n"
        f"Titulo: {titulo}\nFonte: {fonte} | Categoria: {cat}\n\n"
        "Escreva 4 paragrafos numerados separados por linha em branco:\n\n"
        "1) Duas frases de resumo: quem, o que aconteceu, por que e importante.\n\n"
        "2) Contexto e antecedentes historicos. Minimo 3 frases.\n\n"
        "3) Fatos detalhados, dados e declaracoes dos envolvidos. Minimo 3 frases.\n\n"
        "4) Impacto, consequencias e proximos passos. Minimo 3 frases.\n\n"
        "Sem markdown, sem asteriscos, sem negrito. Texto puro."
    )

    try:
        resp = client.messages.create(
            model=MODEL_WRITER,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        txt = _strip_md(resp.content[0].text or "")

        # Divide por numeracao "1)" "2)" "3)" "4)"
        partes = re.split(r'(?m)^\s*[1-4]\)\s*', txt)
        partes = [p.strip() for p in partes if len(p.strip()) > 30]

        if len(partes) >= 4:
            resumo = partes[0]
            corpo  = "\n\n".join(partes[1:4])
        elif len(partes) >= 2:
            resumo = partes[0]
            corpo  = "\n\n".join(partes[1:])
        else:
            # Divide por linha em branco
            blocos = [b.strip() for b in re.split(r'\n{2,}', txt) if len(b.strip()) > 30]
            if len(blocos) >= 2:
                resumo = blocos[0]
                corpo  = "\n\n".join(blocos[1:4])
            else:
                return titulo, txt or titulo

        # Limita resumo a 2 frases
        frases = re.split(r'(?<=[.!?])\s+', resumo.strip())
        resumo = " ".join(frases[:2])
        return resumo.strip(), corpo.strip()

    except Exception as e:
        print(f"      [WARN] corpo: {e}")
        return titulo, titulo


# ─────────────────────────────────────────────────────────────────────────────
# PASSO 3 — Editorial (Haiku, barato)
# ─────────────────────────────────────────────────────────────────────────────
def gerar_editorial(client, noticias, today_str):
    titulos = "\n".join(
        f"- {n['titulo']}" for n in noticias
        if n["categoria"] in ["Politica", "Economia"]
    )[:600]

    prompt = (
        f"Noticias do dia ({today_str}):\n{titulos}\n\n"
        "Escreva um resumo editorial de 3 frases sobre o panorama do dia no Brasil. "
        "Texto puro, sem markdown, sem aspas duplas, portugues formal."
    )
    try:
        resp = client.messages.create(
            model=MODEL_WRITER,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return _strip_md(resp.content[0].text.strip())
    except Exception:
        return "O cenario politico e economico brasileiro segue movimentado com diversas pautas em destaque."


# ─────────────────────────────────────────────────────────────────────────────
# ORQUESTRADOR
# ─────────────────────────────────────────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY nao encontrada.")
    print(f"[OK] API key ({len(api_key)} chars)")

    client    = anthropic.Anthropic(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    # Passo 1: busca todas as noticias de uma vez (1 chamada Sonnet+search)
    noticias = buscar_todas(client, today_str)

    if len(noticias) < 5:
        raise RuntimeError(f"Apenas {len(noticias)} noticias encontradas — insuficiente.")

    # Passo 2: escreve corpo com Haiku (sem search, barato)
    print(f"\n[..] Passo 2: escrevendo corpo de {len(noticias)} noticias (Haiku)...")
    for i, n in enumerate(noticias):
        print(f"   [{i+1:02d}/{len(noticias)}] {n['titulo'][:55]}...")
        resumo, corpo = escrever_corpo(client, n)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        # Pausa minima entre chamadas Haiku (sem rate limit agressivo)
        if i < len(noticias) - 1:
            time.sleep(1)

    # Passo 3: editorial
    editorial = gerar_editorial(client, noticias, today_str)

    # Contagem por categoria
    por_cat = {}
    for n in noticias:
        por_cat[n["categoria"]] = por_cat.get(n["categoria"], 0) + 1

    return {
        "resumo_editorial": editorial,
        "noticias":         noticias,
        "por_categoria":    por_cat,
        "generated_at":     now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label":    get_edition_label(now_br.hour),
        "date_display":     today_str.upper(),
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
            total = len(data["noticias"])
            print(f"\n[OK] Salvo: {total} noticias — {data['por_categoria']}")
            return
        except Exception as e:
            print(f"\n[ERRO] {e}", file=sys.stderr)
            traceback.print_exc()
            if attempt < 2:
                print("Aguardando 30s...", file=sys.stderr)
                time.sleep(30)
            else:
                sys.exit(1)


if __name__ == "__main__":
    main()
