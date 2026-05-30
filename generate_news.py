#!/usr/bin/env python3
"""
generate_news.py
Chama a API da Anthropic com web_search para buscar notícias
e grava news-data.json que a página HTML consome.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import anthropic

# ── Config ──────────────────────────────────────────────────
BRASILIA = ZoneInfo("America/Sao_Paulo")
NUM_NEWS = 10
OUTPUT   = "news-data.json"
MODEL    = "claude-sonnet-4-20250514"


def get_edition_label(hour: int) -> str:
    if hour < 10:
        return "Edição Matutina (08h)"
    elif hour < 14:
        return "Edição do Meio-Dia (12h)"
    else:
        return "Edição Vespertina (17h)"


def build_prompt(today_str: str, num: int) -> str:
    return f"""Hoje é {today_str}. Você é um editor jornalístico especializado em política e economia brasileira.

Use sua ferramenta de busca web para encontrar as {num} notícias mais importantes e recentes sobre POLÍTICA e ECONOMIA no Brasil publicadas HOJE ou nas últimas 24 horas.

Busque especificamente nestas fontes:
- ICL Notícias: iclnoticias.com.br
- Intercept Brasil: theintercept.com/brasil
- Revista Fórum: revistaforum.com.br
- Folha de São Paulo: folha.uol.com.br
- Agência Brasil: agenciabrasil.ebc.com.br

Faça pelo menos 4 buscas diferentes cobrindo essas fontes. Exemplos de queries:
- "política Brasil hoje {today_str}"
- "governo Lula congresso hoje"
- "economia mercado Brasil hoje"
- "site:iclnoticias.com.br hoje política"
- "site:revistaforum.com.br hoje"

Retorne APENAS JSON válido, sem texto antes ou depois, sem markdown, sem blocos de código:

{{"resumo_editorial":"2-3 frases sobre o panorama político-econômico do dia.","noticias":[{{"titulo":"Título direto","fonte":"Nome da fonte","categoria":"Política ou Economia ou Internacional","resumo":"2-3 frases sobre o fato e sua relevância.","importancia":8}}]}}

Retorne exatamente {num} notícias. importancia é inteiro de 1 a 10."""


def fetch_news() -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    now_br    = datetime.now(BRASILIA)
    today_str = now_br.strftime("%A, %d de %B de %Y")
    prompt    = build_prompt(today_str, NUM_NEWS)

    print(f"[{now_br.isoformat()}] Buscando notícias…")

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Extrair bloco de texto
    json_text = ""
    for block in resp.content:
        if block.type == "text":
            json_text = block.text
            break

    if not json_text:
        raise ValueError("API não retornou bloco de texto.")

    # Limpar possíveis fences
    json_text = json_text.replace("```json", "").replace("```", "").strip()
    start = json_text.find("{")
    end   = json_text.rfind("}")
    if start != -1 and end != -1:
        json_text = json_text[start:end + 1]

    data = json.loads(json_text)

    # Adicionar metadados
    data["generated_at"]  = now_br.isoformat()
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = now_br.strftime("%A, %d de %B de %Y").upper()

    print(f"OK — {len(data.get('noticias', []))} notícias coletadas.")
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
