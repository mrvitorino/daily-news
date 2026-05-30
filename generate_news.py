#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil

Estrategia: 4 buscas tematicas separadas (politica, economia, governo, mercado)
cada uma retorna blocos de texto. Os resultados sao agregados, deduplicados
e limitados a NUM_NEWS. Zero JSON intermediario — tudo regex + json.dump final.
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

from google import genai
from google.genai import types

NUM_NEWS = 10
OUTPUT   = "news-data.json"
MODEL    = "gemini-2.5-flash"

WEEKDAYS_PT = {
    "Monday":"segunda-feira","Tuesday":"terca-feira","Wednesday":"quarta-feira",
    "Thursday":"quinta-feira","Friday":"sexta-feira","Saturday":"sabado","Sunday":"domingo"
}
MONTHS_PT = {
    1:"janeiro",2:"fevereiro",3:"marco",4:"abril",5:"maio",6:"junho",
    7:"julho",8:"agosto",9:"setembro",10:"outubro",11:"novembro",12:"dezembro"
}

FONTES_ACEITAS = """Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao,
Valor Economico, ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato,
Carta Capital, CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal,
Bloomberg Linea, Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney,
Opera Mundi, Correio Braziliense, Band News, AFP Brasil, R7 Noticias."""

FONTES_PROIBIDAS = "Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista."

BLOCO_FMT = """##INICIO##
TITULO>> [titulo da noticia]
FONTE>> [nome do veiculo]
CATEGORIA>> [Politica ou Economia ou Internacional]
IMPORTANCIA>> [1 a 10]
URL>> [url completa ou vazio]
##FIM##"""

def format_date_pt(dt):
    wd = WEEKDAYS_PT.get(dt.strftime("%A"), dt.strftime("%A"))
    mo = MONTHS_PT.get(dt.month, str(dt.month))
    return f"{wd}, {dt.day} de {mo} de {dt.year}"

def get_edition_label(hour):
    if hour < 10:   return "Edicao Matutina (08h)"
    elif hour < 14: return "Edicao do Meio-Dia (12h)"
    else:           return "Edicao Vespertina (17h)"

def gemini_search(client, prompt, max_tokens=3000):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=max_tokens,
        )
    )
    return resp.text or ""

def gemini_text(client, prompt, max_tokens=700, temp=0.3):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temp,
            max_output_tokens=max_tokens,
        )
    )
    return resp.text or ""


# ─────────────────────────────────────────
# PARSE DE BLOCOS — regex robusto
# ─────────────────────────────────────────
def parse_blocos(txt):
    blocos = re.findall(r'##INICIO##(.*?)##FIM##', txt, re.DOTALL)
    noticias = []
    for bloco in blocos:
        def ex(campo):
            m = re.search(rf'{campo}>>\s*(.+)', bloco)
            return m.group(1).strip() if m else ""

        titulo    = ex("TITULO")
        fonte     = ex("FONTE") or "Brasil"
        categoria = ex("CATEGORIA")
        imp_str   = ex("IMPORTANCIA")
        url       = ex("URL")

        if not titulo or len(titulo) < 8:
            continue
        if any(x in titulo.lower() for x in ["n/a","nao foi possivel","nao encontrado","não foi","placeholder"]):
            continue

        try:
            importancia = int(re.search(r'\d+', imp_str).group())
        except Exception:
            importancia = 5

        if not url.startswith("http"):
            url = ""
        if categoria not in ["Politica","Economia","Internacional"]:
            categoria = "Politica"

        noticias.append({
            "titulo":      titulo,
            "fonte":       fonte,
            "categoria":   categoria,
            "url":         url,
            "importancia": min(10, max(1, importancia)),
        })
    return noticias


def prompt_busca(tema, n, today_str):
    return f"""Hoje e {today_str}. Voce e um jornalista brasileiro especializado em {tema}.

Use a ferramenta de busca e encontre {n} noticias DIFERENTES sobre {tema} no Brasil
publicadas nas ultimas 48 horas.

FONTES ACEITAS: {FONTES_ACEITAS}
PROIBIDO: {FONTES_PROIBIDAS}

Para cada noticia escreva EXATAMENTE neste formato:
{BLOCO_FMT}

Regras:
- Escreva exatamente {n} blocos ##INICIO## ... ##FIM##
- NUNCA escreva N/A
- Se uma busca nao retornar resultados, tente outra busca sobre o mesmo tema
- Cada noticia deve ser diferente das outras"""


# ─────────────────────────────────────────
# BUSCA POR TEMA — 4 temas separados
# ─────────────────────────────────────────
TEMAS = [
    ("politica brasileira, congresso nacional, STF, eleicoes", 3),
    ("economia brasileira, mercado financeiro, inflacao, emprego", 3),
    ("governo federal brasileiro, ministerios, politicas publicas", 2),
    ("relacoes internacionais do Brasil, comercio exterior, diplomacia brasileira", 2),
]

def buscar_por_temas(client, today_str):
    todas = []
    for tema, n in TEMAS:
        print(f"   [..] Tema: {tema[:45]}...")
        try:
            txt = gemini_search(client, prompt_busca(tema, n, today_str), max_tokens=2500)
            encontradas = parse_blocos(txt)
            print(f"        → {len(encontradas)} noticias")
            todas.extend(encontradas)
            time.sleep(3)
        except Exception as e:
            print(f"        → ERRO: {e}", file=sys.stderr)
            time.sleep(3)

    return todas


def deduplicar(noticias):
    """Remove noticias com titulo muito similar (primeiras 6 palavras iguais)."""
    vistas = set()
    unicas = []
    for n in noticias:
        chave = " ".join(n["titulo"].lower().split()[:6])
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(n)
    return unicas


# ─────────────────────────────────────────
# PASSO C — resumo + corpo em texto puro
# ─────────────────────────────────────────
def gerar_texto(client, noticia):
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]

    prompt = f"""Escreva um texto jornalistico sobre esta noticia:

Titulo: {titulo}
Fonte: {fonte}

Formato obrigatorio:
RESUMO>> duas frases descrevendo o fato e sua importancia
PARAGRAFO1>> primeiro paragrafo com contexto historico
PARAGRAFO2>> segundo paragrafo com fatos e declaracoes
PARAGRAFO3>> terceiro paragrafo com impacto e desdobramentos

Use apenas aspas simples se precisar de aspas.
Portugues brasileiro formal. Apenas o texto, sem introducao."""

    try:
        txt = gemini_text(client, prompt, max_tokens=700, temp=0.3)

        def ex(campo):
            m = re.search(rf'{campo}>>\s*(.+?)(?=\n[A-Z]+>>|\Z)', txt, re.DOTALL)
            return m.group(1).strip() if m else ""

        resumo = ex("RESUMO") or titulo
        p1, p2, p3 = ex("PARAGRAFO1"), ex("PARAGRAFO2"), ex("PARAGRAFO3")
        corpo = "\n\n".join(p for p in [p1, p2, p3] if p) or resumo
        return resumo, corpo
    except Exception as e:
        print(f"      [WARN] {e}")
        return titulo, titulo


def gerar_editorial(client, noticias):
    titulos = "\n".join(f"- {n['titulo']}" for n in noticias[:6])
    prompt = f"""Com base nestas noticias brasileiras recentes:
{titulos}

Escreva um resumo editorial de 2 frases sobre o panorama politico-economico.
Apenas as 2 frases, sem titulo nem aspas duplas."""
    try:
        return gemini_text(client, prompt, max_tokens=150, temp=0.2).strip()
    except Exception:
        return "O cenario politico e economico brasileiro segue movimentado com diversas frentes em destaque."


# ─────────────────────────────────────────
# ORQUESTRADOR
# ─────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY","").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key ({len(api_key)} chars)")

    client    = genai.Client(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    # Busca por 4 temas
    print("[..] Buscando por temas...")
    todas = buscar_por_temas(client, today_str)
    unicas = deduplicar(todas)

    print(f"[OK] Total: {len(todas)} brutas → {len(unicas)} unicas apos deduplicacao")

    if len(unicas) < 3:
        raise RuntimeError(f"Apenas {len(unicas)} noticias unicas — insuficiente.")

    # Ordena por importancia e limita
    unicas.sort(key=lambda n: n["importancia"], reverse=True)
    noticias = unicas[:NUM_NEWS]

    # Gera resumo + corpo para cada
    print(f"[..] Gerando textos para {len(noticias)} noticias...")
    for i, n in enumerate(noticias):
        print(f"   [{i+1}/{len(noticias)}] {n['titulo'][:55]}...")
        resumo, corpo = gerar_texto(client, n)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        if i < len(noticias) - 1:
            time.sleep(1)

    # Editorial
    editorial = gerar_editorial(client, noticias)

    data = {
        "resumo_editorial": editorial,
        "noticias":         noticias,
        "generated_at":     now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label":    get_edition_label(now_br.hour),
        "date_display":     today_str.upper(),
    }
    print(f"[OK] Concluido: {len(noticias)} noticias.")
    return data


def main():
    print("=" * 52)
    print("PANORAMA — Gerador de Boletim (Gemini)")
    print("=" * 52)

    for attempt in range(1, 3):
        try:
            print(f"\n[Tentativa {attempt}/2]")
            data = fetch_news()
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] Salvo em {OUTPUT}")
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
