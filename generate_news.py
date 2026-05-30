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
def _strip_md(txt):
    """Remove formatacao markdown do texto."""
    txt = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', txt)   # **bold** e *italic*
    txt = re.sub(r'#{1,6}\s+', '', txt)                     # # headings
    txt = re.sub(r'`([^`]+)`', r'\1', txt)                  # `code`
    txt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)      # [link](url)
    txt = re.sub(r'^[-*]\s+', '', txt, flags=re.MULTILINE)  # listas
    # Remove prefixos do modelo: "Fonte: X | Categoria: Y"
    txt = re.sub(r'\*{0,2}Fonte\s*:\s*[^|*\n]+(\|[^*\n]+)?\*{0,2}', '', txt, flags=re.IGNORECASE)
    txt = re.sub(r'\*{0,2}Categoria\s*:\s*[^\n*]+\*{0,2}', '', txt, flags=re.IGNORECASE)
    return txt.strip()


def _limpa_resumo(texto):
    """No maximo 2 frases, sem markdown."""
    texto = _strip_md(texto)
    frases = re.split(r'(?<=[.!?])\s+', texto.strip())
    return " ".join(frases[:2]).strip()


def gerar_corpo(client, noticia):
    """
    Gera resumo (2 frases) + corpo (3 paragrafos completos).
    Prompt minimalista sem marcadores — texto corrido que depois dividimos.
    """
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    cat    = noticia["categoria"]

    prompt = (
        f"Escreva um artigo jornalistico em portugues brasileiro sobre:\n"
        f"'{titulo}' — publicado por {fonte} na categoria {cat}.\n\n"
        "O artigo deve ter exatamente 4 paragrafos numerados:\n\n"
        "1) Dois frases de resumo (quem, o que, por que e importante).\n"
        "2) Paragrafo de contexto e antecedentes (minimo 4 frases).\n"
        "3) Paragrafo com fatos, dados e declaracoes (minimo 4 frases).\n"
        "4) Paragrafo com impacto e proximos passos (minimo 4 frases).\n\n"
        "Separe cada paragrafo numerado com uma linha em branco. "
        "NAO use asteriscos, negrito, italico ou qualquer formatacao markdown. "
        "Escreva em texto puro. Total minimo: 350 palavras."
    )

    try:
        txt = gtext(client, prompt, max_tokens=2048, temp=0.35)

        # Remove markdown residual
        txt = _strip_md(txt)

        # Estrategia 1: divide por "1)" "2)" "3)" "4)" no inicio de linha
        partes = re.split(r'(?m)^\s*[1-4]\)\s*', txt)
        partes = [p.strip() for p in partes if len(p.strip()) > 40]
        if len(partes) >= 4:
            return _limpa_resumo(partes[0]), "\n\n".join(partes[1:4])
        if len(partes) == 3:
            return _limpa_resumo(partes[0]), "\n\n".join(partes[1:])

        # Estrategia 2: divide por linha em branco
        blocos = [b.strip() for b in re.split(r'\n{2,}', txt) if len(b.strip()) > 40]
        if len(blocos) >= 4:
            return _limpa_resumo(blocos[0]), "\n\n".join(blocos[1:4])
        if len(blocos) == 3:
            return _limpa_resumo(blocos[0]), "\n\n".join(blocos[1:])
        if len(blocos) == 2:
            return _limpa_resumo(blocos[0]), blocos[1]

        # Estrategia 3: divide por "PARAGRAFO N"
        partes3 = re.split(r'(?i)par[aá]grafo\s*\d+\s*[-–:]?\s*', txt)
        partes3 = [p.strip() for p in partes3 if len(p.strip()) > 40]
        if len(partes3) >= 3:
            return _limpa_resumo(partes3[0]), "\n\n".join(partes3[1:4])

        # Estrategia 4: divide por sentencas em 4 grupos IGUAIS (sem cortar no meio)
        sentencas = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if len(s.strip()) > 15]
        total = len(sentencas)
        if total >= 8:
            q = total // 4
            g0 = " ".join(sentencas[:q])
            g1 = " ".join(sentencas[q:2*q])
            g2 = " ".join(sentencas[2*q:3*q])
            g3 = " ".join(sentencas[3*q:])   # pega o restante todo
            return _limpa_resumo(g0), "\n\n".join(g for g in [g1, g2, g3] if g)

        # Estrategia 5: texto inteiro como corpo
        if txt and len(txt) > 50:
            return titulo, txt

        return titulo, titulo

    except Exception as e:
        print(f"      [WARN] corpo: {e}")
        return titulo, titulo

def _limpa_resumo(texto):
    """Garante que o resumo seja no maximo 2 frases."""
    frases = re.split(r'(?<=[.!?])\s+', texto.strip())
    return " ".join(frases[:2]).strip()

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
    pol_eco = [n["titulo"] for n in noticias if n["categoria"] in ["Politica","Economia"]][:6]
    titulos = "\n".join(f"- {t}" for t in pol_eco)
    prompt = (
        f"Hoje e {today_str}. Com base nestas noticias brasileiras:\n{titulos}\n\n"
        "Escreva um RESUMO EDITORIAL completo com exatamente 3 frases sobre o panorama "
        "politico-economico do dia no Brasil. "
        "Escreva as 3 frases diretamente, sem titulo, sem aspas duplas, em portugues brasileiro."
    )
    try:
        txt = gtext(client, prompt, max_tokens=300, temp=0.2).strip()
        # Remove possiveis prefixos do modelo
        txt = re.sub(r'^(resumo editorial[:\s]*|editorial[:\s]*)', '', txt, flags=re.IGNORECASE).strip()
        return txt
    except Exception:
        return "O cenario politico e economico brasileiro segue movimentado. Diversas pautas relevantes dominam a agenda nacional nesta edicao." 

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
