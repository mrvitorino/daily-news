#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Estrategia em 2 passos por noticia:
  Passo A: busca com google_search (texto livre)
  Passo B: formata em JSON sem ferramenta (response_mime_type=json funciona aqui)
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


# ─────────────────────────────────────────
# PASSO A — busca livre com google_search
# Retorna texto bruto com as noticias encontradas
# ─────────────────────────────────────────
def search_noticias(client, today_str):
    print("[..] Passo A: buscando noticias com Google Search...")

    prompt = f"""Hoje e {today_str}. Voce e um pesquisador jornalistico.

Use a ferramenta de busca para encontrar as {NUM_NEWS} noticias mais importantes sobre POLITICA e ECONOMIA no Brasil publicadas hoje ou nas ultimas 48 horas.

Priorize: Folha de S.Paulo, Agencia Brasil, ICL Noticias, Intercept Brasil, Revista Forum.
Complemente com: G1, UOL, Estadao, Valor Economico, CNN Brasil.

Para cada noticia encontrada, escreva em texto simples:
NOTICIA [numero]
Titulo: [titulo completo]
Fonte: [nome do veiculo]
Categoria: [Politica / Economia / Internacional]
Resumo: [2-3 frases descrevendo o fato e sua relevancia]
Corpo: [3-4 paragrafos detalhados com contexto, fatos, declaracoes e impacto]
URL: [URL completa do artigo se disponivel, ou deixe em branco]
Importancia: [numero de 1 a 10]
---

Liste exatamente {NUM_NEWS} noticias."""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=8192,
        )
    )
    raw = resp.text
    print(f"[OK] Texto bruto: {len(raw)} chars")
    return raw


# ─────────────────────────────────────────
# PASSO B — formata texto em JSON
# Sem google_search → response_mime_type funciona
# ─────────────────────────────────────────
def format_to_json(client, raw_text, today_str):
    print("[..] Passo B: formatando em JSON estruturado...")

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
                        "resumo":      {"type": "string"},
                        "corpo":       {"type": "string"},
                        "url":         {"type": "string"},
                        "importancia": {"type": "integer"}
                    },
                    "required": ["titulo","fonte","categoria","resumo","corpo","url","importancia"]
                }
            }
        },
        "required": ["resumo_editorial","noticias"]
    }

    prompt = f"""Converta o texto abaixo para JSON estruturado.

Regras importantes:
- resumo_editorial: 2-3 frases resumindo o panorama politico-economico do dia
- noticias: array com exatamente {NUM_NEWS} objetos
- corpo: texto completo dos paragrafos, separados por " | " (espaco pipe espaco)
- url: URL do artigo se disponivel, caso contrario string vazia ""
- importancia: inteiro de 1 a 10
- NAO invente informacoes que nao estejam no texto abaixo

TEXTO:
{raw_text}"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=schema,
        )
    )

    data = json.loads(resp.text)
    print(f"[OK] JSON parseado: {len(data.get('noticias',[]))} noticias")

    # Converte separador " | " em quebras de paragrafo reais
    for n in data.get("noticias", []):
        if n.get("corpo"):
            n["corpo"] = n["corpo"].replace(" | ", "\n\n")
        # Valida URL
        if not n.get("url", "").startswith("http"):
            n["url"] = ""

    return data


# ─────────────────────────────────────────
# ORQUESTRADOR
# ─────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key encontrada ({len(api_key)} chars)")

    client    = genai.Client(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] Data: {today_str} | Edicao: {get_edition_label(now_br.hour)}")

    # Passo A: busca com google_search
    raw_text = search_noticias(client, today_str)

    # Pequena pausa entre chamadas
    time.sleep(3)

    # Passo B: formata sem google_search (JSON puro garantido)
    data = format_to_json(client, raw_text, today_str)

    if not data.get("noticias"):
        raise RuntimeError("Nenhuma noticia no JSON final.")

    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()
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
            print("=" * 52)
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
