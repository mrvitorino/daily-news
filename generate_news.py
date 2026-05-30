#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Busca noticias via Google Gemini API (google-genai SDK) + Google Search
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
MODEL    = "gemini-2.0-flash"

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

def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nao encontrada. "
            "Configure em: Settings -> Secrets and variables -> Actions"
        )

    print(f"[OK] API key encontrada ({len(api_key)} chars)")

    client = genai.Client(api_key=api_key)

    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] Data: {today_str}")
    print(f"[OK] Edicao: {get_edition_label(now_br.hour)}")
    print("[..] Chamando Gemini API com Google Search...")

    prompt = f"""Hoje e {today_str}. Voce e um editor jornalistico especializado em politica e economia brasileira.

Use a ferramenta de busca para encontrar as {NUM_NEWS} noticias mais importantes sobre POLITICA e ECONOMIA no Brasil publicadas hoje ou nas ultimas 24 horas.

Busque especificamente nestas fontes:
- ICL Noticias (iclnoticias.com.br)
- Intercept Brasil (theintercept.com/brasil)
- Revista Forum (revistaforum.com.br)
- Folha de Sao Paulo (folha.uol.com.br)
- Agencia Brasil (agenciabrasil.ebc.com.br)

Retorne SOMENTE o JSON abaixo, sem texto antes ou depois, sem markdown, sem blocos de codigo:

{{"resumo_editorial":"2-3 frases sobre o panorama politico-economico do dia.","noticias":[{{"titulo":"titulo claro e direto","fonte":"nome da fonte","categoria":"Politica ou Economia ou Internacional","resumo":"2-3 frases sobre o fato e sua relevancia.","importancia":8}}]}}

Exatamente {NUM_NEWS} noticias. importancia e inteiro de 1 a 10."""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
            max_output_tokens=2048,
        )
    )

    raw = response.text
    print(f"[OK] Resposta recebida ({len(raw)} chars)")

    clean = raw.replace("```json", "").replace("```", "").strip()
    s = clean.find("{")
    e = clean.rfind("}")
    if s == -1 or e == -1:
        print(f"[ERR] Texto recebido:\n{raw[:500]}")
        raise RuntimeError("JSON nao encontrado na resposta da API.")

    clean = clean[s:e+1]
    data  = json.loads(clean)

    n = len(data.get("noticias", []))
    print(f"[OK] {n} noticias parseadas com sucesso.")

    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()
    return data


def main():
    print("=" * 50)
    print("PANORAMA — Gerador de Boletim (Gemini)")
    print("=" * 50)

    retries = 3
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
                print("Aguardando 15s antes da proxima tentativa...", file=sys.stderr)
                time.sleep(15)
            else:
                print("Todas as tentativas falharam.", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
