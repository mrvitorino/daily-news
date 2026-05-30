#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Usa response_mime_type=application/json para garantir JSON puro do Gemini.
Etapa 1: lista de noticias (JSON enxuto)
Etapa 2: corpo individual de cada noticia
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

def safe_parse(text):
    """
    Tenta parsear JSON de forma robusta:
    1. Direto
    2. Removendo fences de markdown
    3. Extraindo primeiro objeto { } encontrado
    4. Reparando aspas simples trocadas por duplas
    """
    attempts = [
        text.strip(),
        re.sub(r"```(?:json)?|```", "", text).strip(),
    ]
    # Tenta extrair entre { e }
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        attempts.append(m.group(0))

    for candidate in attempts:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Ultima tentativa: corrigir aspas dentro de strings
    # (Gemini as vezes usa " dentro de valores sem escapar)
    try:
        # Substitui quebras de linha dentro de strings JSON por \n
        fixed = re.sub(r'(?<=: ")(.*?)(?="(?:\s*[,}\]]))',
                       lambda m: m.group(0).replace('\n', '\\n').replace('"', '\\"'),
                       text, flags=re.DOTALL)
        m2 = re.search(r'\{.*\}', fixed, re.DOTALL)
        if m2:
            return json.loads(m2.group(0))
    except Exception:
        pass

    raise RuntimeError(f"Nao foi possivel parsear JSON. Preview: {text[:300]}")


# ─────────────────────────────────────────
# ETAPA 1 — lista de noticias
# ─────────────────────────────────────────
def fetch_noticias(client, today_str):
    print("[..] Etapa 1: buscando lista de noticias...")

    schema = {
        "type": "object",
        "properties": {
            "resumo_editorial": {"type": "string"},
            "noticias": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id":        {"type": "integer"},
                        "titulo":    {"type": "string"},
                        "fonte":     {"type": "string"},
                        "categoria": {"type": "string"},
                        "resumo":    {"type": "string"},
                        "importancia": {"type": "integer"}
                    },
                    "required": ["id","titulo","fonte","categoria","resumo","importancia"]
                }
            }
        },
        "required": ["resumo_editorial","noticias"]
    }

    prompt = f"""Hoje e {today_str}. Voce e um editor jornalistico especializado em politica e economia brasileira.

Use a ferramenta de busca para encontrar as {NUM_NEWS} noticias mais importantes sobre POLITICA e ECONOMIA no Brasil publicadas hoje ou nas ultimas 48 horas.

Priorize: Folha de S.Paulo, Agencia Brasil, ICL Noticias, Intercept Brasil, Revista Forum.
Complemente com: G1, UOL, Estadao, Valor Economico, CNN Brasil.

Retorne um objeto JSON com:
- resumo_editorial: 2-3 frases sobre o panorama politico-economico do dia
- noticias: array com exatamente {NUM_NEWS} objetos, cada um com id (1 a {NUM_NEWS}), titulo, fonte, categoria (Politica/Economia/Internacional), resumo (2-3 frases), importancia (1-10)"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=schema,
        )
    )

    raw = resp.text
    print(f"[OK] Resposta etapa 1: {len(raw)} chars")
    data = safe_parse(raw)

    noticias = data.get("noticias", [])
    print(f"[OK] {len(noticias)} noticias parseadas.")
    if not noticias:
        raise RuntimeError("Nenhuma noticia retornada.")
    return data


# ─────────────────────────────────────────
# ETAPA 2 — corpo individual
# ─────────────────────────────────────────
def fetch_corpo(client, noticia, today_str):
    titulo = noticia.get("titulo", "")
    fonte  = noticia.get("fonte", "")
    print(f"   [..] Corpo: {titulo[:55]}...")

    schema = {
        "type": "object",
        "properties": {
            "corpo": {"type": "string"},
            "url":   {"type": "string"}
        },
        "required": ["corpo", "url"]
    }

    prompt = f"""Hoje e {today_str}. Busque esta noticia:

Titulo: {titulo}
Fonte preferencial: {fonte}

Retorne:
- corpo: texto jornalistico completo em 3-4 paragrafos descrevendo contexto, fatos, declaracoes e impacto. Separe paragrafos com barra vertical (|) em vez de quebra de linha.
- url: URL direta e completa do artigo original (comecando com https://). Se nao encontrar, retorne string vazia."""

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_schema=schema,
            )
        )
        result = safe_parse(resp.text)
        # Converte separador | de volta para \n\n
        corpo = result.get("corpo", "").replace(" | ", "\n\n").replace("|", "\n\n")
        url   = result.get("url", "")
        # Valida URL
        if not url.startswith("http"):
            url = ""
        return corpo, url
    except Exception as e:
        print(f"   [WARN] Falha no corpo ({e.__class__.__name__}): {e}")
        return noticia.get("resumo", ""), ""


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

    data = fetch_noticias(client, today_str)

    print(f"\n[..] Etapa 2: buscando corpo das {len(data['noticias'])} noticias...")
    for i, noticia in enumerate(data["noticias"]):
        corpo, url = fetch_corpo(client, noticia, today_str)
        noticia["corpo"] = corpo
        noticia["url"]   = url
        if i < len(data["noticias"]) - 1:
            time.sleep(3)

    data["generated_at"]  = now_br.strftime("%Y-%m-%dT%H:%M:%S")
    data["edition_label"] = get_edition_label(now_br.hour)
    data["date_display"]  = today_str.upper()
    print(f"\n[OK] Concluido — {len(data['noticias'])} noticias com corpo.")
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
            print(f"[OK] Salvo em {OUTPUT}")
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
