#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Etapa 1: busca as 10 noticias (JSON pequeno e seguro)
Etapa 2: para cada noticia, busca o corpo completo numa chamada separada
"""

import json
import os
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

def make_client():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    return genai.Client(api_key=api_key)

def parse_json(text):
    """Extrai e parseia JSON de uma resposta de texto."""
    clean = text.replace("```json", "").replace("```", "").strip()
    s = clean.find("{")
    e = clean.rfind("}")
    if s == -1 or e == -1:
        raise RuntimeError("JSON nao encontrado na resposta.")
    return json.loads(clean[s:e+1])

# ─────────────────────────────────────────
# ETAPA 1: buscar lista de noticias (JSON curto, sem corpo)
# ─────────────────────────────────────────
def fetch_noticias(client, today_str):
    print("[..] Etapa 1: buscando lista de noticias...")

    prompt = f"""Hoje e {today_str}. Voce e um editor jornalistico especializado em politica e economia brasileira.

Use a ferramenta de busca para encontrar as {NUM_NEWS} noticias mais importantes sobre POLITICA e ECONOMIA no Brasil publicadas hoje ou nas ultimas 48 horas.

Priorize estas fontes: Folha de S.Paulo, Agencia Brasil, ICL Noticias, Intercept Brasil, Revista Forum.
Se necessario, use: G1, UOL, Estadao, Valor Economico, CNN Brasil.

Retorne SOMENTE este JSON minimo, sem texto antes ou depois:

{{"resumo_editorial":"2-3 frases sobre o panorama do dia.","noticias":[{{"id":1,"titulo":"titulo da noticia","fonte":"nome da fonte","categoria":"Politica ou Economia ou Internacional","resumo":"2-3 frases sobre o fato e sua relevancia.","importancia":8}}]}}

REGRAS:
- Exatamente {NUM_NEWS} noticias
- id e inteiro sequencial de 1 a {NUM_NEWS}
- importancia e inteiro de 1 a 10
- NAO inclua campo url nem corpo neste JSON
- Mantenha o resumo curto (max 3 frases)"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
            max_output_tokens=3000,
        )
    )

    raw = resp.text
    print(f"[OK] Resposta etapa 1: {len(raw)} chars")
    data = parse_json(raw)

    noticias = data.get("noticias", [])
    print(f"[OK] {len(noticias)} noticias parseadas.")
    if len(noticias) == 0:
        raise RuntimeError("Nenhuma noticia retornada.")
    return data

# ─────────────────────────────────────────
# ETAPA 2: para cada noticia, buscar corpo e URL individualmente
# ─────────────────────────────────────────
def fetch_corpo(client, noticia, today_str):
    titulo = noticia.get("titulo", "")
    fonte  = noticia.get("fonte", "")
    print(f"   [..] Buscando corpo: {titulo[:60]}...")

    prompt = f"""Hoje e {today_str}. Busque a seguinte noticia:

Titulo: {titulo}
Fonte: {fonte}

Use a ferramenta de busca para encontrar o artigo original e retorne SOMENTE este JSON:

{{"corpo":"texto completo em 3-5 paragrafos. Use \\n\\n para separar paragrafos. Escreva em portugues brasileiro formal. Inclua contexto, fatos, declaracoes e impacto.","url":"URL direta e completa do artigo (https://...) ou string vazia se nao encontrar"}}

NAO inclua nenhum texto fora do JSON. NAO use aspas duplas dentro dos valores - use aspas simples se necessario."""

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                max_output_tokens=2048,
            )
        )
        raw = resp.text
        result = parse_json(raw)
        return result.get("corpo", ""), result.get("url", "")
    except Exception as e:
        print(f"   [WARN] Falha ao buscar corpo: {e}")
        return noticia.get("resumo", ""), ""

# ─────────────────────────────────────────
# MAIN FETCH
# ─────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key encontrada ({len(api_key)} chars)")

    client   = make_client()
    now_br   = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] Data: {today_str}")
    print(f"[OK] Edicao: {get_edition_label(now_br.hour)}")

    # Etapa 1: lista de noticias
    data = fetch_noticias(client, today_str)

    # Etapa 2: corpo de cada noticia (com pausa para evitar rate limit)
    print(f"\n[..] Etapa 2: buscando corpo das {len(data['noticias'])} noticias...")
    for i, noticia in enumerate(data["noticias"]):
        corpo, url = fetch_corpo(client, noticia, today_str)
        noticia["corpo"] = corpo
        noticia["url"]   = url
        if i < len(data["noticias"]) - 1:
            time.sleep(2)  # pausa entre chamadas

    print(f"\n[OK] Todas as noticias processadas.")
    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()
    return data


def main():
    print("=" * 50)
    print("PANORAMA — Gerador de Boletim (Gemini)")
    print("=" * 50)

    retries = 2
    for attempt in range(1, retries + 1):
        try:
            print(f"\n[Tentativa {attempt}/{retries}]")
            data = fetch_news()
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] Salvo em {OUTPUT}")
            print("=" * 50)
            return
        except Exception as e:
            print(f"\n[ERRO] {e}", file=sys.stderr)
            traceback.print_exc()
            if attempt < retries:
                print("Aguardando 20s antes da proxima tentativa...", file=sys.stderr)
                time.sleep(20)
            else:
                print("Todas as tentativas falharam.", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
