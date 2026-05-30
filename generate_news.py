#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Abordagem 100% texto puro — zero JSON intermediario.

Passo A: busca com google_search, retorna blocos de texto estruturado
Passo B: parseia os blocos com regex (sem JSON, sem risco de parse error)
Passo C: gera resumo + corpo em texto puro para cada noticia
Passo D: serializa tudo em JSON somente no final (json.dump nativo do Python)
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

def format_date_pt(dt):
    wd = WEEKDAYS_PT.get(dt.strftime("%A"), dt.strftime("%A"))
    mo = MONTHS_PT.get(dt.month, str(dt.month))
    return f"{wd}, {dt.day} de {mo} de {dt.year}"

def get_edition_label(hour):
    if hour < 10:   return "Edicao Matutina (08h)"
    elif hour < 14: return "Edicao do Meio-Dia (12h)"
    else:           return "Edicao Vespertina (17h)"

def gemini(client, prompt, search=False, max_tokens=4000, temp=0.1):
    cfg = dict(temperature=temp, max_output_tokens=max_tokens)
    if search:
        cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(**cfg)
    )
    return resp.text or ""


# ─────────────────────────────────────────
# PASSO A — busca e retorna blocos de texto
# Formato fixo com delimitadores que nao aparecem em titulos
# ─────────────────────────────────────────
def passo_a(client, today_str):
    print("[..] Passo A: buscando noticias...")

    prompt = f"""Hoje e {today_str}. Voce e um jornalista brasileiro.

Faca pelo menos 6 buscas e encontre {NUM_NEWS} noticias reais sobre
politica e economia brasileira das ultimas 48 horas.

Buscas obrigatorias:
1. politica brasil hoje
2. economia brasil hoje
3. governo lula congresso hoje
4. mercado financeiro brasil hoje
5. STF senado camara hoje
6. Se faltar: saude publica educacao eleicoes meio ambiente brasil recente

FONTES ACEITAS: Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao,
Valor Economico, ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato,
Carta Capital, CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal,
Bloomberg Linea, Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney,
Opera Mundi, Correio Braziliense, Band News, AFP Brasil, R7 Noticias.

PROIBIDO: Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista.

FORMATO DE SAIDA — use exatamente estes separadores:
##INICIO##
TITULO>> [titulo da noticia sem aspas]
FONTE>> [nome do veiculo]
CATEGORIA>> [Politica ou Economia ou Internacional]
IMPORTANCIA>> [numero de 1 a 10]
URL>> [url completa ou deixe em branco]
##FIM##

Repita o bloco ##INICIO## ... ##FIM## exatamente {NUM_NEWS} vezes.
NUNCA use N/A. NUNCA diga que nao encontrou noticias."""

    txt = gemini(client, prompt, search=True, max_tokens=6000, temp=0.1)
    print(f"[OK] Passo A: {len(txt)} chars, {txt.count('##INICIO##')} blocos")
    return txt


# ─────────────────────────────────────────
# PASSO B — parseia blocos com regex, zero JSON
# ─────────────────────────────────────────
def passo_b(raw_text, today_str):
    print("[..] Passo B: parseando blocos com regex...")

    blocos = re.findall(r'##INICIO##(.*?)##FIM##', raw_text, re.DOTALL)
    print(f"   Blocos encontrados: {len(blocos)}")

    def extrai(bloco, campo):
        m = re.search(rf'{campo}>>\s*(.+)', bloco)
        return m.group(1).strip() if m else ""

    noticias = []
    for bloco in blocos:
        titulo     = extrai(bloco, "TITULO")
        fonte      = extrai(bloco, "FONTE")
        categoria  = extrai(bloco, "CATEGORIA")
        imp_str    = extrai(bloco, "IMPORTANCIA")
        url        = extrai(bloco, "URL")

        # Validar
        if not titulo or len(titulo) < 8:
            continue
        bad = any(x in titulo.lower() for x in ["n/a","nao foi possivel","nao encontrado","não foi"])
        if bad:
            print(f"   [SKIP] {titulo[:60]}")
            continue

        try:
            importancia = int(re.search(r'\d+', imp_str).group())
        except Exception:
            importancia = 5

        if not url.startswith("http"):
            url = ""

        if not categoria or categoria not in ["Politica","Economia","Internacional"]:
            categoria = "Politica"

        noticias.append({
            "titulo": titulo,
            "fonte": fonte or "Brasil",
            "categoria": categoria,
            "url": url,
            "importancia": min(10, max(1, importancia)),
        })

    print(f"[OK] Passo B: {len(noticias)} noticias validas.")

    if len(noticias) < 5:
        # Tenta fallback: parseia linha a linha sem blocos
        print("   [WARN] Poucos blocos — tentando parse linha a linha...")
        noticias = parse_fallback(raw_text)
        print(f"   Fallback: {len(noticias)} noticias.")

    if len(noticias) < 3:
        raise RuntimeError(f"Apenas {len(noticias)} noticias — insuficiente.")

    return noticias


def parse_fallback(txt):
    """Parse alternativo para quando o modelo nao segue o formato de blocos."""
    noticias = []
    linhas = txt.split("\n")
    atual = {}
    for linha in linhas:
        linha = linha.strip()
        if "TITULO>>" in linha:
            if atual.get("titulo"):
                noticias.append(atual)
            t = linha.split(">>",1)[1].strip()
            atual = {"titulo":t,"fonte":"Brasil","categoria":"Politica","url":"","importancia":5}
        elif "FONTE>>" in linha and atual:
            atual["fonte"] = linha.split(">>",1)[1].strip() or "Brasil"
        elif "CATEGORIA>>" in linha and atual:
            c = linha.split(">>",1)[1].strip()
            atual["categoria"] = c if c in ["Politica","Economia","Internacional"] else "Politica"
        elif "IMPORTANCIA>>" in linha and atual:
            m = re.search(r'\d+', linha)
            atual["importancia"] = int(m.group()) if m else 5
        elif "URL>>" in linha and atual:
            u = linha.split(">>",1)[1].strip()
            atual["url"] = u if u.startswith("http") else ""
    if atual.get("titulo"):
        noticias.append(atual)
    return [n for n in noticias if len(n.get("titulo","")) >= 8]


# ─────────────────────────────────────────
# PASSO C — resumo + corpo em texto puro
# ─────────────────────────────────────────
def passo_c(client, noticia, today_str):
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    print(f"   [..] {titulo[:55]}...")

    prompt = f"""Escreva um texto jornalistico sobre esta noticia:

Titulo: {titulo}
Fonte: {fonte}

Siga este formato exato:
RESUMO>> [duas frases descrevendo o fato e sua importancia]
PARAGRAFO1>> [primeiro paragrafo com contexto historico]
PARAGRAFO2>> [segundo paragrafo com os fatos principais e declaracoes]
PARAGRAFO3>> [terceiro paragrafo com impacto e desdobramentos]

Use apenas aspas simples se precisar de aspas.
Escreva em portugues brasileiro formal."""

    try:
        txt = gemini(client, prompt, search=False, max_tokens=700, temp=0.3)

        def ex(campo):
            m = re.search(rf'{campo}>>\s*(.+?)(?=\n[A-Z]+>>|\Z)', txt, re.DOTALL)
            return m.group(1).strip() if m else ""

        resumo = ex("RESUMO") or titulo
        p1 = ex("PARAGRAFO1")
        p2 = ex("PARAGRAFO2")
        p3 = ex("PARAGRAFO3")
        corpo = "\n\n".join(p for p in [p1, p2, p3] if p) or resumo
        return resumo, corpo

    except Exception as e:
        print(f"   [WARN] {e}")
        return titulo, titulo


# ─────────────────────────────────────────
# PASSO D — gera resumo editorial
# ─────────────────────────────────────────
def passo_d_editorial(client, noticias, today_str):
    titulos = "\n".join(f"- {n['titulo']}" for n in noticias[:5])
    prompt = f"""Com base nestas noticias brasileiras de hoje:
{titulos}

Escreva um resumo editorial em 2 frases sobre o panorama politico-economico do dia.
Escreva apenas as 2 frases, sem titulo, sem aspas duplas."""
    try:
        txt = gemini(client, prompt, search=False, max_tokens=200, temp=0.2)
        return txt.strip()
    except Exception:
        return "O cenario politico e economico brasileiro segue movimentado."


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

    # Passos A e B: busca e parse
    raw      = passo_a(client, today_str)
    time.sleep(2)
    noticias = passo_b(raw, today_str)
    time.sleep(2)

    # Passo C: textos individuais
    print(f"[..] Passo C: gerando textos ({len(noticias)} noticias)...")
    for i, n in enumerate(noticias):
        resumo, corpo = passo_c(client, n, today_str)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        if i < len(noticias) - 1:
            time.sleep(1)

    # Passo D: editorial
    editorial = passo_d_editorial(client, noticias, today_str)

    # Monta estrutura final — json.dump cuida da serialização correta
    data = {
        "resumo_editorial": editorial,
        "noticias": noticias,
        "generated_at":  now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label": get_edition_label(now_br.hour),
        "date_display":  today_str.upper(),
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
