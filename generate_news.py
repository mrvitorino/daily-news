#!/usr/bin/env python3
"""
generate_news.py
Chama a API da Anthropic com web_search para buscar noticias
e grava news-data.json que a pagina HTML consome.
"""

import json
import os
import sys
import time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    BRASILIA = ZoneInfo("America/Sao_Paulo")
except Exception:
    # Fallback: UTC-3
    from datetime import timezone, timedelta
    BRASILIA = timezone(timedelta(hours=-3))

import anthropic

NUM_NEWS = 10
OUTPUT   = "news-data.json"
MODEL    = "claude-sonnet-4-20250514"

WEEKDAYS_PT = {
    "Monday": "segunda-feira", "Tuesday": "terca-feira",
    "Wednesday": "quarta-feira", "Thursday": "quinta-feira",
    "Friday": "sexta-feira", "Saturday": "sabado", "Sunday": "domingo"
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
    if hour < 10:
        return "Edicao Matutina (08h)"
    elif hour < 14:
        return "Edicao do Meio-Dia (12h)"
    else:
        return "Edicao Vespertina (17h)"

def build_prompt(today_str, num):
    return f"""Hoje e {today_str}. Voce e um editor jornalistico especializado em politica e economia brasileira.

Use sua ferramenta de busca web para encontrar as {num} noticias mais importantes e recentes sobre POLITICA e ECONOMIA no Brasil publicadas HOJE ou nas ultimas 24 horas.

Busque especificamente nestas fontes:
- ICL Noticias: iclnoticias.com.br
- Intercept Brasil: theintercept.com/brasil
- Revista Forum: revistaforum.com.br
- Folha de Sao Paulo: folha.uol.com.br
- Agencia Brasil: agenciabrasil.ebc.com.br

Faca pelo menos 4 buscas diferentes. Exemplos de queries:
- "politica Brasil hoje {today_str}"
- "governo Lula congresso hoje"
- "economia mercado Brasil hoje"
- "site:iclnoticias.com.br politica hoje"
- "site:revistaforum.com.br hoje"

Retorne APENAS JSON valido, sem texto antes ou depois, sem markdown, sem blocos de codigo:

{{"resumo_editorial":"2-3 frases sobre o panorama politico-economico do dia.","noticias":[{{"titulo":"Titulo direto","fonte":"Nome da fonte","categoria":"Politica ou Economia ou Internacional","resumo":"2-3 frases sobre o fato e sua relevancia.","importancia":8}}]}}

Retorne exatamente {num} noticias. importancia e inteiro de 1 a 10."""

def fetch_news():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY nao definida. Adicione o secret no repositorio GitHub.")

    client = anthropic.Anthropic(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    prompt    = build_prompt(today_str, NUM_NEWS)

    print(f"[{now_br.strftime('%Y-%m-%d %H:%M')} BRT] Buscando noticias...")
    print(f"Data: {today_str}")

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    json_text = ""
    for block in resp.content:
        if block.type == "text":
            json_text = block.text
            break

    if not json_text:
        raise ValueError("API nao retornou bloco de texto.")

    json_text = json_text.replace("```json", "").replace("```", "").strip()
    start = json_text.find("{")
    end   = json_text.rfind("}")
    if start != -1 and end != -1:
        json_text = json_text[start:end + 1]

    data = json.loads(json_text)
    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()

    print(f"OK - {len(data.get('noticias', []))} noticias coletadas.")
    return data

def main():
    retries = 3
    for attempt in range(1, retries + 1):
        try:
            data = fetch_news()
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Salvo em {OUTPUT}")
            return
        except Exception as e:
            print(f"Tentativa {attempt}/{retries} falhou: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(10)
            else:
                sys.exit(1)

if __name__ == "__main__":
    main()
