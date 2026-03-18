"""
server.py - Servidor local do Monitor Regulatorio
Expoe a API que o dashboard consome e agenda as verificacoes automaticas.

Live Reload: qualquer alteracao em monitor_regulatorio.html recarrega
             o navegador automaticamente via Server-Sent Events (SSE).

Uso:
    python server.py

Acesse o dashboard em: http://localhost:5000
"""

import json
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

from flask import Flask, jsonify, send_file, request, Response, stream_with_context
from flask_cors import CORS

import monitor as mon_module

app = Flask(__name__)
CORS(app)

NOTIFICATIONS_FILE   = "notifications.json"
DASHBOARD_FILE       = "monitor_regulatorio.html"
SCHEDULED_HOUR = 11  # Verificação automática todo dia às 11h
NEWS_FILE            = "news_cache.json"

# ── Configuração de notícias ──────────────────────────────────────
NEWS_QUERY       = "precatórios"   # Termo de busca
NEWS_TIMELINE    = 30              # Notícias buscadas e salvas no cache


def fetch_news() -> list:
    import urllib.parse
    query = urllib.parse.quote(NEWS_QUERY)
    api_key = os.environ.get("NEWSAPI_KEY", "")
    url = f"https://newsapi.org/v2/everything?q={query}&language=pt&sortBy=publishedAt&pageSize={NEWS_TIMELINE}&apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = []
        for article in data.get("articles", []):
            results.append({
                "title":         article.get("title", "").strip(),
                "link":          article.get("url", "").strip(),
                "source":        article.get("source", {}).get("name", "NewsAPI"),
                "published":     article.get("publishedAt", ""),
                "published_iso": article.get("publishedAt", ""),
            })
        return results
    except Exception as e:
        print(f"[news] Erro ao buscar notícias: {e}")
        return []


def save_news(items: list):
    Path(NEWS_FILE).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_news() -> list:
    p = Path(NEWS_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []

# ─────────────────────────────────────────────
#  LIVE RELOAD via Server-Sent Events
# ─────────────────────────────────────────────
_reload_clients: list = []
_reload_lock = threading.Lock()


def _broadcast_reload():
    with _reload_lock:
        for q in list(_reload_clients):
            try:
                q.put_nowait("reload")
            except Exception:
                pass
    print("[live-reload] Mudanca detectada — navegador sera recarregado.")


def _watch_html():
    """Thread que monitora o HTML e dispara reload ao salvar."""
    path = Path(DASHBOARD_FILE)
    last_mtime = path.stat().st_mtime if path.exists() else 0
    while True:
        time.sleep(0.5)
        try:
            mtime = path.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                _broadcast_reload()
        except FileNotFoundError:
            pass


@app.route("/api/livereload")
def livereload_stream():
    """SSE endpoint — o dashboard escuta aqui e recarrega ao receber sinal."""
    client_q = queue.Queue(maxsize=5)
    with _reload_lock:
        _reload_clients.append(client_q)

    def event_stream():
        try:
            while True:
                try:
                    msg = client_q.get(timeout=20)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield "data: ping\n\n"
        finally:
            with _reload_lock:
                if client_q in _reload_clients:
                    _reload_clients.remove(client_q)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─────────────────────────────────────────────
#  PERSISTENCIA DE NOTIFICACOES
# ─────────────────────────────────────────────

def load_notifications() -> list:
    p = Path(NOTIFICATIONS_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def save_notification(entry: dict):
    notifs = load_notifications()
    notifs.insert(0, entry)
    notifs = notifs[:200]
    Path(NOTIFICATIONS_FILE).write_text(
        json.dumps(notifs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─────────────────────────────────────────────
#  AGENDADOR DIARIO
# ─────────────────────────────────────────────

scheduler_state = {
    "last_run": None,
    "next_run": None,
    "running":  False,
}


def _next_scheduled_run() -> datetime:
    """Retorna o próximo datetime em que a verificação automática deve rodar (às 11h)."""
    now = datetime.now()
    candidate = now.replace(hour=SCHEDULED_HOUR, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate


def scheduled_check():
    """Thread do agendador — inicializa o próximo run com base no estado salvo."""
    time.sleep(10)
    state = mon_module.load_state()
    if state:
        last_times = [v.get("verificado_em") for v in state.values() if v.get("verificado_em")]
        if last_times:
            last_dt = datetime.fromisoformat(sorted(last_times)[-1])
            scheduler_state["last_run"] = last_dt.isoformat()

    # Sempre agenda para o próximo 11h, independente do histórico
    scheduler_state["next_run"] = _next_scheduled_run().isoformat()

    while True:
        now = datetime.now()
        next_run = scheduler_state.get("next_run")
        should_run = (next_run is None) or (datetime.fromisoformat(next_run) <= now)
        if should_run and not scheduler_state["running"]:
            print(f"\n[scheduler] Verificacao automatica: {now.strftime('%d/%m/%Y %H:%M')}")
            _do_check(triggered_by="automatico")
        time.sleep(60)


def _do_check(triggered_by: str = "manual") -> dict:
    if scheduler_state["running"]:
        return {"erro": "Verificacao ja em andamento"}
    scheduler_state["running"] = True
    try:
        import asyncio
        summary = asyncio.run(mon_module.run_all())
        # Busca e salva notícias junto com cada verificação
        news = fetch_news()
        if news:
            save_news(news)
            print(f"[news] {len(news)} notícias salvas em {NEWS_FILE}")
        scheduler_state["last_run"] = datetime.now().isoformat()
        if triggered_by == "automatico":
            scheduler_state["next_run"] = _next_scheduled_run().isoformat()
        scheduler_state["running"]  = False
        entry = {
            "id":           f"notif_{int(time.time())}",
            "timestamp":    datetime.now().isoformat(),
            "triggered_by": triggered_by,
            "total_casos":  summary["total"],
            "erros":        summary["erros"],
            "mudancas":     summary["mudancas"],
            "changes":      summary.get("changes", []),
            "lida":         False,
        }
        save_notification(entry)
        return summary
    except Exception as e:
        scheduler_state["running"] = False
        print(f"[scheduler] Erro: {e}")
        entry = {
            "id":           f"notif_{int(time.time())}",
            "timestamp":    datetime.now().isoformat(),
            "triggered_by": triggered_by,
            "total_casos":  0,
            "erros":        1,
            "mudancas":     0,
            "changes":      [],
            "erro_msg":     str(e),
            "lida":         False,
        }
        save_notification(entry)
        return {"erro": str(e)}


# ─────────────────────────────────────────────
#  ROTAS DA API
# ─────────────────────────────────────────────

@app.route("/")
def index():
    response = send_file(DASHBOARD_FILE)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"]        = "no-cache"
    return response


@app.route("/api/status")
def api_status():
    return jsonify({
        "ok":        True,
        "timestamp": datetime.now().isoformat(),
        "scheduler": {
            "last_run": scheduler_state["last_run"],
            "next_run": scheduler_state["next_run"],
            "running":  scheduler_state["running"],
        },
        "notificacoes_nao_lidas": sum(
            1 for n in load_notifications() if not n.get("lida")
        ),
    })


@app.route("/api/check", methods=["POST"])
def api_check():
    if scheduler_state["running"]:
        return jsonify({"erro": "Verificacao ja em andamento"}), 409
    threading.Thread(
        target=_do_check, kwargs={"triggered_by": "manual"}, daemon=True
    ).start()
    return jsonify({"ok": True, "mensagem": "Verificacao iniciada"})


@app.route("/api/check/status")
def api_check_status():
    return jsonify({
        "running":  scheduler_state["running"],
        "last_run": scheduler_state["last_run"],
        "next_run": scheduler_state["next_run"],
    })


@app.route("/api/notifications")
def api_notifications():
    limit = int(request.args.get("limit", 50))
    return jsonify(load_notifications()[:limit])


@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
def api_mark_read(notif_id):
    notifs = load_notifications()
    for n in notifs:
        if n.get("id") == notif_id:
            n["lida"] = True
            break
    Path(NOTIFICATIONS_FILE).write_text(
        json.dumps(notifs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify({"ok": True})


@app.route("/api/notifications/read-all", methods=["POST"])
def api_mark_all_read():
    notifs = load_notifications()
    for n in notifs:
        n["lida"] = True
    Path(NOTIFICATIONS_FILE).write_text(
        json.dumps(notifs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify({"ok": True})


@app.route("/api/news")
def api_news():
    limit = int(request.args.get("limit", NEWS_TIMELINE))
    return jsonify(load_news()[:limit])


@app.route("/api/state")
def api_state():
    return jsonify(mon_module.load_state())


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 52)
    print("  Monitor Regulatorio PJUS - Servidor Local")
    print("=" * 52)
    print(f"\n  Dashboard:   http://localhost:5000")
    print(f"  Live Reload: ATIVO - salve o HTML e o browser atualiza")
    print(f"  Intervalo:   todo dia às {SCHEDULED_HOUR:02d}h\n")

    threading.Thread(target=scheduled_check, daemon=True).start()
    threading.Thread(target=_watch_html, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
