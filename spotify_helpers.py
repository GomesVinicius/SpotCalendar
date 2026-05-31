import os, re, time
import spotipy
from spotipy.oauth2 import SpotifyOAuth

CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI  = os.getenv("REDIRECT_URI", "http://127.0.0.1:5000/callback")
SCOPE         = "playlist-read-private playlist-read-collaborative"


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


def spotify_call(func, *args, **kwargs):
    """Retry automático em rate limit."""
    while True:
        try:
            return func(*args, **kwargs)
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get("Retry-After", 5)) + 1
                print(f"[RATE LIMIT] aguardando {retry_after}s...", flush=True)
                time.sleep(retry_after)
            else:
                raise


# Estado global de progresso (por user_id)
_progress = {}  # user_id -> {"done": [...], "current": None, "total": 0, "finished": False}

def get_progress(user_id):
    return _progress.get(user_id, {"done": [], "current": None, "total": 0, "finished": False})


def collect_tracks(access_token, user_id):
    """
    Coleta todas as músicas das playlists do usuário.
    Roda de forma SÍNCRONA — retorna a lista quando terminar.
    """
    _progress[user_id] = {"done": [], "current": None, "total": 0, "finished": False}

    sp = spotipy.Spotify(auth=access_token)
    playlists_res = spotify_call(sp.current_user_playlists, limit=50)
    all_playlists = list(playlists_res["items"])
    while playlists_res["next"]:
        playlists_res = spotify_call(sp.next, playlists_res)
        all_playlists.extend(playlists_res["items"])

    own = [p for p in all_playlists if p["owner"]["id"] == user_id]
    print(f"[COLLECT] {len(own)} playlists proprias encontradas", flush=True)
    _progress[user_id]["total"] = len(own)

    songs = []
    for pl in own:
        print(f"[COLLECT] coletando: {pl['name']}", flush=True)
        _progress[user_id]["current"] = pl["name"]
        try:
            offset = 0
            pl_count = 0
            while True:
                items = spotify_call(sp.playlist_items, pl["id"], offset=offset, limit=100)
                for item in items["items"]:
                    try:
                        if item is None:
                            continue
                        t = item.get("item") or item.get("track")
                        if not t or t.get("is_local") or not t.get("id"):
                            continue
                        imgs = (t.get("album") or {}).get("images") or []
                        if not imgs:
                            continue
                        img_url  = imgs[1]["url"] if len(imgs) > 1 else imgs[0]["url"]
                        song_url = (t.get("external_urls") or {}).get("spotify", "")
                        song_id  = song_url.rstrip("/").rsplit("/", 1)[-1] if song_url else ""
                        image_id = img_url.rstrip("/").rsplit("/", 1)[-1]  if img_url  else ""
                        songs.append({
                            "id":       len(songs) + 1,
                            "name":     t.get("name", ""),
                            "artists":  ", ".join(dict.fromkeys(
                                            a["name"] for a in (t.get("artists") or [])
                                        )),
                            "playlist": pl["name"],
                            "added_at": item.get("added_at") or "",
                            "sid":      song_id,
                            "iid":      image_id,
                        })
                        pl_count += 1
                    except Exception as e:
                        print(f"[ITEM_ERR] {e}", flush=True)
                if not items["next"]:
                    break
                offset += 100
        except Exception as e:
            print(f"[PL_ERR] {pl['name']}: {e}", flush=True)

        # Marca playlist como concluída
        _progress[user_id]["done"].append({"name": pl["name"], "total": pl_count})
        _progress[user_id]["current"] = None

    _progress[user_id]["finished"] = True
    print(f"[COLLECT] total: {len(songs)} músicas", flush=True)
    return songs
