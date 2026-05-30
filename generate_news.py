#!/usr/bin/env python3
"""
generate_news.py — Panorama Brasil
Passo A: busca com google_search → texto livre
Passo B: converte em JSON SEM corpo (curto, seguro)
Passo C: para cada noticia, busca corpo individualmente (chamadas pequenas)
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
# PASSO A — busca com google_search, retorna texto livre
# ─────────────────────────────────────────
def passo_a_buscar(client, today_str):
    print("[..] Passo A: buscando noticias com Google Search...")

    prompt = f"""Hoje e {today_str}. Voce e um pesquisador jornalistico cobrindo o Brasil.

Faca buscas e liste as {NUM_NEWS} noticias mais importantes sobre POLITICA e ECONOMIA
brasileira das ultimas 48 horas. Faca pelo menos 5 buscas diferentes:
1. "politica brasil hoje"
2. "economia brasil hoje"
3. "governo lula congresso hoje"
4. "mercado financeiro brasil hoje"
5. "STF eleicoes brasil recente"

FONTES ACEITAS: Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao,
Valor Economico, ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato,
Carta Capital, CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal,
Bloomberg Linea, Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney,
Opera Mundi, Correio Braziliense, Band News, AFP Brasil.

FONTES PROIBIDAS: Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News,
O Antagonista, Gazeta do Povo opiniao, Oeste, Crusoe, extrema-direita.

IMPORTANTE: Liste exatamente {NUM_NEWS} noticias reais. NUNCA escreva N/A ou
"nao foi possivel encontrar". Se precisar, amplie os temas para saude,
educacao, meio ambiente, seguranca publica, relacoes internacionais do Brasil.

Para cada noticia escreva:
NOTICIA [n]
TITULO: texto do titulo
FONTE: nome do veiculo
CATEGORIA: Politica ou Economia ou Internacional
RESUMO: duas ou tres frases sobre o fato
URL: url completa se disponivel
IMPORTANCIA: numero de 1 a 10
FIM"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=6000,
        )
    )
    txt = resp.text
    print(f"[OK] Passo A: {len(txt)} chars")
    return txt


# ─────────────────────────────────────────
# PASSO B — converte texto em JSON CURTO (sem corpo)
# Sem google_search → response_mime_type funciona
# ─────────────────────────────────────────
def passo_b_estruturar(client, raw_text, today_str):
    print("[..] Passo B: estruturando em JSON (sem corpo)...")

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
                        "url":         {"type": "string"},
                        "importancia": {"type": "integer"}
                    },
                    "required": ["titulo","fonte","categoria","resumo","url","importancia"]
                }
            }
        },
        "required": ["resumo_editorial","noticias"]
    }

    prompt = f"""Converta o texto abaixo em JSON estruturado.

Regras:
- resumo_editorial: 2-3 frases sobre o panorama politico-economico do dia
- noticias: array com os itens encontrados no texto
- resumo: apenas 2-3 frases curtas (nao inclua texto longo)
- url: URL do artigo se disponivel no texto, senao string vazia
- importancia: inteiro 1-10
- IGNORE entradas com titulo "N/A" ou "nao foi possivel"
- NAO invente nada que nao esteja no texto

TEXTO:
{raw_text[:6000]}"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=4000,
            response_mime_type="application/json",
            response_schema=schema,
        )
    )

    data = json.loads(resp.text)

    # Filtrar N/A
    validas = []
    for n in data.get("noticias", []):
        t = n.get("titulo", "").strip()
        if (not t or len(t) < 10
                or t.lower().startswith("n/a")
                or "nao foi possivel" in t.lower()
                or "não foi possível" in t.lower()):
            print(f"   [SKIP] {t[:60]}")
            continue
        if not n.get("url","").startswith("http"):
            n["url"] = ""
        validas.append(n)

    data["noticias"] = validas
    print(f"[OK] Passo B: {len(validas)} noticias validas.")

    if len(validas) < 5:
        raise RuntimeError(f"Apenas {len(validas)} noticias validas — minimo e 5.")
    return data


# ─────────────────────────────────────────
# PASSO C — corpo individual por noticia
# Chamada pequena e isolada por noticia
# ─────────────────────────────────────────
def passo_c_corpo(client, noticia, today_str):
    titulo = noticia.get("titulo","")
    fonte  = noticia.get("fonte","")
    resumo = noticia.get("resumo","")
    print(f"   [..] Corpo: {titulo[:55]}...")

    prompt = f"""Escreva um texto jornalistico completo sobre esta noticia:

Titulo: {titulo}
Fonte: {fonte}
Resumo: {resumo}

Escreva 3 paragrafos em portugues brasileiro formal, separados pela sequencia PARAGRAFO.
Inclua contexto historico, fatos principais, declaracoes relevantes e impacto.
Use apenas informacoes que condizem com o titulo e resumo acima.
Nao use aspas duplas no texto.
Escreva apenas os paragrafos, sem titulo nem introducao."""

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1500,
            )
        )
        txt = resp.text.strip()
        # Converte separador em quebras reais
        corpo = txt.replace("PARAGRAFO", "\n\n").strip()
        # Remove aspas duplas que possam ter sobrado
        corpo = corpo.replace('"', "'")
        return corpo
    except Exception as e:
        print(f"   [WARN] Corpo falhou: {e}")
        return resumo  # fallback: usa o resumo


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

    # Passo A: busca
    raw = passo_a_buscar(client, today_str)
    time.sleep(2)

    # Passo B: estrutura em JSON curto
    data = passo_b_estruturar(client, raw, today_str)
    time.sleep(2)

    # Passo C: corpo de cada noticia (sem google_search, sem JSON forçado)
    print(f"[..] Passo C: gerando corpo de {len(data['noticias'])} noticias...")
    for i, n in enumerate(data["noticias"]):
        n["corpo"] = passo_c_corpo(client, n, today_str)
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
