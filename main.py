import os, re, json, queue, threading, time
import pandas as pd
import spotipy
from flask import Flask, redirect, request, session, Response, render_template_string, jsonify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = "http://127.0.0.1:5000/callback"
SCOPE         = "playlist-read-private playlist-read-collaborative"

# fila de progresso por session_id
progress_queues: dict[str, queue.Queue] = {}
tracks_store:   dict[str, list]         = {}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def make_auth_manager(state=None):
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        show_dialog=True,
        state=state,
        cache_handler=spotipy.cache_handler.MemoryCacheHandler(),
    )

def slug(s):
    return re.sub(r"[^a-z0-9]", "_", s.lower())

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_path(sid):
    return os.path.join(CACHE_DIR, f"{sid}.json")

def save_cache(sid, tracks, display_name):
    import datetime
    data = {
        "display_name": display_name,
        "saved_at": datetime.datetime.utcnow().isoformat(),
        "tracks": tracks,
    }
    with open(cache_path(sid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[CACHE] Salvo {len(tracks)} músicas em {cache_path(sid)}", flush=True)

def load_cache(sid):
    path = cache_path(sid)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[CACHE] Carregado {len(data['tracks'])} músicas de {path}", flush=True)
    return data

# ─────────────────────────────────────────────
# ROTA: página inicial / login
# ─────────────────────────────────────────────
PAGE_LOGIN = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spotify Memory Calendar</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#1f1e1e;color:#f0f0f0;
     min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#272626;border:1px solid #333;border-radius:20px;padding:48px 40px;
      max-width:400px;width:90%;text-align:center}
.logo{color:#1DB954;font-size:52px;margin-bottom:16px}
h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:8px}
p{font-size:13px;color:#aaa;line-height:1.6;margin-bottom:32px}
.btn{display:inline-flex;align-items:center;gap:10px;background:#1DB954;color:#000;
     font-weight:700;font-size:14px;border:none;border-radius:50px;padding:14px 32px;
     cursor:pointer;text-decoration:none;transition:background .15s,transform .1s}
.btn:hover{background:#1ed760;transform:scale(1.03)}
.btn i{font-size:20px}
.footer{margin-top:24px;font-size:11px;color:#555}
</style>
</head>
<body>
<div class="card">
  <div class="logo"><i class="ti ti-brand-spotify"></i></div>
  <h1>Spotify Memory Calendar</h1>
  <p>Veja quais músicas você adicionou hoje em anos anteriores.<br>
     Conecte sua conta do Spotify para começar.</p>
  <a class="btn" href="/login"><i class="ti ti-brand-spotify"></i> Entrar com Spotify</a>
  <div class="footer">Seus dados ficam apenas nesta sessão.</div>
</div>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(PAGE_LOGIN)

# ─────────────────────────────────────────────
# ROTA: inicia OAuth
# ─────────────────────────────────────────────
@app.route("/login")
def login():
    auth = make_auth_manager()
    url  = auth.get_authorize_url()
    # salva code_verifier / state se necessário
    session["auth_state"] = auth.state
    return redirect(url)

# ─────────────────────────────────────────────
# ROTA: callback OAuth
# ─────────────────────────────────────────────
@app.route("/callback")
def callback():
    code  = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"<h2>Erro de autorizacao: {error}</h2><a href='/'>Voltar</a>"
    if not code:
        return "<h2>Codigo de autorizacao ausente.</h2><a href='/'>Voltar</a>"

    auth         = make_auth_manager(state=session.get("auth_state"))
    token_info   = auth.get_access_token(code, as_dict=True, check_cache=False)
    access_token = token_info["access_token"]

    sp   = spotipy.Spotify(auth=access_token)
    user = sp.current_user()
    session["display_name"] = user["display_name"]
    session["user_id"]      = user["id"]
    sid = slug(user["id"])
    session["sid"]   = sid
    session["token"] = access_token

    # verifica se já tem cache salvo para este usuário
    cached = load_cache(sid)
    if cached:
        tracks_store[sid] = cached["tracks"]
        session["cache_saved_at"] = cached.get("saved_at", "")
        return redirect("/calendar")

    progress_queues[sid] = queue.Queue()
    tracks_store[sid]    = None  # marca como "em andamento"

    threading.Thread(
        target=collect_tracks,
        args=(access_token, sid, user["display_name"]),
        daemon=True
    ).start()
    return redirect("/progress")

# ─────────────────────────────────────────────
# COLETA (roda em thread)
# ─────────────────────────────────────────────
def push(sid, msg_type, payload):
    msg = {"type": msg_type, **payload}
    print(f"[{msg_type.upper()}] {payload}", flush=True)
    if sid in progress_queues:
        progress_queues[sid].put(msg)

def spotify_call(func, *args, sid=None, **kwargs):
    """Chama qualquer função do spotipy com retry automático em rate limit."""
    while True:
        try:
            return func(*args, **kwargs)
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get("Retry-After", 5)) + 1
                print(f"[RATE LIMIT] aguardando {retry_after}s...", flush=True)
                if sid:
                    push(sid, "warn", {"text": f"⏳ Rate limit do Spotify — aguardando {retry_after}s e continuando..."})
                time.sleep(retry_after)
            else:
                raise

def collect_tracks(access_token, sid, display_name):
    try:
        sp = spotipy.Spotify(auth=access_token)
        push(sid, "status", {"text": f"Conectado como {display_name}"})

        # usa o user_id real para filtrar playlists (mais confiavel que display_name)
        user_id = spotify_call(sp.current_user, sid=sid)["id"]

        playlists_res = spotify_call(sp.current_user_playlists, limit=50, sid=sid)
        all_playlists = list(playlists_res["items"])
        while playlists_res["next"]:
            playlists_res = spotify_call(sp.next, playlists_res, sid=sid)
            all_playlists.extend(playlists_res["items"])

        push(sid, "status", {"text": f"{len(all_playlists)} playlists encontradas, filtrando as suas..."})

        # filtra por owner id (nao display_name, que pode divergir)
        own = [p for p in all_playlists if p["owner"]["id"] == user_id]
        total_pl = len(own)
        push(sid, "status", {"text": f"{total_pl} playlists suas encontradas"})

        if total_pl == 0:
            push(sid, "warn", {"text": "Nenhuma playlist propria encontrada."})

        songs = []
        for i, pl in enumerate(own, 1):
            push(sid, "playlist", {
                "name":    pl["name"],
                "index":   i,
                "total":   total_pl,
                "percent": round(i / total_pl * 100),
            })
            try:
                offset = 0
                while True:
                    items = spotify_call(sp.playlist_items, pl["id"], offset=offset, limit=100, sid=sid)
                    for item in items["items"]:
                        try:
                            if item is None:
                                continue
                            # endpoint playlist_items retorna item["item"], nao item["track"]
                            t = item.get("item") or item.get("track")
                            if t is None:
                                continue
                            if t.get("is_local") or not t.get("id"):
                                continue
                            album = t.get("album") or {}
                            imgs  = album.get("images") or []
                            if not imgs:
                                continue
                            added_at = item.get("added_at") or ""
                            songs.append({
                                "id":       len(songs) + 1,
                                "name":     t.get("name", "Desconhecido"),
                                "artists":  ", ".join(dict.fromkeys(
                                                a["name"] for a in (t.get("artists") or [])
                                            )) or "Desconhecido",
                                "playlist": pl["name"],
                                "added_at": added_at,
                                "url_song": (t.get("external_urls") or {}).get("spotify", ""),
                                "image":    imgs[1]["url"] if len(imgs) > 1 else imgs[0]["url"],
                            })
                        except Exception as item_err:
                            import traceback
                            err_detail = traceback.format_exc()
                            print(f"[ITEM_ERR] playlist={pl['name']} erro={item_err}\n{err_detail}", flush=True)
                            push(sid, "warn", {"text": f"Item ignorado ({pl['name']}): {item_err}"})
                    if not items["next"]:
                        break
                    offset += 100
            except Exception as e:
                import traceback
                push(sid, "warn", {"text": f"Erro em '{pl['name']}': {e} | {traceback.format_exc()}"})

        tracks_store[sid] = songs
        save_cache(sid, songs, display_name)
        push(sid, "done", {"total": len(songs)})
    except Exception as e:
        import traceback
        push(sid, "error", {"text": str(e) + "\n" + traceback.format_exc()})
        tracks_store[sid] = []

# ─────────────────────────────────────────────
# ROTA: tela de progresso
# ─────────────────────────────────────────────
PAGE_PROGRESS = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coletando músicas…</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#1f1e1e;color:#f0f0f0;
     min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#272626;border:1px solid #333;border-radius:20px;padding:40px 36px;
      max-width:480px;width:92%}
.top{display:flex;align-items:center;gap:12px;margin-bottom:28px}
.logo{color:#1DB954;font-size:32px}
h1{font-size:18px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#aaa;margin-top:2px}

.bar-wrap{background:#1a1a1a;border-radius:50px;height:8px;overflow:hidden;margin-bottom:10px}
.bar{height:100%;background:#1DB954;border-radius:50px;width:0%;transition:width .4s ease}

.pl-name{font-size:13px;color:#ddd;margin-bottom:20px;min-height:18px;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl-name span{color:#1DB954;font-weight:600}

.log{background:#1a1a1a;border-radius:10px;padding:12px 14px;max-height:160px;
     overflow-y:auto;font-size:11px;color:#777;line-height:1.7;
     scrollbar-width:thin;scrollbar-color:#333 transparent}
.log .ok{color:#1DB954}
.log .warn{color:#e6a817}
.log .err{color:#e05c5c}

.done-block{display:none;text-align:center;margin-top:24px}
.done-block p{font-size:13px;color:#aaa;margin-bottom:16px}
.btn{display:inline-flex;align-items:center;gap:8px;background:#1DB954;color:#000;
     font-weight:700;font-size:14px;border:none;border-radius:50px;padding:13px 28px;
     cursor:pointer;text-decoration:none;transition:background .15s,transform .1s}
.btn:hover{background:#1ed760;transform:scale(1.03)}
</style>
</head>
<body>
<div class="card">
  <div class="top">
    <i class="ti ti-brand-spotify logo"></i>
    <div>
      <h1>Coletando suas músicas</h1>
      <div class="sub" id="status-text">Aguardando…</div>
    </div>
  </div>

  <div class="bar-wrap"><div class="bar" id="bar"></div></div>
  <div class="pl-name" id="pl-name">iniciando…</div>

  <div class="log" id="log"></div>

  <div class="done-block" id="done-block">
    <p id="done-msg"></p>
    <a class="btn" href="/calendar"><i class="ti ti-calendar"></i> Ver meu calendário</a>
  </div>
</div>

<script>
const bar      = document.getElementById('bar');
const plName   = document.getElementById('pl-name');
const statusTx = document.getElementById('status-text');
const logEl    = document.getElementById('log');
const doneBlk  = document.getElementById('done-block');
const doneMsg  = document.getElementById('done-msg');

function addLog(text, cls) {
  const d = document.createElement('div');
  if (cls) d.className = cls;
  d.textContent = text;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}

const es = new EventSource('/stream');
es.onmessage = e => {
  const msg = JSON.parse(e.data);

  if (msg.type === 'status') {
    statusTx.textContent = msg.text;
    addLog('ℹ ' + msg.text);
  }
  else if (msg.type === 'playlist') {
    bar.style.width = msg.percent + '%';
    plName.innerHTML = `Playlist <span>${msg.name}</span> — ${msg.index} de ${msg.total}`;
    addLog(`📂 ${msg.name}`);
  }
  else if (msg.type === 'warn') {
    addLog('⚠ ' + msg.text, 'warn');
  }
  else if (msg.type === 'error') {
    addLog('✗ ' + msg.text, 'err');
    statusTx.textContent = 'Erro na coleta.';
    es.close();
  }
  else if (msg.type === 'done') {
    bar.style.width = '100%';
    plName.innerHTML = '<span>Coleta concluída!</span>';
    doneMsg.textContent = msg.total + ' músicas coletadas no total.';
    doneBlk.style.display = 'block';
    addLog('✓ Concluído — ' + msg.total + ' músicas', 'ok');
    es.close();
  }
};
</script>
</body>
</html>"""

@app.route("/progress")
def progress():
    if "sid" not in session:
        return redirect("/")
    return render_template_string(PAGE_PROGRESS)

# ─────────────────────────────────────────────
# ROTA: SSE stream de progresso
# ─────────────────────────────────────────────
@app.route("/stream")
def stream():
    sid = session.get("sid")
    if not sid or sid not in progress_queues:
        return Response("data: {}\n\n", mimetype="text/event-stream")

    def generate():
        q = progress_queues[sid]
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─────────────────────────────────────────────
# ROTA: calendário
# ─────────────────────────────────────────────
CALENDAR_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spotify Memory Calendar</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#1f1e1e;color:#f0f0f0;
     display:flex;flex-direction:column;height:100vh;padding:14px 18px 10px}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-shrink:0}
.brand{color:#1DB954;font-size:22px}
.label{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#aaa;margin-bottom:2px}
.user-name{font-size:11px;color:#1DB954;margin-top:1px;font-weight:600}
.month-name{font-size:24px;font-weight:700;color:#fff;line-height:1}
.nav{display:flex;align-items:center;gap:6px}
.nav-btn{background:#2a2a2a;border:1px solid #3a3a3a;color:#ddd;width:34px;height:34px;
         border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;
         font-size:16px;transition:background .15s,color .15s}
.nav-btn:hover{background:#1DB954;color:#000;border-color:#1DB954}
.nav-today{background:#2a2a2a;border:1px solid #3a3a3a;color:#ddd;height:34px;padding:0 14px;
           border-radius:8px;cursor:pointer;font-size:11px;letter-spacing:.08em;
           text-transform:uppercase;transition:background .15s,color .15s}
.nav-today:hover{background:#333;color:#fff}
.btn-logout,.btn-refresh{background:none;border:1px solid #3a3a3a;color:#888;height:34px;padding:0 12px;
            border-radius:8px;cursor:pointer;font-size:11px;text-decoration:none;
            display:flex;align-items:center;gap:5px;transition:border-color .15s,color .15s}
.btn-logout:hover{border-color:#e05c5c;color:#e05c5c}
.btn-refresh:hover{border-color:#1DB954;color:#1DB954}
.legend{font-size:11px;color:#ccc;letter-spacing:.04em}
.weekdays{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;margin-bottom:5px;flex-shrink:0}
.wd{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#aaa;text-align:center;padding:4px 0}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;flex:1;min-height:0}
.day{border-radius:10px;border:1px solid #2e2e2e;padding:7px;background:#272626;
     display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden;
     transition:border-color .15s;scrollbar-width:thin;scrollbar-color:#3a3a3a transparent}
.day::-webkit-scrollbar{width:3px}
.day::-webkit-scrollbar-thumb{background:#3a3a3a;border-radius:2px}
.day:hover{border-color:#444}
.day.empty{border-color:transparent;background:transparent;overflow:hidden}
.day.today{border-color:#1DB954}
.day-num{font-size:12px;color:#ddd;margin-bottom:5px;flex-shrink:0;font-variant-numeric:tabular-nums;font-weight:500}
.day.today .day-num{color:#1DB954;font-weight:700}
.covers{display:grid;gap:3px}
.cover-wrap{position:relative;cursor:pointer;border-radius:5px;overflow:hidden;width:100%}
.cover-wrap img{display:block;width:100%;height:100%;object-fit:cover;border-radius:5px;transition:transform .15s,opacity .15s}
.covers.single .cover-wrap{aspect-ratio:unset}
.covers.single .cover-wrap img{height:auto;max-height:100px}
.covers.multi .cover-wrap{aspect-ratio:1}
.cover-wrap:hover img{transform:scale(1.08);opacity:.75}
.tooltip{position:fixed;background:#1a1a1a;border:1px solid #3a3a3a;border-radius:10px;
         padding:0;pointer-events:none;opacity:0;transition:opacity .1s;z-index:9999;
         min-width:200px;max-width:260px;overflow:hidden}
.tooltip.visible{opacity:1}
.tooltip-img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.tooltip-body{padding:10px 12px}
.tip-song{display:block;font-weight:700;font-size:13px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tip-artist{display:block;font-size:12px;color:#1DB954;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.tip-divider{display:block;height:1px;background:#2e2e2e;margin:8px 0}
.tip-row{display:flex;align-items:center;gap:6px;margin-top:5px}
.tip-row i{font-size:13px;color:#888;flex-shrink:0}
.tip-label{font-size:10px;color:#888;display:block;margin-bottom:1px;text-transform:uppercase;letter-spacing:.06em}
.tip-value{font-size:11px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.year-badge{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 7px;letter-spacing:.03em;line-height:1.5}
.modal-item-year-badge{display:inline-block;font-size:12px;font-weight:700;border-radius:5px;padding:2px 7px;letter-spacing:.03em;line-height:1.5;margin-top:6px}
.more-btn{font-size:15px;font-weight:700;background:#1DB954;border:none;border-radius:5px;
          color:#000;cursor:pointer;transition:background .12s,transform .1s;
          display:flex;align-items:center;justify-content:center;width:100%;aspect-ratio:1;letter-spacing:-.5px}
.more-btn:hover{background:#1ed760;transform:scale(1.05)}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:10000;display:none;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#272626;border:1px solid #3a3a3a;border-radius:16px;padding:24px;
       max-width:720px;width:92vw;max-height:82vh;overflow-y:auto}
.modal-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px}
.modal-title{font-size:17px;font-weight:700;color:#fff}
.modal-date{font-size:12px;color:#1DB954;margin-top:3px}
.modal-close{background:none;border:1px solid #444;color:#ddd;width:32px;height:32px;
             border-radius:8px;cursor:pointer;font-size:18px;display:flex;align-items:center;
             justify-content:center;transition:background .12s;flex-shrink:0}
.modal-close:hover{background:#333;color:#fff}
.modal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px}
.modal-item{cursor:pointer;border-radius:10px;overflow:hidden;background:#2e2e2e;
            border:1px solid #3a3a3a;transition:border-color .15s,transform .12s}
.modal-item:hover{border-color:#1DB954;transform:scale(1.03)}
.modal-item img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.modal-item-info{padding:10px}
.modal-item-name{font-size:12px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-item-artist{font-size:11px;color:#1DB954;margin-top:2px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-item-divider{height:1px;background:#3a3a3a;margin:8px 0}
.modal-item-row{display:flex;align-items:flex-start;gap:5px;margin-top:5px}
.modal-item-row i{font-size:12px;color:#888;flex-shrink:0;margin-top:1px}
.modal-item-label{font-size:9px;color:#888;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:1px}
.modal-item-value{font-size:10px;color:#ccc;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
</style>
</head>
<body>
<div class="header">
  <div style="display:flex;align-items:center;gap:10px">
    <i class="ti ti-brand-spotify brand"></i>
    <div>
      <div class="label">memórias musicais</div>
      <div class="user-name">{{ display_name }}{% if cache_saved_at %} · <span style="color:#555;font-weight:400">cache de {{ cache_saved_at }}</span>{% endif %}</div>
      <div class="month-name" id="month-name">—</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <div class="legend" id="legend"></div>
    <div class="nav">
      <button class="nav-btn" id="prev-year"  title="Ano anterior"><i class="ti ti-chevrons-left"></i></button>
      <button class="nav-btn" id="prev-month" title="Mês anterior"><i class="ti ti-chevron-left"></i></button>
      <button class="nav-today" id="go-today">Hoje</button>
      <button class="nav-btn" id="next-month" title="Próximo mês"><i class="ti ti-chevron-right"></i></button>
      <button class="nav-btn" id="next-year"  title="Próximo ano"><i class="ti ti-chevrons-right"></i></button>
    </div>
    <a class="btn-refresh" href="/refresh" title="Forçar nova coleta do Spotify"><i class="ti ti-refresh"></i> Atualizar</a>
    <a class="btn-logout" href="/logout"><i class="ti ti-logout"></i> Sair</a>
  </div>
</div>

<div class="weekdays">
  <div class="wd">dom</div><div class="wd">seg</div><div class="wd">ter</div>
  <div class="wd">qua</div><div class="wd">qui</div><div class="wd">sex</div><div class="wd">sáb</div>
</div>
<div class="grid" id="cal-grid"></div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <div class="modal-header">
      <div><div class="modal-title" id="modal-title"></div><div class="modal-date" id="modal-date"></div></div>
      <button class="modal-close" id="modal-close"><i class="ti ti-x"></i></button>
    </div>
    <div class="modal-grid" id="modal-grid"></div>
  </div>
</div>
<div class="tooltip" id="global-tooltip"></div>

<script>
const TRACKS = {{ tracks_json | safe }};
const MESES  = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const nowReal = new Date();
let curYear = nowReal.getFullYear(), curMonth = nowReal.getMonth();
const tooltip = document.getElementById('global-tooltip');

const ALL_YEARS = [...new Set(TRACKS.map(t => new Date(t.added_at).getUTCFullYear()))];
const MIN_YEAR  = Math.min(...ALL_YEARS);
const MAX_YEAR  = Math.max(...ALL_YEARS);

function yearColor(year) {
  if (MIN_YEAR === MAX_YEAR) return {bg:'rgba(99,179,237,.18)',text:'#63b3ed'};
  const t = (year - MIN_YEAR) / (MAX_YEAR - MIN_YEAR);
  let r,g,b;
  if (t < .5) { const tt=t/.5; r=220; g=Math.round(80+tt*140); b=30; }
  else         { const tt=(t-.5)/.5; r=Math.round(220-tt*160); g=Math.round(220-tt*90); b=Math.round(30+tt*210); }
  return {bg:`rgba(${r},${g},${b},.18)`,text:`rgb(${r},${g},${b})`};
}
function yearBadge(year, cls) {
  const {bg,text} = yearColor(year);
  return `<span class="${cls||'year-badge'}" style="background:${bg};color:${text}">${year}</span>`;
}
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('pt-BR',{day:'2-digit',month:'long',year:'numeric',timeZone:'UTC'});
}
function showTooltip(el, s) {
  tooltip.innerHTML = `
    <img class="tooltip-img" src="${s.image}" alt="${s.name}">
    <div class="tooltip-body">
      <span class="tip-song">${s.name}</span>
      <span class="tip-artist">${s.artists||'Artista desconhecido'}</span>
      ${yearBadge(s.year)}
      <span class="tip-divider"></span>
      <div class="tip-row"><i class="ti ti-calendar"></i><div><span class="tip-label">Adicionado em</span><span class="tip-value">${formatDate(s.added_at)}</span></div></div>
      <div class="tip-row"><i class="ti ti-music"></i><div><span class="tip-label">Playlist</span><span class="tip-value">${s.playlist}</span></div></div>
    </div>`;
  tooltip.classList.add('visible');
  requestAnimationFrame(() => {
    const r=el.getBoundingClientRect(), tw=tooltip.offsetWidth, th=tooltip.offsetHeight;
    let top=r.top-th-8, left=r.left+r.width/2-tw/2;
    if(top<8) top=r.bottom+8;
    if(left<8) left=8;
    if(left+tw>innerWidth-8) left=innerWidth-tw-8;
    tooltip.style.top=top+'px'; tooltip.style.left=left+'px';
  });
}
function hideTooltip(){ tooltip.classList.remove('visible'); }

function openModal(day, songs) {
  document.getElementById('modal-title').textContent = songs.length+' música'+(songs.length>1?'s':'')+' neste dia';
  document.getElementById('modal-date').textContent  = day+' de '+MESES[curMonth]+' — vários anos';
  const mg = document.getElementById('modal-grid');
  mg.innerHTML='';
  songs.forEach(s => {
    const item = document.createElement('div');
    item.className='modal-item';
    item.innerHTML=`<img src="${s.image}" alt="${s.name}">
      <div class="modal-item-info">
        <div class="modal-item-name">${s.name}</div>
        <div class="modal-item-artist">${s.artists||'Artista desconhecido'}</div>
        ${yearBadge(s.year,'modal-item-year-badge')}
        <div class="modal-item-divider"></div>
        <div class="modal-item-row"><i class="ti ti-calendar"></i><div><span class="modal-item-label">Adicionado em</span><span class="modal-item-value">${formatDate(s.added_at)}</span></div></div>
        <div class="modal-item-row"><i class="ti ti-music"></i><div><span class="modal-item-label">Playlist</span><span class="modal-item-value">${s.playlist}</span></div></div>
      </div>`;
    item.addEventListener('click', ()=>window.open(s.url_song,'_blank'));
    mg.appendChild(item);
  });
  document.getElementById('modal-overlay').classList.add('open');
}
document.getElementById('modal-close').addEventListener('click',()=>document.getElementById('modal-overlay').classList.remove('open'));
document.getElementById('modal-overlay').addEventListener('click',e=>{ if(e.target===document.getElementById('modal-overlay')) document.getElementById('modal-overlay').classList.remove('open'); });

const MAX_VISIBLE=6;
function getCols(n){ const s=Math.min(n,MAX_VISIBLE); if(s===1)return 1; if(s<=4)return 2; return 3; }

function buildCalendar() {
  const year=curYear, month=curMonth;
  const isCur=(nowReal.getFullYear()===year && nowReal.getMonth()===month);
  document.getElementById('month-name').textContent=MESES[month]+' '+year;
  const daysInMonth=new Date(year,month+1,0).getDate();
  const firstDow   =new Date(year,month,1).getDay();
  const byDay={};
  TRACKS.forEach(t=>{
    const d=new Date(t.added_at), tm=d.getUTCMonth(), td=d.getUTCDate(), ty=d.getUTCFullYear();
    if(tm===month && ty!==year){ if(!byDay[td])byDay[td]=[]; byDay[td].push({...t,year:ty}); }
  });
  Object.values(byDay).forEach(a=>a.sort((a,b)=>b.year-a.year));
  const grid=document.getElementById('cal-grid');
  grid.innerHTML='';
  for(let i=0;i<firstDow;i++){ const e=document.createElement('div'); e.className='day empty'; grid.appendChild(e); }
  for(let d=1;d<=daysInMonth;d++){
    const cell=document.createElement('div');
    cell.className='day'+(isCur && d===nowReal.getDate()?' today':'');
    const num=document.createElement('span'); num.className='day-num'; num.textContent=d; cell.appendChild(num);
    const songs=byDay[d]||[];
    if(songs.length>0){
      const hasMore=songs.length>MAX_VISIBLE;
      const showImgs=hasMore?MAX_VISIBLE-1:songs.length;
      const cols=getCols(songs.length);
      const covers=document.createElement('div');
      covers.className='covers '+(songs.length===1?'single':'multi');
      covers.style.gridTemplateColumns=`repeat(${cols},1fr)`;
      songs.slice(0,showImgs).forEach(s=>{
        const wrap=document.createElement('div'); wrap.className='cover-wrap';
        const img=document.createElement('img'); img.src=s.image; img.alt=s.name;
        wrap.appendChild(img);
        wrap.addEventListener('mouseenter',()=>showTooltip(img,s));
        wrap.addEventListener('mouseleave',hideTooltip);
        wrap.addEventListener('click',ev=>{ev.stopPropagation();window.open(s.url_song,'_blank');});
        covers.appendChild(wrap);
      });
      if(hasMore){
        const more=document.createElement('button'); more.className='more-btn';
        more.textContent='+' +(songs.length-showImgs);
        more.addEventListener('click',ev=>{ev.stopPropagation();openModal(d,songs);});
        covers.appendChild(more);
      }
      cell.appendChild(covers);
    }
    grid.appendChild(cell);
  }
  const total=Object.values(byDay).reduce((a,b)=>a+b.length,0);
  document.getElementById('legend').textContent=
    total>0?total+' música'+(total>1?'s':'')+' neste mês em anos anteriores':'nenhuma música neste mês em anos anteriores';
}
document.getElementById('prev-month').addEventListener('click',()=>{curMonth--;if(curMonth<0){curMonth=11;curYear--;}buildCalendar();});
document.getElementById('next-month').addEventListener('click',()=>{curMonth++;if(curMonth>11){curMonth=0;curYear++;}buildCalendar();});
document.getElementById('prev-year') .addEventListener('click',()=>{curYear--;buildCalendar();});
document.getElementById('next-year') .addEventListener('click',()=>{curYear++;buildCalendar();});
document.getElementById('go-today')  .addEventListener('click',()=>{curYear=nowReal.getFullYear();curMonth=nowReal.getMonth();buildCalendar();});
window.addEventListener('resize',buildCalendar);
buildCalendar();
</script>
</body>
</html>"""

@app.route("/calendar")
def calendar():
    sid = session.get("sid")
    if not sid or sid not in tracks_store:
        return redirect("/")
    tracks = tracks_store[sid]

    if tracks is None:
        return redirect("/progress")  # ainda coletando

    if len(tracks) == 0:
        return render_template_string("""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Erro</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css">
<style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Segoe UI',sans-serif;background:#1f1e1e;
color:#f0f0f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#272626;border:1px solid #3a3a3a;border-radius:20px;padding:40px;max-width:420px;
width:90%;text-align:center}.icon{font-size:48px;color:#e05c5c;margin-bottom:16px}
h2{font-size:18px;font-weight:700;color:#fff;margin-bottom:10px}
p{font-size:13px;color:#aaa;line-height:1.6;margin-bottom:24px}
.btn{display:inline-flex;align-items:center;gap:8px;background:#1DB954;color:#000;
font-weight:700;font-size:13px;border-radius:50px;padding:12px 24px;text-decoration:none;
transition:background .15s}.btn:hover{background:#1ed760}</style></head>
<body><div class="card"><div class="icon"><i class="ti ti-alert-circle"></i></div>
<h2>Nenhuma música coletada</h2>
<p>Pode ter ocorrido um erro durante a coleta ou suas playlists estão vazias.<br>
Tente fazer login novamente.</p>
<a class="btn" href="/logout"><i class="ti ti-refresh"></i> Tentar novamente</a>
</div></body></html>""")

    df = pd.DataFrame(tracks)
    df["added_at"] = pd.to_datetime(df["added_at"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    tracks_json = json.dumps(df.to_dict(orient="records"), ensure_ascii=False)
    import datetime
    saved_at_raw = session.get("cache_saved_at", "")
    saved_at_fmt = ""
    if saved_at_raw:
        try:
            dt = datetime.datetime.fromisoformat(saved_at_raw)
            saved_at_fmt = dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass

    return render_template_string(
        CALENDAR_TEMPLATE,
        tracks_json=tracks_json,
        display_name=session.get("display_name", ""),
        cache_saved_at=saved_at_fmt,
    )

# ─────────────────────────────────────────────
# ROTA: logout
# ─────────────────────────────────────────────
@app.route("/refresh")
def refresh():
    """Apaga o cache e força nova coleta."""
    sid = session.get("sid")
    if sid:
        path = cache_path(sid)
        if os.path.exists(path):
            os.remove(path)
            print(f"[CACHE] Removido {path}", flush=True)
        tracks_store.pop(sid, None)
        progress_queues.pop(sid, None)
    # mantém a sessão mas força nova coleta
    access_token = session.get("token")
    if not access_token:
        return redirect("/")
    sp   = spotipy.Spotify(auth=access_token)
    try:
        user = sp.current_user()
    except Exception:
        return redirect("/logout")
    progress_queues[sid] = queue.Queue()
    tracks_store[sid]    = None
    threading.Thread(
        target=collect_tracks,
        args=(access_token, sid, session.get("display_name", "")),
        daemon=True
    ).start()
    return redirect("/progress")

@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid:
        tracks_store.pop(sid, None)
        progress_queues.pop(sid, None)
    session.clear()
    return redirect("/")

@app.route("/debug/tracks")
def debug_tracks():
    """Mostra as primeiras músicas e quantas batem com o mês/dia atual."""
    import datetime
    sid = session.get("sid")
    if not sid or sid not in tracks_store:
        return jsonify({"error": "sem dados"})
    tracks = tracks_store[sid] or []
    now = datetime.datetime.utcnow()
    cur_month = now.month - 1  # JS usa 0-indexed
    cur_year  = now.year

    matches = []
    for t in tracks:
        added = t.get("added_at", "")
        try:
            d = datetime.datetime.fromisoformat(added.replace("Z", "+00:00"))
            if d.month - 1 == cur_month and d.year != cur_year:
                matches.append({
                    "name":     t["name"],
                    "added_at": added,
                    "month":    d.month,
                    "day":      d.day,
                    "year":     d.year,
                })
        except Exception as e:
            pass

    return jsonify({
        "cur_month_js": cur_month,
        "cur_year":     cur_year,
        "total_tracks": len(tracks),
        "matches_this_month": len(matches),
        "sample_matches": matches[:10],
        "sample_added_at": [t.get("added_at") for t in tracks[:5]],
    })

@app.route("/debug")
def debug():
    sid = session.get("sid")
    if not sid:
        return jsonify({"error": "sem sessao ativa"})

    q   = progress_queues.get(sid)
    tr  = tracks_store.get(sid)
    msgs = []
    if q:
        # drena a fila sem bloquear para ver o que esta la
        while not q.empty():
            try: msgs.append(q.get_nowait())
            except: break

    return jsonify({
        "sid":            sid,
        "display_name":   session.get("display_name"),
        "tracks_count":   len(tr) if isinstance(tr, list) else str(tr),
        "queue_messages": msgs,
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
