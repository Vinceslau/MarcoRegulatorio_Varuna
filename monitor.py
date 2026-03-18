"""
monitor.py — Raspador Playwright para o Monitor Regulatório
Acessa os portais oficiais e detecta movimentações nos casos monitorados.
"""

import asyncio
import json
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
#  CONFIGURAÇÃO — edite antes de usar
# ─────────────────────────────────────────────
CONFIG = {
    "email": {
        "smtp_server":  "smtp.gmail.com",
        "smtp_port":    587,
        "sender":       "seu_email@gmail.com",
        "password":     "sua_senha_de_app",
        "recipient":    "seu_email@gmail.com",
    },
    "state_file":  "monitor_state.json",
    "headless":    True,
    "timeout_ms":  35_000,
    "concurrency": 4,
}

# ─────────────────────────────────────────────
#  CASOS MONITORADOS
# ─────────────────────────────────────────────
CASES = [
    {
        "id": "ADI7703",
        "name": "ADI 7703",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7004505",
        "incidente": "7004505",
        "scraper": "stf",
    },
    {
        "id": "RE1515163",
        "name": "RE 1515163",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7035265",
        "incidente": "7035265",
        "scraper": "stf",
    },
    {
        "id": "RE1516074",
        "name": "RE 1516074 (Tema 1349)",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7037768",
        "incidente": "7037768",
        "scraper": "stf",
    },
    {
        "id": "RE922144",
        "name": "RE 922144 (Tema 865)",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=4864567",
        "incidente": "4864567",
        "scraper": "stf",
    },
    {
        "id": "RE970343",
        "name": "RE 970343",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=4981758",
        "incidente": "4981758",
        "scraper": "stf",
    },
    {
        "id": "ADI7435",
        "name": "ADI 7435",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6721181",
        "incidente": "6721181",
        "scraper": "stf",
    },
    {
        "id": "RE1558191",
        "name": "RE 1558191/SP",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7298583",
        "incidente": "7298583",
        "scraper": "stf",
    },
    {
        "id": "ADI7873",
        "name": "ADI 7873",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7366591",
        "incidente": "7366591",
        "scraper": "stf",
    },
    {
        "id": "RESP2217133",
        "name": "REsp nº 2217133/RS",
        "tribunal": "STJ",
        "url": "https://processo.stj.jus.br/processo/pesquisa/?termo=RESP2217133&aplicacao=processos.ea&tipoPesquisa=tipoPesquisaGenerica&chkordem=DESC&chkMorto=MORTO",
        "scraper": "stj",
    },
    {
        "id": "PL504",
        "name": "PL 504/2024",
        "tribunal": "Câmara",
        "url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2418993",
        "scraper": "camara",
    },
    {
        "id": "PL2581",
        "name": "PL 2581/24",
        "tribunal": "Câmara",
        "url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2443476",
        "scraper": "camara",
    },
    {
        "id": "PL2354",
        "name": "PL 2354/2024",
        "tribunal": "Câmara",
        "url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2440521",
        "scraper": "camara",
    },
    {
        "id": "PL4072",
        "name": "PL 4072/2025",
        "tribunal": "Câmara",
        "url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2549050",
        "scraper": "camara",
    },
    {
        "id": "TCESP",
        "name": "TCE/SP (00016837.989.24-3)",
        "tribunal": "TCE",
        # TODO: deixar em stand by
        "url": "https://www.tce.sp.gov.br/processos",
        "numero": "00016837.989.24-3",
        "scraper": "tcesp",
    },
    {
        "id": "PROC1078035",
        "name": "1078035-43.2024.4.01.3300",
        "tribunal": "Judicial",
        "url": "https://pje1g-consultapublica.trf1.jus.br/consultapublica/ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam?ca=bd957c50e88916eaa47784587efb8ff1f12508038c5c97a5",
        "numero": "1078035-43.2024.4.01.3300",
        "scraper": "trf1_direto",
    },

    {
        "id": "RE678360",
        "name": "RE 678360",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=4219076",
        "incidente": "4219076",
        "scraper": "stf",
    },
    {
        "id": "REC7879",
        "name": "Rcl 78529",
        "tribunal": "STF",
        "url": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=7226551",
        "incidente": "7226551",
        "scraper": "stf",
    },
    {
        "id": "PEC66",
        "name": "PEC 66/2023",
        "tribunal": "Câmara",
        "url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2454495",
        "scraper": "camara",
    },
]


# ─────────────────────────────────────────────
#  HELPER: corrige encoding latin-1 → utf-8
# ─────────────────────────────────────────────

def _fix_encoding(text: str) -> str:
    """Corrige texto com encoding latin-1 interpretado como utf-8 (ex: 'Ã ' → 'à')."""
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except Exception:
        return text


# ─────────────────────────────────────────────
#  SCRAPERS
# ─────────────────────────────────────────────

async def scrape_stf(page, case: dict) -> dict:
    """
    Raspa a última movimentação do STF em 3 camadas:
      1. Visita página principal (sessão) → abaAndamentos.asp (leve)
      2. Página principal com networkidle + clique na aba Andamentos
      3. Fallback: texto livre do body
    """
    incidente = case.get("incidente", "")

    # Camada 1
    if incidente:
        try:
            await page.goto(case["url"],
                            wait_until="domcontentloaded",
                            timeout=CONFIG["timeout_ms"])
            await page.wait_for_timeout(2000)

            aba_url = (f"https://portal.stf.jus.br/processos/abaAndamentos.asp"
                       f"?incidente={incidente}&imprimir=")
            await page.goto(aba_url,
                            wait_until="domcontentloaded",
                            timeout=CONFIG["timeout_ms"])
            await page.wait_for_timeout(1500)

            events = []

            items = await page.locator(
                ".andamento-item, li.andamento, .andamento, "
                "tr.andamento, .processo-andamento"
            ).all()
            for item in items[:20]:
                nome = ""
                data = ""
                try:
                    nome_el = item.locator("h5, .andamento-nome, strong, b")
                    if await nome_el.count() > 0:
                        nome = _fix_encoding((await nome_el.first.inner_text()).strip())
                    data_el = item.locator(".andamento-data, .data, span, small, td")
                    if await data_el.count() > 0:
                        data_raw = (await data_el.first.inner_text()).strip()
                        m = re.search(r"\d{2}/\d{2}/\d{4}", data_raw)
                        if m:
                            data = m.group(0)
                except Exception:
                    pass
                if data and nome:
                    events.append({"data": data, "descricao": nome})

            if not events:
                rows = await page.locator("table tr").all()
                for row in rows[:30]:
                    cells = await row.locator("td").all_text_contents()
                    if len(cells) >= 2:
                        d = cells[0].strip()
                        desc = _fix_encoding(cells[1].strip())
                        if re.match(r"\d{2}/\d{2}/\d{4}", d) and desc:
                            events.append({"data": d, "descricao": desc})

            if not events:
                content = await page.locator("body").inner_text()
                for line in content.split("\n"):
                    line = line.strip()
                    m = re.match(r"(\d{2}/\d{2}/\d{4})\s+(.*)", line)
                    if m and m.group(2):
                        events.append({"data": m.group(1),
                                       "descricao": _fix_encoding(m.group(2).strip())})

            if events:
                ultima = events[0]
                return _ok(case, ultima["data"], ultima["descricao"], events[:5])
        except Exception:
            pass

    # Camada 2
    try:
        await page.goto(case["url"],
                        wait_until="networkidle",
                        timeout=CONFIG["timeout_ms"])
    except PlaywrightTimeout:
        try:
            await page.goto(case["url"],
                            wait_until="domcontentloaded",
                            timeout=CONFIG["timeout_ms"])
            await page.wait_for_timeout(3000)
        except Exception:
            pass

    try:
        tab = page.locator(
            "a:has-text('Andamentos'), button:has-text('Andamentos'), "
            "[data-tab='andamentos'], #tab-andamentos"
        )
        if await tab.count() > 0:
            await tab.first.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

    events = []
    rows = await page.locator("table tr").all()
    for row in rows[:30]:
        cells = await row.locator("td").all_text_contents()
        if len(cells) >= 2:
            data = cells[0].strip()
            desc = _fix_encoding(cells[1].strip()) if len(cells) > 1 else ""
            if re.match(r"\d{2}/\d{2}/\d{4}", data) and desc:
                events.append({"data": data, "descricao": desc})

    # Camada 3
    if not events:
        content = await page.locator("body").inner_text()
        for line in content.split("\n"):
            line = line.strip()
            m = re.match(r"(\d{2}/\d{2}/\d{4})\s*(.*)", line)
            if m:
                events.append({"data": m.group(1),
                               "descricao": _fix_encoding(m.group(2).strip())})

    ultima = events[0] if events else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], events[:5])


async def scrape_stj(page, case: dict) -> dict:
    """
    Raspa fases do STJ.

    Estrutura da página:
      - URL já abre direto no processo
      - Clicar na aba "Fases" para carregar as movimentações
      - Cada fase: div.classDivFaseLinha
        - Data:      span.classSpanFaseData  (DD/MM/YYYY)
        - Descrição: span.classSpanFaseTexto (ignora span.clsFaseCodigoConselhoNacionalJustica)
    """
    await page.goto(case["url"],
                    wait_until="domcontentloaded",
                    timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(2000)

    # Clica na aba Fases
    try:
        aba = page.locator("a:has-text('Fases'), span:has-text('Fases')")
        if await aba.count() > 0:
            await aba.first.click()
            await page.wait_for_timeout(3000)
    except Exception:
        pass

    events = []
    try:
        linhas = await page.locator("div.classDivFaseLinha").all()
        for linha in linhas[:30]:
            try:
                data_el = linha.locator("span.classSpanFaseData")
                desc_el = linha.locator("span.classSpanFaseTexto")
                if await data_el.count() == 0 or await desc_el.count() == 0:
                    continue
                data = (await data_el.first.inner_text()).strip()
                await desc_el.first.locator("span.clsFaseCodigoConselhoNacionalJustica").evaluate(
                    "el => el.remove()"
                )
                desc = re.sub(r'\s+', ' ', (await desc_el.first.inner_text())).strip()
                if re.match(r"\d{2}/\d{2}/\d{4}", data) and desc:
                    events.append({"data": data, "descricao": desc[:300]})
            except Exception:
                continue
    except Exception as e:
        return _err(case, f"Erro ao raspar STJ: {e}")

    ultima = events[0] if events else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], events[:5])


async def scrape_camara(page, case: dict) -> dict:
    """
    Raspa tramitação de PL na Câmara dos Deputados.

    Seletores estáveis (por summary, não por id):
      - table[summary="Último despacho da proposição"]   → despacho atual
      - table[summary="Lista das tramitações da proposição"] → tramitação completa
    Linhas de dados ficam em tr.odd e tr.even dentro dessas tabelas.
    """
    await page.goto(case["url"],
                    wait_until="domcontentloaded",
                    timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(2000)

    # Aguarda a tabela de tramitação aparecer no DOM
    if await page.locator('table[summary="Lista das tramitações da proposição"]').count() == 0:
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

    def _clean(text: str) -> str:
        text = re.sub(r'[\t\n\r]+', ' ', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    # ── 1. Despacho atual (última linha válida = mais recente) ─
    despacho_data = ""
    despacho_desc = ""
    try:
        despacho_table = page.locator('table[summary="Último despacho da proposição"]')
        if await despacho_table.count() > 0:
            # tr.odd e tr.even são as linhas de dados
            rows = await despacho_table.locator("tr.odd, tr.even").all()
            for row in rows:
                cells = await row.locator("td").all_text_contents()
                if len(cells) >= 2:
                    d = cells[0].strip()
                    desc = _clean(cells[1])
                    if re.match(r"\d{2}/\d{2}/\d{4}", d) and desc:
                        despacho_data = d
                        despacho_desc = desc[:350]
                        break  # tabela em ordem decrescente — primeira linha = mais recente
    except Exception:
        pass

    # ── 2. Tramitação completa ────────────────────────────────
    events = []
    seen = set()
    try:
        tram_table = page.locator('table[summary="Lista das tramitações da proposição"]')
        if await tram_table.count() > 0:
            rows = await tram_table.locator("tr.odd, tr.even").all()
            for row in rows[:80]:
                cells = await row.locator("td").all_text_contents()
                if len(cells) >= 2:
                    data = cells[0].strip()
                    desc = _clean(cells[1])
                    if re.match(r"\d{2}/\d{2}/\d{4}", data) and desc:
                        key = (data, desc[:80])
                        if key not in seen:
                            seen.add(key)
                            events.append({"data": data, "descricao": desc[:350]})
    except Exception as e:
        return _err(case, f"Erro ao raspar Câmara: {e}")

    def parse_date(d):
        try:
            return datetime.strptime(d["data"], "%d/%m/%Y")
        except Exception:
            return datetime.min

    events.sort(key=parse_date, reverse=True)

    # ── 3. Decide ultima_data e ultima_descricao ──────────────
    if despacho_desc:
        ultima_data = despacho_data or (events[0]["data"] if events else "—")
        ultima_desc = f"[Despacho atual] {despacho_desc}"
    elif events:
        ultima_data = events[0]["data"]
        ultima_desc = events[0]["descricao"]
    else:
        ultima_data = "—"
        ultima_desc = "Sem tramitação detectada"

    return _ok(case, ultima_data, ultima_desc, events[:5])

async def scrape_tcesp(page, case: dict) -> dict:
    """Raspa processo no TCE-SP."""
    await page.goto(case["url"],
                    wait_until="domcontentloaded",
                    timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(2000)

    try:
        campo = page.locator(
            "input[name*='numero'], input[placeholder*='número'], input[id*='numero']"
        ).first
        if await campo.count() > 0:
            await campo.fill(case.get("numero", ""))
            await campo.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2500)
    except Exception:
        pass

    events = []
    try:
        rows = await page.locator("table tr").all()
        for row in rows[:20]:
            cells = await row.locator("td").all_text_contents()
            if len(cells) >= 2:
                data = cells[0].strip()
                desc = cells[1].strip()
                if re.match(r"\d{2}/\d{2}/\d{4}", data):
                    events.append({"data": data, "descricao": desc[:300]})
    except Exception as e:
        return _err(case, f"Erro ao raspar TCE-SP: {e}")

    ultima = events[0] if events else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], events[:5])


async def scrape_trf1(page, case: dict) -> dict:
    """
    TRF1 — Consulta Pública PJe
    1. Abre a página de busca
    2. Digita o número do processo no campo específico
    3. Captura a nova aba que abre com o detalhe
    4. Lê a tabela de movimentações (paginada — itera todas as páginas)
    """
    SEARCH_URL = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam"
    FIELD_ID   = "fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso"
    numero     = case.get("numero", "")

    # ── 1. Abre página de busca ───────────────────────────────
    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(2000)

    # ── 2. Preenche o número e submete ────────────────────────
    campo = page.locator(f"#{FIELD_ID.replace(':', r'\:')}")
    await campo.fill(numero)
    await campo.press("Enter")
    await page.wait_for_timeout(2000)

    # Clica no primeiro resultado encontrado e captura a nova aba
    try:
        async with page.context.expect_page() as new_page_info:
            await page.locator("a.rich-table-cell, tbody tr a, #fPP\\:tableResultados a").first.click()
        detail_page = await new_page_info.value
        await detail_page.wait_for_load_state("domcontentloaded")
        await detail_page.wait_for_timeout(2500)
    except Exception as e:
        return _err(case, f"TRF1: não conseguiu abrir detalhe do processo — {e}")

    # ── 3. Lê todas as páginas de movimentações ───────────────
    events = []

    async def _read_current_page(p):
        spans = await p.locator("#j_id150\\:processoEvento span[id*='j_id518']").all()
        for span in spans:
            text = (await span.inner_text()).strip()
            # Formato: "DD/MM/YYYY HH:MM:SS - Descrição"
            m = re.match(r"(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}:\d{2}\s+-\s+(.*)", text)
            if m:
                events.append({
                    "data":      m.group(1),
                    "descricao": _fix_encoding(m.group(2).strip()[:300]),
                })

    await _read_current_page(detail_page)

    # Verifica se há mais páginas e itera
    try:
        total_text = await detail_page.locator("span.total-results, .rich-datascroller-button-next").first.inner_text()
    except Exception:
        total_text = ""

    page_num = 2
    while True:
        next_btn = detail_page.locator(
            "input[id*='next'], a[id*='next'], "
            ".rich-datascroller-button-next:not([disabled])"
        )
        if await next_btn.count() == 0:
            break
        try:
            await next_btn.first.click()
            await detail_page.wait_for_timeout(1500)
            await _read_current_page(detail_page)
            page_num += 1
            if page_num > 10:  # segurança: máximo 10 páginas
                break
        except Exception:
            break

    await detail_page.close()

    # ── 4. Deduplica e ordena ─────────────────────────────────
    seen, unique = set(), []
    for e in events:
        k = (e["data"], e["descricao"][:60])
        if k not in seen:
            seen.add(k)
            unique.append(e)

    def parse_date(d):
        try:
            return datetime.strptime(d["data"], "%d/%m/%Y")
        except Exception:
            return datetime.min

    unique.sort(key=parse_date, reverse=True)

    ultima = unique[0] if unique else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], unique[:5])

async def scrape_trf1_direto(page, case: dict) -> dict:
    """
    TRF1 — Acesso direto à página do processo via link público (ca=...).
    Lê a tabela de movimentações iterando todas as páginas.
    """
    await page.goto(case["url"], wait_until="domcontentloaded", timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(3000)

    events = []

    async def _read_page():
        spans = await page.locator("span[id*='j_id518']").all()
        for span in spans:
            text = (await span.inner_text()).strip()
            m = re.match(r"(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}:\d{2}\s+-\s+(.*)", text)
            if m:
                events.append({
                    "data":      m.group(1),
                    "descricao": _fix_encoding(m.group(2).strip()[:300]),
                })

    await _read_page()

    # Itera páginas seguintes
    for _ in range(9):  # máximo 10 páginas no total
        next_btn = page.locator("a[id*='next']:not([class*='disabled']), input[id*='next']")
        if await next_btn.count() == 0:
            break
        try:
            await next_btn.first.click()
            await page.wait_for_timeout(1500)
            await _read_page()
        except Exception:
            break

    # Deduplica e ordena
    seen, unique = set(), []
    for e in events:
        k = (e["data"], e["descricao"][:60])
        if k not in seen:
            seen.add(k)
            unique.append(e)

    def parse_date(d):
        try:
            return datetime.strptime(d["data"], "%d/%m/%Y")
        except Exception:
            return datetime.min

    unique.sort(key=parse_date, reverse=True)

    ultima = unique[0] if unique else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], unique[:5])

async def scrape_tjam(page, case: dict) -> dict:
    """Raspa processo no TJAM."""
    await page.goto(case["url"],
                    wait_until="domcontentloaded",
                    timeout=CONFIG["timeout_ms"])
    await page.wait_for_timeout(2000)

    events = []
    try:
        rows = await page.locator(
            "table.tabelaTopoDetalhe tr, table tr, .movimentacaoProcesso tr"
        ).all()
        for row in rows[:25]:
            cells = await row.locator("td").all_text_contents()
            if len(cells) >= 2:
                data = cells[0].strip()
                desc = cells[1].strip()
                if re.match(r"\d{2}/\d{2}/\d{4}", data):
                    events.append({"data": data, "descricao": desc[:300]})
    except Exception as e:
        return _err(case, f"Erro ao raspar TJAM: {e}")

    ultima = events[0] if events else {"data": "—", "descricao": "Sem movimentação detectada"}
    return _ok(case, ultima["data"], ultima["descricao"], events[:5])


async def scrape_manual(page, case: dict) -> dict:
    """Caso sem scraper automático — usa data_fixa para evitar falsos positivos."""
    return {
        "id": case["id"],
        "name": case["name"],
        "tribunal": case["tribunal"],
        "ultima_data": case.get("data_fixa", "—"),
        "ultima_descricao": f"⚠ Consulta manual necessária. {case.get('nota', '')}",
        "eventos_recentes": [],
        "url": case.get("url", ""),
        "erro": "manual",
    }


# ── Helpers ───────────────────────────────────────────────────────

def _ok(case: dict, data: str, desc: str, eventos: list) -> dict:
    return {
        "id": case["id"],
        "name": case["name"],
        "tribunal": case["tribunal"],
        "ultima_data": data,
        "ultima_descricao": desc,
        "eventos_recentes": eventos,
        "url": case.get("url", ""),
        "erro": None,
    }


def _err(case: dict, msg: str) -> dict:
    return {
        "id": case["id"],
        "name": case["name"],
        "tribunal": case["tribunal"],
        "ultima_data": "—",
        "ultima_descricao": msg,
        "eventos_recentes": [],
        "url": case.get("url", ""),
        "erro": msg,
    }


SCRAPERS = {
   "stf":        scrape_stf,
    "stj":        scrape_stj,
    "camara":     scrape_camara,
    "tcesp":      scrape_tcesp,
    "trf1":       scrape_trf1,
    "trf1_direto": scrape_trf1_direto,
    "tjam":       scrape_tjam,
    "manual":     scrape_manual,
}


# ─────────────────────────────────────────────
#  ESTADO
# ─────────────────────────────────────────────

def load_state() -> dict:
    p = Path(CONFIG["state_file"])
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    Path(CONFIG["state_file"]).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def detect_changes(old_state: dict, new_results: list) -> list:
    changes = []
    for result in new_results:
        cid = result["id"]
        if result.get("erro") == "manual":
            continue
        old = old_state.get(cid, {})
        old_data = old.get("ultima_data", "")
        old_desc = old.get("ultima_descricao", "")
        new_data = result["ultima_data"]
        new_desc = result["ultima_descricao"]
        if (new_data != old_data or new_desc != old_desc) and new_data != "—":
            changes.append({
                "id": cid,
                "name": result["name"],
                "tribunal": result["tribunal"],
                "data_anterior": old_data or "—",
                "desc_anterior": old_desc or "Sem registro anterior",
                "data_nova": new_data,
                "desc_nova": new_desc,
                "url": result.get("url", ""),
            })
    return changes


# ─────────────────────────────────────────────
#  E-MAIL
# ─────────────────────────────────────────────

def send_email(changes: list, all_results: list):
    cfg = CONFIG["email"]
    password = os.environ.get("EMAIL_PASSWORD") or cfg.get("password", "")
    if not cfg["sender"] or cfg["sender"] == "seu_email@gmail.com":
        print("⚠  E-mail não configurado. Edite CONFIG['email'] no topo do monitor.py")
        return
    if not password or password == "sua_senha_de_app":
        print("⚠  Senha de e-mail não configurada.")
        return

    now = datetime.now().strftime("%d/%m/%Y às %H:%M")
    rows_html = ""
    for c in changes:
        rows_html += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #1e2535;font-family:monospace;color:#60a5fa;font-size:13px">{c['name']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #1e2535;color:#94a3b8;font-size:13px">{c['tribunal']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #1e2535;color:#22c55e;font-size:13px">{c['data_nova']}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #1e2535;color:#e2e8f0;font-size:13px">{c['desc_nova'][:200]}</td>
        </tr>"""

    html_body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<body style="margin:0;padding:0;background:#0a0c10;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:700px;margin:32px auto;background:#10141c;border:1px solid #1e2535;border-radius:12px;overflow:hidden">
    <div style="background:#161b26;padding:24px 32px;border-bottom:1px solid #1e2535">
      <span style="font-size:24px">⚖️</span>
      <span style="font-size:18px;font-weight:700;color:#e2e8f0;margin-left:12px">Monitor Regulatório</span>
    </div>
    <div style="margin:24px 32px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.25);border-radius:8px;padding:16px 20px">
      <div style="color:#f59e0b;font-size:14px;font-weight:600">🔔 {len(changes)} nova(s) movimentação(ões) detectada(s)</div>
      <div style="color:#94a3b8;font-size:12px;margin-top:4px">Verificação realizada em {now}</div>
    </div>
    <div style="padding:0 32px 24px">
      <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#161b26">
          <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Caso</th>
          <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Tribunal</th>
          <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Data</th>
          <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Movimentação</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚖️ [{len(changes)} movimentação(ões)] Monitor Regulatório — {now}"
    msg["From"]    = cfg["sender"]
    msg["To"]      = cfg["recipient"]
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(cfg["sender"], password)
            server.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
        print(f"✉  E-mail enviado para {cfg['recipient']}")
    except Exception as e:
        print(f"✗  Erro ao enviar e-mail: {e}")


# ─────────────────────────────────────────────
#  RUNNER PRINCIPAL
# ─────────────────────────────────────────────

async def run_all() -> dict:
    old_state = load_state()
    errors = []
    semaphore = asyncio.Semaphore(CONFIG["concurrency"])

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=CONFIG["headless"],
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )

        async def run_case(case):
            async with semaphore:
                scraper_fn = SCRAPERS.get(case["scraper"], scrape_manual)
                print(f"  → {case['name']} ({case['tribunal']})...",
                      end=" ", flush=True)
                page = await context.new_page()
                try:
                    result = await scraper_fn(page, case)
                    print(f"✓  [{result['ultima_data']}] "
                          f"{result['ultima_descricao'][:60]}")
                    return result
                except Exception as e:
                    print(f"✗  Erro: {e}")
                    errors.append({"id": case["id"], "name": case["name"], "erro": str(e)})
                    return {
                        "id": case["id"],
                        "name": case["name"],
                        "tribunal": case["tribunal"],
                        "ultima_data": "—",
                        "ultima_descricao": f"Erro: {e}",
                        "eventos_recentes": [],
                        "url": case.get("url", ""),
                        "erro": str(e),
                    }
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

        results = list(await asyncio.gather(*[run_case(c) for c in CASES]))
        await browser.close()

    changes = detect_changes(old_state, results)

    new_state = {
        r["id"]: {
            "ultima_data": r["ultima_data"],
            "ultima_descricao": r["ultima_descricao"],
            "eventos_recentes": r.get("eventos_recentes", []),
            "verificado_em": datetime.now().isoformat(),
        }
        for r in results
    }
    save_state(new_state)

    if changes:
        print(f"\n🔔 {len(changes)} mudança(s) detectada(s)! Enviando e-mail...")
        send_email(changes, results)
    else:
        print("\n✅ Nenhuma mudança detectada.")

    return {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "erros": len(errors),
        "mudancas": len(changes),
        "changes": changes,
        "results": results,
    }


def main():
    print(f"\n{'═'*60}")
    print(f"  Monitor Regulatório — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'═'*60}\n")
    summary = asyncio.run(run_all())
    print(f"\n{'─'*60}")
    print(f"  Concluído: {summary['total']} casos | "
          f"{summary['erros']} erros | "
          f"{summary['mudancas']} mudanças")
    print(f"{'─'*60}\n")
    return summary


if __name__ == "__main__":
    main()