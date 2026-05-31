#!/usr/bin/env python3
"""
generate_news.py — Boletim Geral de Noticias
API: Google Gemini 2.5 Flash (gratuito com billing ativo)

Arquitetura 3 passos por categoria (zero JSON intermediario com texto livre):
  Passo 1 (google_search): busca → texto estruturado com blocos ##INICIO##
  Passo 2 (response_mime_type=json, SEM search): extrai so campos seguros
           (titulo curto, fonte, url, importancia — nunca corrompem JSON)
  Passo 3 (sem ferramentas, sem JSON): escreve corpo em paragrafos numerados
           parse por sentencas completas, nunca trunca no meio

Custo: gratuito (Gemini free tier — 1500 req/dia com billing)
"""

import json, os, re, sys, time, traceback, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    BRASILIA = ZoneInfo("America/Sao_Paulo")
except Exception:
    BRASILIA = timezone(timedelta(hours=-3))

from google import genai
from google.genai import types

OUTPUT       = "news-data.json"
MODEL        = "gemini-2.5-flash"
NEWS_PER_CAT = 8

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

def get_edition_label(h):
    return "Edicao Matutina (08h)" if h < 12 else "Edicao Vespertina (17h)"

def _strip_md(txt):
    if not txt: return ""
    txt = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', txt)
    txt = re.sub(r'#{1,6}\s+', '', txt)
    txt = re.sub(r'`([^`]+)`', r'\1', txt)
    txt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
    txt = re.sub(r'(?i)fonte\s*:\s*[^|\n]+(\|[^\n]+)?', '', txt)
    return txt.strip()

def gsearch(client, prompt, max_tokens=4000):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1, max_output_tokens=max_tokens))
    return resp.text or ""

def gjson(client, prompt, schema, max_tokens=3000):
    """Chamada sem ferramentas — aceita response_mime_type=json."""
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=schema))
    return json.loads(resp.text)

def _validate_url(url):
    """Retorna url se acessível (2xx/3xx), senão string vazia."""
    if not url or not url.startswith("http"):
        return ""
    try:
        req = urllib.request.Request(url, method="HEAD",
              headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return url if r.status < 400 else ""
    except Exception:
        return ""

def gtext(client, prompt, max_tokens=1000, temp=0.3):
    resp = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temp, max_output_tokens=max_tokens))
    return resp.text or ""

# ── CONSTANTES ────────────────────────────────────────────────────────────────
FONTES_OK = (
    "Agencia Brasil, Folha de S.Paulo, G1, UOL, O Globo, Estadao, Valor Economico, "
    "ICL Noticias, Intercept Brasil, Revista Forum, Brasil de Fato, Carta Capital, "
    "CNN Brasil, Metropoles, Reuters Brasil, El Pais Brasil, Nexo Jornal, Bloomberg Linea, "
    "Agencia Publica, IstoE, Exame, InfoMoney, Opera Mundi, Band News, Correio Braziliense, "
    "R7 Noticias, The Verge, Wired, TechCrunch, Ars Technica, Canaltech, TecMundo, "
    "Variety, Hollywood Reporter, Screen Rant, Rolling Stone Brasil"
)
FONTES_NO = "Jovem Pan, Brasil Paralelo, Terca Livre, Pleno News, O Antagonista"

BLOCO = """##INICIO##
TITULO>> titulo da noticia aqui
FONTE>> nome do veiculo
IMPORTANCIA>> numero de 1 a 10
URL>> url completa do artigo ou deixe vazio
##FIM##"""

# ── PASSO 1: busca com google_search ─────────────────────────────────────────
def _parse_blocos(txt, categoria):
    """Parser robusto: tenta ##INICIO## primeiro, depois linha a linha."""
    noticias = []

    # Estrategia 1: delimitadores ##INICIO## / ##FIM##
    blocos = re.findall(r'##INICIO##(.*?)##FIM##', txt, re.DOTALL)
    for b in blocos:
        def ex(c, bloco=b):
            m = re.search(rf'{c}>>\s*(.+)', bloco)
            return m.group(1).strip() if m else ""
        titulo = ex("TITULO")
        if not titulo or len(titulo) < 8: continue
        if any(x in titulo.lower() for x in ["n/a","nao foi","placeholder","[titulo"]): continue
        url = ex("URL")
        if not url.startswith("http") or "vertexaisearch" in url or "grounding-api" in url:
            url = ""
        else:
            url = _validate_url(url)
        try: imp = min(10, max(1, int(re.search(r'\d+', ex("IMPORTANCIA")).group())))
        except: imp = 5
        noticias.append({
            "titulo": titulo, "fonte": ex("FONTE") or "Redacao",
            "categoria": categoria, "importancia": imp, "url": url,
        })

    if noticias:
        return noticias

    # Estrategia 2: linha a linha com TITULO>> e FONTE>>
    atual = {}
    for linha in txt.split("\n"):
        linha = linha.strip()
        if "TITULO>>" in linha:
            if atual.get("titulo"): noticias.append(atual)
            atual = {"titulo": linha.split(">>",1)[1].strip(), "fonte": "Redacao",
                     "categoria": categoria, "importancia": 5, "url": ""}
        elif "FONTE>>" in linha and atual:
            atual["fonte"] = linha.split(">>",1)[1].strip() or "Redacao"
        elif "IMPORTANCIA>>" in linha and atual:
            m = re.search(r'\d+', linha)
            if m: atual["importancia"] = min(10, max(1, int(m.group())))
        elif "URL>>" in linha and atual:
            u = linha.split(">>",1)[1].strip()
            if u.startswith("http") and "vertexaisearch" not in u:
                atual["url"] = u
    if atual.get("titulo"): noticias.append(atual)

    # Filtra invalidos
    return [n for n in noticias if len(n.get("titulo","")) >= 8
            and not any(x in n["titulo"].lower()
                        for x in ["n/a","nao foi","placeholder"])]


def p1_buscar(client, categoria, instrucoes, n, today_str):
    prompt = (
        f"Hoje e {today_str}. Busque {n} noticias sobre {instrucoes} das ultimas 48h.\n"
        f"FONTES ACEITAS: {FONTES_OK}\nPROIBIDO: {FONTES_NO}\n\n"
        f"Para CADA noticia, escreva EXATAMENTE neste formato:\n{BLOCO}\n\n"
        f"OBRIGATORIO: {n} blocos ##INICIO## ... ##FIM##. "
        "Sem texto fora dos blocos. Sem N/A. "
        "Se nao souber a URL, deixe o campo URL vazio."
    )
    txt = gsearch(client, prompt, 3500)
    noticias = _parse_blocos(txt, categoria)
    print(f"   blocos encontrados: {len(noticias)}")
    return noticias

# ── PASSO 2: estrutura metadados em JSON seguro (sem texto livre) ─────────────
def p2_meta(client, noticias_raw, categoria):
    """
    Recebe lista de noticias (so titulo/fonte/url/importancia) e devolve
    JSON limpo usando response_mime_type.
    Sem corpo, sem resumo — campos que nunca corrompem JSON.
    """
    if not noticias_raw:
        return []

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "titulo":      {"type": "string"},
                "fonte":       {"type": "string"},
                "importancia": {"type": "integer"},
                "url":         {"type": "string"},
            },
            "required": ["titulo", "fonte", "importancia", "url"]
        }
    }

    lista_txt = "\n".join(
        f"{i+1}. Titulo: {n['titulo']} | Fonte: {n['fonte']} | "
        f"Importancia: {n['importancia']} | URL: {n['url']}"
        for i, n in enumerate(noticias_raw)
    )
    prompt = (
        f"Converta esta lista de noticias de {categoria} para JSON.\n"
        f"Para cada item: titulo (maximo 15 palavras), fonte, importancia (1-10), url.\n"
        f"Se url nao for https://, coloque string vazia.\n\n{lista_txt}"
    )

    try:
        result = gjson(client, prompt, schema, 2000)
        # Adiciona categoria e filtra invalidos
        out = []
        for n in result:
            t = n.get("titulo","").strip()
            if not t or len(t) < 8: continue
            url = n.get("url","")
            if not url.startswith("http"):
                url = ""
            else:
                url = _validate_url(url)
            out.append({
                "titulo":      t,
                "fonte":       n.get("fonte","Redacao").strip() or "Redacao",
                "categoria":   categoria,
                "importancia": min(10, max(1, int(n.get("importancia",5)))),
                "url":         url,
            })
        return out
    except Exception as e:
        print(f"   [WARN] p2_meta falhou ({e}) — usando dados brutos")
        return noticias_raw

# ── PASSO 3: corpo em texto puro, parse por sentencas completas ───────────────
def p3_corpo(client, noticia):
    titulo = noticia["titulo"]
    fonte  = noticia["fonte"]
    cat    = noticia["categoria"]

    prompt = (
        f"Escreva um artigo jornalistico completo em portugues brasileiro.\n\n"
        f"Noticia: {titulo}\n"
        f"Fonte: {fonte} | Categoria: {cat}\n\n"
        "O artigo tem 4 paragrafos numerados. IMPORTANTE: nao repita o titulo no texto.\n\n"
        "1) RESUMO: escreva 2 frases proprias descrevendo o fato e sua importancia. "
        "NAO copie o titulo. Minimo 30 palavras.\n\n"
        "2) CONTEXTO: antecedentes e cenario atual. Minimo 4 frases. Minimo 60 palavras.\n\n"
        "3) DETALHES: fatos especificos, dados numericos e declaracoes. Minimo 4 frases. Minimo 60 palavras.\n\n"
        "4) IMPACTO: consequencias e proximos passos esperados. Minimo 4 frases. Minimo 60 palavras.\n\n"
        "Regras: sem markdown, sem asteriscos, sem negrito. Texto puro. "
        "Cada paragrafo termina com ponto final. Total minimo: 300 palavras."
    )

    try:
        txt = _strip_md(gtext(client, prompt, max_tokens=3000, temp=0.35))

        # Remove prefixos como "RESUMO:", "CONTEXTO:", "Titulo:" e numeração "1." "1)" do texto
        txt = re.sub(r'(?m)^\s*(RESUMO|CONTEXTO|DETALHES|IMPACTO|Titulo)\s*:\s*', '', txt)

        # Estrategia 1: divide por "1)" ou "1." no início da linha
        partes = re.split(r'(?m)^\s*[1-4][.)]\s*', txt)
        partes = [p.strip() for p in partes if len(p.strip()) > 40]
        if len(partes) >= 4:
            return _limpa2(partes[0]), "\n\n".join(partes[1:4])
        if len(partes) == 3:
            return _limpa2(partes[0]), "\n\n".join(partes[1:])

        # Estrategia 2: linha em branco
        blocos = [b.strip() for b in re.split(r'\n{2,}', txt) if len(b.strip()) > 40]
        if len(blocos) >= 3:
            return _limpa2(blocos[0]), "\n\n".join(blocos[1:4])
        if len(blocos) == 2:
            return _limpa2(blocos[0]), blocos[1]

        # Estrategia 3: sentencas completas em 4 grupos (nunca corta no meio)
        sentencas = [s.strip() for s in re.split(r'(?<=[.!?])\s+', txt) if len(s.strip()) > 15]
        total = len(sentencas)
        if total >= 8:
            q = total // 4
            g = [
                " ".join(sentencas[:q]),
                " ".join(sentencas[q:2*q]),
                " ".join(sentencas[2*q:3*q]),
                " ".join(sentencas[3*q:]),   # ultimo grupo pega o restante todo
            ]
            return _limpa2(g[0]), "\n\n".join(x for x in g[1:] if x)

        # Fallback: texto inteiro como corpo
        return titulo, txt or titulo

    except Exception as e:
        print(f"      [WARN] corpo: {e}")
        return titulo, titulo

def _limpa2(texto):
    """Resumo: max 2 frases."""
    frases = re.split(r'(?<=[.!?])\s+', texto.strip())
    return " ".join(frases[:2]).strip()

# ── EDITORIAL ─────────────────────────────────────────────────────────────────
def gerar_editorial(client, noticias, today_str):
    titulos = "\n".join(
        f"- {n['titulo']}" for n in noticias
        if n["categoria"] in ["Politica","Economia"]
    )[:600]
    prompt = (
        f"Noticias do dia ({today_str}):\n{titulos}\n\n"
        "Escreva um resumo editorial de 3 frases completas sobre o panorama do dia no Brasil. "
        "Texto puro, sem markdown, sem aspas duplas, em portugues formal."
    )
    try:
        return _strip_md(gtext(client, prompt, 500, 0.2).strip())
    except Exception:
        return "O cenario politico e economico brasileiro segue movimentado."

# ── CONFIGURACAO DAS CATEGORIAS ───────────────────────────────────────────────
CATEGORIAS = [
    ("Politica",
     "politica brasileira: Congresso Nacional, STF, governo federal Lula, "
     "eleicoes 2026, partidos, ministerios, relacoes Executivo-Legislativo"),

    ("Economia",
     "economia brasileira: mercado financeiro, bolsa, inflacao IPCA, "
     "taxa Selic, cambio, emprego, PIB, agronegocio, comercio exterior"),

    ("Cultura",
     "cultura no Brasil: musica shows lancamentos albuns, literatura livros, "
     "teatro, artes visuais, exposicoes, festivais, gastronomia, patrimonio"),

    ("Tecnologia",
     "tecnologia no Brasil e mundo: inteligencia artificial IA, startups, "
     "Apple Google Microsoft Meta Amazon, ciberseguranca, inovacao, ciencia"),

    ("Entretenimento",
     "lancamentos de filmes e series em streaming em 2026: busque separadamente Netflix novidades maio junho 2026, Amazon Prime Video lancamentos 2026, HBO Max Max lancamentos 2026, Apple TV Plus estreias 2026, Disney Plus novidades 2026. Inclua tambem filmes em cartaz no cinema, criticas recentes e noticias de entretenimento"),
]

# ── ORQUESTRADOR ──────────────────────────────────────────────────────────────
def fetch_news():
    api_key = os.environ.get("GEMINI_API_KEY","").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada.")
    print(f"[OK] API key Gemini ({len(api_key)} chars)")

    client    = genai.Client(api_key=api_key)
    now_br    = datetime.now(BRASILIA)
    today_str = format_date_pt(now_br)
    print(f"[OK] {today_str} | {get_edition_label(now_br.hour)}")

    todas     = []
    por_cat   = {}

    for categoria, instrucoes in CATEGORIAS:
        print(f"\n--- {categoria} ---")
        try:
            # P1: busca
            raw = p1_buscar(client, categoria, instrucoes, NEWS_PER_CAT, today_str)
            print(f"   P1 blocos: {len(raw)}")
            time.sleep(3)

            # P2: metadados JSON (sem texto livre, nunca corrompe)
            meta = p2_meta(client, raw, categoria)
            print(f"   P2 meta: {len(meta)} noticias")
            time.sleep(3)

            # P3: corpo para cada noticia
            for i, n in enumerate(meta):
                print(f"   P3 [{i+1}/{len(meta)}] {n['titulo'][:50]}...")
                resumo, corpo = p3_corpo(client, n)
                n["resumo"] = resumo
                n["corpo"]  = corpo
                if i < len(meta) - 1:
                    time.sleep(2)

            todas.extend(meta)
            por_cat[categoria] = len(meta)
            time.sleep(5)  # pausa entre categorias

        except Exception as e:
            print(f"   [ERRO] {categoria}: {e}", file=sys.stderr)
            traceback.print_exc()
            por_cat[categoria] = 0
            time.sleep(5)

    total = len(todas)
    print(f"\n[OK] Total: {total} | {por_cat}")
    if total < 5:
        raise RuntimeError(f"Apenas {total} noticias — insuficiente.")

    editorial = gerar_editorial(client, todas, today_str)

    return {
        "resumo_editorial": editorial,
        "noticias":         todas,
        "por_categoria":    por_cat,
        "generated_at":     now_br.strftime("%Y-%m-%dT%H:%M:%S"),
        "edition_label":    get_edition_label(now_br.hour),
        "date_display":     today_str.upper(),
    }

def main():
    print("="*52)
    print("BOLETIM GERAL DE NOTICIAS — Gerador (Gemini)")
    print("="*52)
    for attempt in range(1, 3):
        try:
            print(f"\n[Tentativa {attempt}/2]")
            data = fetch_news()
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n[OK] Salvo: {len(data['noticias'])} noticias")
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
