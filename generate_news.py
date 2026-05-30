#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Busca noticias via Google Gemini API + Google Search e grava news-data.json
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

def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")

    print(f"[OK] API key encontrada ({len(api_key)} chars)")

    client = genai.Client(api_key=api_key)

    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    yesterday = now_br - timedelta(days=1)
    yesterday_str = format_date_pt(yesterday)

    print(f"[OK] Data: {today_str}")
    print(f"[OK] Edicao: {get_edition_label(now_br.hour)}")
    print("[..] Chamando Gemini API com Google Search...")

    prompt = f"""Voce e um editor jornalistico especializado em politica e economia brasileira. Hoje e {today_str}.

Sua tarefa: buscar e listar as {NUM_NEWS} noticias mais importantes sobre politica e economia do Brasil dos ultimos 2 dias ({yesterday_str} e {today_str}).

INSTRUCOES DE BUSCA:
- Faca multiplas buscas em portugues sobre politica e economia brasileira recente
- Priorize estas fontes: Folha de S.Paulo, Agencia Brasil, ICL Noticias, Intercept Brasil, Revista Forum
- Se nao encontrar nas fontes prioritarias, use qualquer fonte jornalistica brasileira confiavel (G1, UOL, Estadao, Valor Economico, CNN Brasil, etc)
- Busque por temas como: governo federal, congresso nacional, economia brasileira, mercado financeiro, politicas publicas, eleicoes, STF, banco central, inflacao, emprego
- Retorne sempre {NUM_NEWS} noticias, mesmo que precise usar fontes alternativas ou noticias de ate 48 horas atras

FORMATO DE RESPOSTA:
Retorne SOMENTE o JSON abaixo, sem texto antes ou depois, sem markdown, sem blocos de codigo:

{{"resumo_editorial":"2-3 frases resumindo o panorama politico-economico dos ultimos 2 dias no Brasil.","noticias":[{{"titulo":"titulo claro e direto da noticia","fonte":"nome do veiculo de imprensa","categoria":"Politica ou Economia ou Internacional","resumo":"2-3 frases explicando o que aconteceu e por que e relevante.","importancia":8}}]}}

OBRIGATORIO: retorne exatamente {NUM_NEWS} noticias. O campo importancia e um inteiro de 1 a 10."""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
            max_output_tokens=4096,
        )
    )

    raw = response.text
    print(f"[OK] Resposta recebida ({len(raw)} chars)")

    # Limpar e parsear JSON
    clean = raw.replace("```json", "").replace("```", "").strip()
    s = clean.find("{")
    e = clean.rfind("}")
    if s == -1 or e == -1:
        print(f"[ERR] Texto recebido:\n{raw[:800]}")
        raise RuntimeError("JSON nao encontrado na resposta da API.")

    clean = clean[s:e+1]
    data  = json.loads(clean)

    noticias = data.get("noticias", [])
    print(f"[OK] {len(noticias)} noticias parseadas.")

    if len(noticias) == 0:
        print(f"[ERR] Resposta completa:\n{raw[:1000]}")
        raise RuntimeError("API retornou 0 noticias.")

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
