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

    prompt = f"""Hoje e {today_str}. Voce e um pesquisador jornalistico experiente cobrindo Brasil.

Sua tarefa: encontrar {NUM_NEWS} noticias reais sobre politica e economia brasileira das ultimas 48 horas.

ESTRATEGIA DE BUSCA — faca multiplas buscas ate completar {NUM_NEWS} noticias:
1. Busque: "politica brasil hoje {today_str}"
2. Busque: "economia brasil hoje {today_str}"
3. Busque: "governo lula congresso nacional hoje"
4. Busque: "mercado financeiro brasil hoje"
5. Busque: "STF senado camara hoje brasil"
6. Se ainda faltar noticias: busque temas como inflacao, emprego, agronegocio, eleicoes, relacoes exteriores, saude publica, educacao, seguranca publica no brasil

FONTES ACEITAS (use qualquer uma destas):
Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao, Valor Economico,
ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato, Carta Capital,
CNN Brasil, Band News, Metropoles, Reuters Brasil, AFP Brasil, El Pais Brasil,
CartaCapital, Agencia Publica, Opera Mundi, Piaui, Epoca, IstoE, Exame,
InfoMoney, Bloomberg Linea, Nexo Jornal, The Intercept Brasil, Correio Braziliense,
R7 (somente noticias factuais), Terra Noticias, UOL Noticias, MSN Noticias Brasil

FONTES PROIBIDAS: Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News,
O Antagonista, Gazeta do Povo (secao de opiniao), Oeste, Crusoe, qualquer
veiculo de orientacao editorial de extrema-direita.

REGRA CRITICA: Se nao encontrar noticias suficientes nas primeiras buscas,
AMPLIE o tema e busque mais. NUNCA escreva "nao foi possivel encontrar" ou "N/A".
Sempre existe noticia relevante sobre o Brasil — busque ate encontrar {NUM_NEWS}.

Para cada noticia, escreva:
NOTICIA [numero]
Titulo: [titulo completo e informativo]
Fonte: [nome do veiculo de comunicacao]
Categoria: [Politica / Economia / Internacional]
Resumo: [2-3 frases descrevendo o fato e sua relevancia]
Corpo: [3-4 paragrafos com contexto, fatos, declaracoes e impacto]
URL: [URL completa do artigo ou vazio]
Importancia: [1 a 10]
---

Liste exatamente {NUM_NEWS} noticias reais. Nenhum placeholder. Nenhum N/A."""

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
    # e filtra entradas vazias/N/A geradas pelo modelo
    noticias_validas = []
    for n in data.get("noticias", []):
        titulo = n.get("titulo", "").strip()
        # Descarta entradas N/A ou placeholder
        if (not titulo
                or titulo.lower().startswith("n/a")
                or titulo.lower().startswith("nao foi possivel")
                or titulo.lower().startswith("não foi possível")
                or len(titulo) < 10):
            print(f"   [SKIP] Entrada invalida descartada: {titulo[:60]}")
            continue
        if n.get("corpo"):
            n["corpo"] = n["corpo"].replace(" | ", "\n\n")
        if not n.get("url", "").startswith("http"):
            n["url"] = ""
        noticias_validas.append(n)

    data["noticias"] = noticias_validas
    print(f"[OK] {len(noticias_validas)} noticias validas apos filtro.")

    if len(noticias_validas) < 5:
        raise RuntimeError(f"Poucas noticias validas: {len(noticias_validas)}. Tentando novamente.")

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
