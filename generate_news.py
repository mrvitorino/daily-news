#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil

Passo A: busca com google_search → texto livre estruturado
Passo B: extrai metadados SEGUROS em JSON (so campos sem texto livre)
Passo C: gera resumo + corpo em texto puro por noticia (sem JSON)
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

def call_gemini(client, prompt, use_search=False, max_tokens=4000, temp=0.1,
                mime_type=None, schema=None):
    """Wrapper unificado para chamadas ao Gemini."""
    cfg = dict(temperature=temp, max_output_tokens=max_tokens)
    if use_search:
        cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if mime_type:
        cfg["response_mime_type"] = mime_type
    if schema:
        cfg["response_schema"] = schema
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(**cfg)
    )
    return resp.text


# ─────────────────────────────────────────
# PASSO A — busca ampla, retorna texto livre
# ─────────────────────────────────────────
def passo_a_buscar(client, today_str):
    print("[..] Passo A: buscando com Google Search...")

    prompt = f"""Hoje e {today_str}. Voce e um jornalista brasileiro experiente.

Faca MULTIPLAS buscas (minimo 6) e encontre {NUM_NEWS} noticias reais sobre
POLITICA e ECONOMIA do Brasil das ultimas 48 horas.

Buscas sugeridas:
1. politica brasil {today_str}
2. economia brasil {today_str}
3. governo lula hoje
4. congresso nacional hoje
5. mercado financeiro brasil hoje
6. STF decisao recente
7. Se faltar noticias: saude educacao meio ambiente seguranca brasil recente

FONTES ACEITAS: Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao,
Valor Economico, ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato,
Carta Capital, CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal,
Bloomberg Linea, Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney,
Opera Mundi, Correio Braziliense, Band News, AFP Brasil, R7 Noticias.

PROIBIDO: Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista.

Escreva cada noticia exatamente neste formato (sem variacao):
===NOTICIA===
TITULO: [titulo completo da noticia]
FONTE: [nome do veiculo]
CATEGORIA: [Politica ou Economia ou Internacional]
IMPORTANCIA: [numero de 1 a 10]
URL: [url completa ou vazio]
===FIM===

REGRA ABSOLUTA: escreva exatamente {NUM_NEWS} blocos ===NOTICIA=== ... ===FIM===
Nunca escreva N/A, nunca deixe campos vazios, nunca diga que nao encontrou noticias."""

    txt = call_gemini(client, prompt, use_search=True, max_tokens=6000, temp=0.1)
    print(f"[OK] Passo A: {len(txt)} chars")
    return txt


# ─────────────────────────────────────────
# PASSO B — extrai metadados do texto (só campos seguros)
# Usa schema com APENAS strings curtas sem texto livre
# ─────────────────────────────────────────
def passo_b_extrair_meta(client, raw_text, today_str):
    print("[..] Passo B: extraindo metadados em JSON...")

    # Schema minimo: so campos que nunca contem aspas ou texto longo
    schema = {
        "type": "object",
        "properties": {
            "resumo_editorial": {"type": "string"},
            "noticias": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titulo":      {"type": "string"},
                        "fonte":       {"type": "string"},
                        "categoria":   {"type": "string"},
                        "url":         {"type": "string"},
                        "importancia": {"type": "integer"}
                    },
                    "required": ["titulo","fonte","categoria","url","importancia"]
                }
            }
        },
        "required": ["resumo_editorial","noticias"]
    }

    prompt = f"""Extraia os dados do texto abaixo em JSON.

Para resumo_editorial: escreva 2 frases simples sobre o panorama do dia.
Para cada noticia: extraia titulo, fonte, categoria, url e importancia.
Titulo deve ser curto (maximo 15 palavras).
Ignore entradas com titulo vazio, N/A ou "nao encontrado".

TEXTO:
{raw_text[:5000]}"""

    txt = call_gemini(client, prompt, use_search=False, max_tokens=3000, temp=0.0,
                      mime_type="application/json", schema=schema)

    data = json.loads(txt)

    # Filtrar invalidas
    validas = []
    for n in data.get("noticias", []):
        t = n.get("titulo","").strip()
        bad = (not t or len(t) < 8
               or t.lower().startswith("n/a")
               or "nao foi possivel" in t.lower()
               or "nao encontrado" in t.lower()
               or "não foi" in t.lower())
        if bad:
            print(f"   [SKIP] {t[:60]}")
            continue
        if not n.get("url","").startswith("http"):
            n["url"] = ""
        validas.append(n)

    data["noticias"] = validas
    print(f"[OK] Passo B: {len(validas)} noticias validas.")

    if len(validas) < 5:
        raise RuntimeError(f"Apenas {len(validas)} noticias validas apos filtro.")
    return data


# ─────────────────────────────────────────
# PASSO C — gera resumo + corpo em TEXTO PURO
# Sem JSON, sem schema → zero risco de parse error
# ─────────────────────────────────────────
def passo_c_texto(client, noticia, today_str):
    titulo = noticia.get("titulo","")
    fonte  = noticia.get("fonte","")
    print(f"   [..] Texto: {titulo[:55]}...")

    prompt = f"""Escreva um texto jornalistico sobre esta noticia brasileira:

Titulo: {titulo}
Fonte: {fonte}

Formato de saida (siga exatamente):
RESUMO: [escreva aqui 2 frases descrevendo o fato e sua importancia]
CORPO: [escreva aqui 3 paragrafos separados por // descrevendo contexto, fatos e impacto]

Regras:
- Use apenas aspas simples se precisar de aspas
- Nao use markdown, nao use asteriscos
- Escreva em portugues brasileiro formal
- Base-se apenas no titulo e fonte fornecidos"""

    try:
        txt = call_gemini(client, prompt, use_search=False, max_tokens=800, temp=0.3)

        resumo = ""
        corpo  = ""

        # Extrai RESUMO
        m = re.search(r'RESUMO:\s*(.+?)(?=CORPO:|$)', txt, re.DOTALL | re.IGNORECASE)
        if m:
            resumo = m.group(1).strip()

        # Extrai CORPO
        m2 = re.search(r'CORPO:\s*(.+?)$', txt, re.DOTALL | re.IGNORECASE)
        if m2:
            corpo = m2.group(1).strip().replace(" // ", "\n\n").replace("//", "\n\n")

        # Fallbacks
        if not resumo:
            resumo = titulo
        if not corpo:
            corpo = resumo

        return resumo, corpo

    except Exception as e:
        print(f"   [WARN] {e}")
        return titulo, titulo


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

    raw  = passo_a_buscar(client, today_str)
    time.sleep(3)
    data = passo_b_extrair_meta(client, raw, today_str)
    time.sleep(2)

    print(f"[..] Passo C: gerando textos para {len(data['noticias'])} noticias...")
    for i, n in enumerate(data["noticias"]):
        resumo, corpo = passo_c_texto(client, n, today_str)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        if i < len(data["noticias"]) - 1:
            time.sleep(2)

    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()
    print(f"[OK] Concluido: {len(data['noticias'])} noticias.")
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
