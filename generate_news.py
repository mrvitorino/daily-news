#!/usr/bin/env python3
"""
generate_news.py — Boletim Geral de Noticias
5 categorias: Politica, Economia, Cultura, Tecnologia, Entretenimento
Cada categoria: ate 20 noticias
Zero JSON intermediario — tudo regex + json.dump final
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

OUTPUT = "news-data.json"
MODEL  = "gemini-2.5-flash"

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
    return "Edicao Matutina (08h)" if hour < 12 else "Edicao Vespertina (17h)"

def gemini_search(client, prompt, max_tokens=4000):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1, max_output_tokens=max_tokens,
        )
    )
    return resp.text or ""

def gemini_text(client, prompt, max_tokens=800, temp=0.3):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=temp, max_output_tokens=max_tokens)
    )
    return resp.text or ""

BLOCO = """##INICIO##
TITULO>> [titulo]
FONTE>> [fonte]
CATEGORIA>> [categoria]
IMPORTANCIA>> [1-10]
URL>> [url ou vazio]
##FIM##"""

FONTES_OK = ("Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao, Valor Economico, "
             "ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato, Carta Capital, "
             "CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal, Bloomberg Linea, "
             "Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney, Opera Mundi, Band News, "
             "Correio Braziliense, AFP Brasil, R7 Noticias, Veja, Medio Ambiente News, "
             "The Verge, Wired, TechCrunch, Ars Technica, MIT Technology Review, "
             "Canaltech, TecMundo, Olhar Digital, Convergencia Digital, "
             "Variety, Hollywood Reporter, Deadline, Screen Rant, IGN, "
             "Movieweb, Rolling Stone Brasil, Billboard Brasil, Quatro Rodas.")
FONTES_NO  = "Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista."

def parse_blocos(txt, categoria_esperada=None):
    blocos = re.findall(r'##INICIO##(.*?)##FIM##', txt, re.DOTALL)
    noticias = []
    for bloco in blocos:
        def ex(c):
            m = re.search(rf'{c}>>\s*(.+)', bloco)
            return m.group(1).strip() if m else ""
        titulo    = ex("TITULO")
        fonte     = ex("FONTE") or "Redacao"
        categoria = ex("CATEGORIA") or categoria_esperada or "Geral"
        imp_str   = ex("IMPORTANCIA")
        url       = ex("URL")

        if not titulo or len(titulo) < 8:
            continue
        if any(x in titulo.lower() for x in ["n/a","nao foi","nao encontr","não foi","placeholder","[titulo"]):
            continue
        try:
            imp = int(re.search(r'\d+', imp_str).group())
        except Exception:
            imp = 5
        if not url.startswith("http"):
            url = ""
        noticias.append({
            "titulo":      titulo,
            "fonte":       fonte,
            "categoria":   categoria,
            "url":         url,
            "importancia": min(10, max(1, imp)),
        })
    return noticias

def deduplicar(lista):
    vistas = set()
    out = []
    for n in lista:
        chave = " ".join(n["titulo"].lower().split()[:7])
        if chave not in vistas:
            vistas.add(chave)
            out.append(n)
    return out

# ─── BUSCAS POR CATEGORIA ───────────────

def buscar_politica(client, today_str, max_n=20):
    print("[..] Buscando: Politica...")
    temas = [
        ("politica brasileira congresso STF hoje", 7),
        ("governo lula ministerios politicas publicas hoje", 7),
        ("eleicoes partidos politicos brasil recente", 6),
    ]
    todas = []
    for tema, n in temas:
        prompt = f"""Hoje e {today_str}. Encontre {n} noticias sobre {tema} das ultimas 48h.
FONTES ACEITAS: {FONTES_OK}
PROIBIDO: {FONTES_NO}
Use o formato abaixo para CADA noticia (exatamente {n} blocos):
{BLOCO}
CATEGORIA deve ser: Politica
NUNCA escreva N/A."""
        txt = gemini_search(client, prompt, 3000)
        enc = parse_blocos(txt, "Politica")
        print(f"   {tema[:40]}: {len(enc)}")
        todas.extend(enc)
        time.sleep(3)
    return deduplicar(todas)[:max_n]

def buscar_economia(client, today_str, max_n=20):
    print("[..] Buscando: Economia...")
    temas = [
        ("economia brasileira mercado financeiro bolsa hoje", 7),
        ("inflacao emprego renda salario brasil hoje", 7),
        ("comercio exterior agronegocio industria brasil recente", 6),
    ]
    todas = []
    for tema, n in temas:
        prompt = f"""Hoje e {today_str}. Encontre {n} noticias sobre {tema} das ultimas 48h.
FONTES ACEITAS: {FONTES_OK}
PROIBIDO: {FONTES_NO}
Use o formato abaixo para CADA noticia (exatamente {n} blocos):
{BLOCO}
CATEGORIA deve ser: Economia
NUNCA escreva N/A."""
        txt = gemini_search(client, prompt, 3000)
        enc = parse_blocos(txt, "Economia")
        print(f"   {tema[:40]}: {len(enc)}")
        todas.extend(enc)
        time.sleep(3)
    return deduplicar(todas)[:max_n]

def buscar_cultura(client, today_str, max_n=20):
    print("[..] Buscando: Cultura...")
    temas = [
        ("cultura arte literatura musica brasil hoje", 7),
        ("teatro cinema exposicao museu festival brasil recente", 7),
        ("patrimonio historico gastronomia moda design brasil hoje", 6),
    ]
    todas = []
    for tema, n in temas:
        prompt = f"""Hoje e {today_str}. Encontre {n} noticias sobre {tema} das ultimas 48h.
FONTES ACEITAS: {FONTES_OK}
PROIBIDO: {FONTES_NO}
Use o formato abaixo para CADA noticia (exatamente {n} blocos):
{BLOCO}
CATEGORIA deve ser: Cultura
NUNCA escreva N/A."""
        txt = gemini_search(client, prompt, 3000)
        enc = parse_blocos(txt, "Cultura")
        print(f"   {tema[:40]}: {len(enc)}")
        todas.extend(enc)
        time.sleep(3)
    return deduplicar(todas)[:max_n]

def buscar_tecnologia(client, today_str, max_n=20):
    print("[..] Buscando: Tecnologia...")
    temas = [
        ("tecnologia inteligencia artificial startups brasil hoje", 7),
        ("inovacao tecnologica gadgets software hardware mundial recente", 7),
        ("ciberseguranca privacidade regulacao digital brasil mundo hoje", 6),
    ]
    todas = []
    for tema, n in temas:
        prompt = f"""Hoje e {today_str}. Encontre {n} noticias sobre {tema} das ultimas 48h.
FONTES ACEITAS: {FONTES_OK}
PROIBIDO: {FONTES_NO}
Use o formato abaixo para CADA noticia (exatamente {n} blocos):
{BLOCO}
CATEGORIA deve ser: Tecnologia
NUNCA escreva N/A."""
        txt = gemini_search(client, prompt, 3000)
        enc = parse_blocos(txt, "Tecnologia")
        print(f"   {tema[:40]}: {len(enc)}")
        todas.extend(enc)
        time.sleep(3)
    return deduplicar(todas)[:max_n]

def buscar_entretenimento(client, today_str, max_n=20):
    print("[..] Buscando: Entretenimento...")
    temas = [
        ("lancamentos filmes series Netflix Amazon Prime Video 2026", 8),
        ("lancamentos HBO Max Apple TV Plus Disney Plus novidades 2026", 7),
        ("cinema bilheteria estreias criticas filmes series recente", 5),
    ]
    todas = []
    for tema, n in temas:
        prompt = f"""Hoje e {today_str}. Encontre {n} noticias ou lancamentos sobre {tema}.
Inclua filmes e series lancados recentemente ou anunciados para breve.
FONTES ACEITAS: {FONTES_OK}
Use o formato abaixo para CADA item (exatamente {n} blocos):
{BLOCO}
CATEGORIA deve ser: Entretenimento
NUNCA escreva N/A."""
        txt = gemini_search(client, prompt, 3000)
        enc = parse_blocos(txt, "Entretenimento")
        print(f"   {tema[:40]}: {len(enc)}")
        todas.extend(enc)
        time.sleep(3)
    return deduplicar(todas)[:max_n]

# ─── TEXTO EXPANDIDO ─────────────────────

def gerar_texto(client, noticia):
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    cat    = noticia["categoria"]

    prompt = f"""Escreva um texto jornalistico completo sobre:

Titulo: {titulo}
Fonte: {fonte}
Categoria: {cat}

Formato obrigatorio (siga exatamente):
RESUMO>> escreva aqui duas frases descrevendo o fato e sua importancia
PARAGRAFO1>> escreva aqui o primeiro paragrafo com contexto e antecedentes
PARAGRAFO2>> escreva aqui o segundo paragrafo com fatos detalhados e declaracoes relevantes
PARAGRAFO3>> escreva aqui o terceiro paragrafo com impacto consequencias e desdobramentos esperados

Regras:
- Use aspas simples se precisar de aspas, NUNCA aspas duplas
- Portugues brasileiro formal
- Cada paragrafo deve ter no minimo 3 linhas
- Baseie-se no titulo fornecido"""

    try:
        txt = gemini_text(client, prompt, max_tokens=900, temp=0.3)

        def ex(campo):
            m = re.search(rf'{campo}>>\s*(.+?)(?=\n[A-Z]+[0-9]*>>|\Z)', txt, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else ""

        resumo = ex("RESUMO") or titulo
        p1 = ex("PARAGRAFO1")
        p2 = ex("PARAGRAFO2")
        p3 = ex("PARAGRAFO3")
        corpo = "\n\n".join(p for p in [p1, p2, p3] if p) or resumo
        return resumo, corpo
    except Exception as e:
        print(f"      [WARN] texto: {e}")
        return titulo, titulo

def gerar_editorial(client, todas_noticias, today_str):
    sample = [n["titulo"] for n in todas_noticias if n["categoria"] in ["Politica","Economia"]][:6]
    titulos = "\n".join(f"- {t}" for t in sample)
    prompt = f"""Com base nestas noticias de hoje ({today_str}):
{titulos}

Escreva um resumo editorial de 2 frases sobre o panorama do dia no Brasil.
Apenas as frases, sem titulo, sem aspas duplas."""
    try:
        return gemini_text(client, prompt, max_tokens=150, temp=0.2).strip()
    except Exception:
        return "O cenario brasileiro segue movimentado com destaque para politica, economia e cultura."

# ─── ORQUESTRADOR ────────────────────────

def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY","").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key ({len(api_key)} chars)")

    client    = genai.Client(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    # Busca por categoria
    politica      = buscar_politica(client, today_str)
    economia      = buscar_economia(client, today_str)
    cultura       = buscar_cultura(client, today_str)
    tecnologia    = buscar_tecnologia(client, today_str)
    entretenimento= buscar_entretenimento(client, today_str)

    todas = politica + economia + cultura + tecnologia + entretenimento
    print(f"\n[OK] Total: Pol={len(politica)} Eco={len(economia)} Cul={len(cultura)} "
          f"Tec={len(tecnologia)} Ent={len(entretenimento)}")

    if len(todas) < 5:
        raise RuntimeError(f"Apenas {len(todas)} noticias — insuficiente.")

    # Gera resumo + corpo
    print(f"\n[..] Gerando textos para {len(todas)} noticias...")
    for i, n in enumerate(todas):
        print(f"   [{i+1}/{len(todas)}] {n['titulo'][:55]}...")
        resumo, corpo = gerar_texto(client, n)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        if i < len(todas) - 1:
            time.sleep(1)

    editorial = gerar_editorial(client, todas, today_str)

    return {
        "resumo_editorial":  editorial,
        "noticias":          todas,
        "por_categoria": {
            "Politica":       len(politica),
            "Economia":       len(economia),
            "Cultura":        len(cultura),
            "Tecnologia":     len(tecnologia),
            "Entretenimento": len(entretenimento),
        },
        "generated_at":  now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label": get_edition_label(now_br.hour),
        "date_display":  today_str.upper(),
    }

def main():
    print("=" * 52)
    print("BOLETIM GERAL DE NOTICIAS — Gerador")
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
