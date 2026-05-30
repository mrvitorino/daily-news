#!/usr/bin/env python3
"""
generate_news.py — Boletim Geral de Noticias
5 categorias x 20 noticias. Zero JSON intermediario.
Corpo gerado com multiturno para garantir paragrafos reais.
"""

import json, os, re, sys, time, traceback
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

WEEKDAYS_PT = {"Monday":"segunda-feira","Tuesday":"terca-feira","Wednesday":"quarta-feira",
               "Thursday":"quinta-feira","Friday":"sexta-feira","Saturday":"sabado","Sunday":"domingo"}
MONTHS_PT   = {1:"janeiro",2:"fevereiro",3:"marco",4:"abril",5:"maio",6:"junho",
               7:"julho",8:"agosto",9:"setembro",10:"outubro",11:"novembro",12:"dezembro"}

def format_date_pt(dt):
    return f"{WEEKDAYS_PT.get(dt.strftime('%A'),dt.strftime('%A'))}, {dt.day} de {MONTHS_PT.get(dt.month)} de {dt.year}"

def get_edition_label(h):
    return "Edicao Matutina (08h)" if h < 12 else "Edicao Vespertina (17h)"

def gsearch(client, prompt, max_tokens=4000):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1, max_output_tokens=max_tokens))
    return resp.text or ""

def gtext(client, prompt, max_tokens=1000, temp=0.4):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=temp, max_output_tokens=max_tokens))
    return resp.text or ""

# ── PARSE DE BLOCOS ──────────────────────────────────────────────────────────
def parse_blocos(txt, cat_default):
    blocos = re.findall(r'##INICIO##(.*?)##FIM##', txt, re.DOTALL)
    out = []
    for b in blocos:
        def ex(c): m=re.search(rf'{c}>>\s*(.+)',b); return m.group(1).strip() if m else ""
        titulo = ex("TITULO")
        if not titulo or len(titulo)<8: continue
        if any(x in titulo.lower() for x in ["n/a","nao foi","placeholder","[titulo","não foi"]): continue
        fonte = ex("FONTE") or "Redacao"
        cat   = ex("CATEGORIA") or cat_default
        url   = ex("URL")
        # Rejeita URLs internas do Gemini/Google
        if "vertexaisearch" in url or "grounding-api" in url or not url.startswith("http"):
            url = ""
        try: imp = min(10, max(1, int(re.search(r'\d+', ex("IMPORTANCIA")).group())))
        except: imp = 5
        out.append({"titulo":titulo,"fonte":fonte,"categoria":cat,"url":url,"importancia":imp})
    return out

def dedup(lst):
    seen=set(); out=[]
    for n in lst:
        k=" ".join(n["titulo"].lower().split()[:7])
        if k not in seen: seen.add(k); out.append(n)
    return out

# ── TEMPLATE DE BUSCA ────────────────────────────────────────────────────────
FONTES_OK = ("Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao, Valor Economico, "
             "ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato, Carta Capital, "
             "CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal, Bloomberg Linea, "
             "Agencia Publica, Piaui, Epoca, IstoE, Exame, InfoMoney, Opera Mundi, Band News, "
             "Correio Braziliense, AFP Brasil, R7 Noticias, The Verge, Wired, TechCrunch, "
             "Ars Technica, MIT Technology Review, Canaltech, TecMundo, Olhar Digital, "
             "Variety, Hollywood Reporter, Deadline, Screen Rant, Rolling Stone Brasil")
FONTES_NO = "Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista"

BLOCO_TMPL = """##INICIO##
TITULO>> titulo da noticia aqui
FONTE>> nome do veiculo aqui
CATEGORIA>> categoria aqui
IMPORTANCIA>> numero de 1 a 10
URL>> url completa do artigo ou deixe em branco
##FIM##"""

def busca_prompt(tema, n, cat, today_str, extra=""):
    return f"""Hoje e {today_str}. Jornalista especializado em {cat}.

Busque e liste {n} noticias REAIS sobre {tema} das ultimas 48 horas.
{extra}
FONTES ACEITAS: {FONTES_OK}
PROIBIDO: {FONTES_NO}

Para cada noticia use EXATAMENTE este formato ({n} blocos obrigatorios):
{BLOCO_TMPL}

REGRAS ABSOLUTAS:
- Escreva exatamente {n} blocos ##INICIO## ... ##FIM##
- NUNCA escreva N/A ou "nao encontrado"
- URL deve ser do artigo original (ex: https://g1.globo.com/...) — se nao souber, deixe em branco
- CATEGORIA deve ser exatamente: {cat}"""

# ── BUSCAS POR CATEGORIA ─────────────────────────────────────────────────────
def buscar(client, today_str, categoria, temas_n, extra="", max_n=20):
    print(f"[..] Buscando: {categoria}...")
    todas = []
    for tema, n in temas_n:
        try:
            txt = gsearch(client, busca_prompt(tema, n, categoria, today_str, extra), 3500)
            enc = parse_blocos(txt, categoria)
            print(f"   '{tema[:45]}': {len(enc)}")
            todas.extend(enc)
            time.sleep(3)
        except Exception as e:
            print(f"   ERRO: {e}", file=sys.stderr)
            time.sleep(3)
    result = dedup(todas)
    result.sort(key=lambda x: x["importancia"], reverse=True)
    return result[:max_n]

def buscar_politica(client, today_str):
    return buscar(client, today_str, "Politica", [
        ("politica brasileira congresso nacional STF hoje", 7),
        ("governo lula ministerios politicas publicas hoje", 7),
        ("eleicoes partidos oposicao brasil recente", 6),
    ])

def buscar_economia(client, today_str):
    return buscar(client, today_str, "Economia", [
        ("economia brasileira mercado financeiro bolsa cambio hoje", 7),
        ("inflacao emprego renda salario PIB brasil hoje", 7),
        ("agronegocio industria exportacao importacao brasil recente", 6),
    ])

def buscar_cultura(client, today_str):
    return buscar(client, today_str, "Cultura", [
        ("cultura arte musica show concerto festival brasil 2026", 7),
        ("literatura livros teatro exposicao museu brasil recente", 7),
        ("gastronomia moda patrimonio historico cultura popular brasil 2026", 6),
    ], extra="Inclua eventos, lancamentos de albuns, livros, pecas de teatro, exposicoes.")

def buscar_tecnologia(client, today_str):
    return buscar(client, today_str, "Tecnologia", [
        ("inteligencia artificial IA tecnologia inovacao mundo 2026", 7),
        ("startups tecnologia brasil big tech Apple Google Microsoft Amazon 2026", 7),
        ("ciberseguranca privacidade regulacao digital internet 2026", 6),
    ], extra="Inclua noticias do Brasil e do mundo. Aceite fontes internacionais como The Verge, Wired, TechCrunch.")

def buscar_entretenimento(client, today_str):
    return buscar(client, today_str, "Entretenimento", [
        ("lancamentos filmes series Netflix Amazon Prime Video maio junho 2026", 8),
        ("lancamentos HBO Max Apple TV Disney Plus novidades 2026", 7),
        ("criticas cinema bilheteria estreias filmes series recente 2026", 5),
    ], extra="Inclua filmes em cartaz, series lancadas, renovacoes e cancelamentos.")

# ── GERAR CORPO ──────────────────────────────────────────────────────────────
def gerar_corpo(client, noticia):
    """Gera resumo e corpo em texto puro usando multiturno para garantir qualidade."""
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    cat    = noticia["categoria"]

    # Instrucao muito explicita para evitar resposta de uma linha
    prompt = f"""Voce e um jornalista. Escreva um texto completo sobre esta noticia:

TITULO: {titulo}
FONTE: {fonte}
CATEGORIA: {cat}

Escreva em 4 secoes separadas. Cada secao comeca com o marcador em maiusculas seguido de dois sinais de maior (>>).

RESUMO>> [Escreva aqui exatamente 2 frases completas descrevendo o fato principal e sua importancia. Minimo 30 palavras.]

PARAGRAFO1>> [Escreva aqui um paragrafo completo de pelo menos 4 linhas sobre o contexto e antecedentes desta noticia.]

PARAGRAFO2>> [Escreva aqui um paragrafo completo de pelo menos 4 linhas com os fatos detalhados, numeros e declaracoes de envolvidos.]

PARAGRAFO3>> [Escreva aqui um paragrafo completo de pelo menos 4 linhas sobre o impacto, consequencias e proximo passos esperados.]

IMPORTANTE:
- Use APENAS aspas simples se precisar de aspas
- Escreva em portugues brasileiro formal
- Cada secao deve ter conteudo substantivo — nao repita o titulo
- Base-se no titulo e categoria para inferir contexto plausivel"""

    try:
        txt = gtext(client, prompt, max_tokens=1200, temp=0.4)

        def ex(campo):
            # Regex robusto: captura tudo ate o proximo marcador ou fim
            m = re.search(
                rf'{campo}>>\s*([\s\S]+?)(?=\n[A-Z]+[0-9]*>>|\Z)',
                txt, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        resumo = ex("RESUMO")
        p1 = ex("PARAGRAFO1")
        p2 = ex("PARAGRAFO2")
        p3 = ex("PARAGRAFO3")

        # Valida que temos conteudo real
        if not resumo or len(resumo) < 20:
            # Tenta extrair qualquer paragrafo substancial do texto
            paragrafos = [p.strip() for p in txt.split('\n\n') if len(p.strip()) > 50]
            resumo = paragrafos[0] if paragrafos else titulo
            p1 = paragrafos[1] if len(paragrafos) > 1 else ""
            p2 = paragrafos[2] if len(paragrafos) > 2 else ""
            p3 = paragrafos[3] if len(paragrafos) > 3 else ""

        corpo = "\n\n".join(p for p in [p1, p2, p3] if p and len(p) > 20)
        if not corpo:
            corpo = resumo

        return resumo, corpo

    except Exception as e:
        print(f"      [WARN] corpo: {e}")
        return titulo, titulo

# ── GERAR URL REAL ───────────────────────────────────────────────────────────
def buscar_url(client, noticia):
    """Busca a URL real do artigo quando nao veio na etapa anterior."""
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    try:
        prompt = f"""Encontre a URL direta do artigo com este titulo publicado por {fonte}:

"{titulo}"

Responda APENAS com a URL completa (comecando com https://).
Se nao encontrar, responda apenas: NAO_ENCONTRADO"""
        txt = gsearch(client, prompt, max_tokens=200).strip()
        # Extrai URL do texto
        m = re.search(r'https?://[^\s\n"\'<>]+', txt)
        if m:
            url = m.group(0).rstrip('.,)')
            # Rejeita URLs internas do Gemini
            if "vertexaisearch" in url or "grounding-api" in url:
                return ""
            return url
    except Exception:
        pass
    return ""

# ── EDITORIAL ────────────────────────────────────────────────────────────────
def gerar_editorial(client, noticias, today_str):
    pol_eco = [n["titulo"] for n in noticias if n["categoria"] in ["Politica","Economia"]][:5]
    titulos = "\n".join(f"- {t}" for t in pol_eco)
    prompt = f"""Com base nestas noticias brasileiras de hoje ({today_str}):
{titulos}

Escreva um resumo editorial de 2 frases sobre o panorama politico-economico.
Apenas as frases. Use aspas simples. Sem titulo."""
    try:
        return gtext(client, prompt, max_tokens=150, temp=0.2).strip()
    except Exception:
        return "O cenario brasileiro segue movimentado com destaque para as agendas politica e economica."

# ── ORQUESTRADOR ─────────────────────────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY","").strip()
    if not api_key: raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key ({len(api_key)} chars)")

    client    = genai.Client(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    # Buscas por categoria
    politica       = buscar_politica(client, today_str)
    economia       = buscar_economia(client, today_str)
    cultura        = buscar_cultura(client, today_str)
    tecnologia     = buscar_tecnologia(client, today_str)
    entretenimento = buscar_entretenimento(client, today_str)

    todas = politica + economia + cultura + tecnologia + entretenimento
    print(f"\n[OK] Pol={len(politica)} Eco={len(economia)} Cul={len(cultura)} "
          f"Tec={len(tecnologia)} Ent={len(entretenimento)} Total={len(todas)}")

    if len(todas) < 5:
        raise RuntimeError(f"Apenas {len(todas)} noticias — insuficiente.")

    # Gera corpo + busca URL para quem nao tem
    print(f"\n[..] Gerando corpo para {len(todas)} noticias...")
    for i, n in enumerate(todas):
        print(f"   [{i+1}/{len(todas)}] {n['titulo'][:55]}...")
        resumo, corpo = gerar_corpo(client, n)
        n["resumo"] = resumo
        n["corpo"]  = corpo
        # Busca URL se veio vazia
        if not n.get("url"):
            n["url"] = buscar_url(client, n)
        time.sleep(1)

    editorial = gerar_editorial(client, todas, today_str)

    return {
        "resumo_editorial": editorial,
        "noticias":         todas,
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
    print("="*52)
    print("BOLETIM GERAL DE NOTICIAS — Gerador")
    print("="*52)
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
