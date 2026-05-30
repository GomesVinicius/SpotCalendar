import spotipy
from flask import redirect, request, session, render_template, jsonify

from spotify_helpers import make_auth_manager, collect_tracks


def register_routes(app):

    @app.route("/")
    def index():
        return render_template("login.html")

    @app.route("/login")
    def login():
        auth = make_auth_manager()
        session["auth_state"] = auth.state
        return redirect(auth.get_authorize_url())

    @app.route("/callback")
    def callback():
        error = request.args.get("error")
        code  = request.args.get("code")
        if error:
            return f"<h2>Erro: {error}</h2><a href='/'>Voltar</a>"
        if not code:
            return "<h2>Código ausente.</h2><a href='/'>Voltar</a>"

        auth         = make_auth_manager(state=session.get("auth_state"))
        token_info   = auth.get_access_token(code, as_dict=True, check_cache=False)
        access_token = token_info["access_token"]

        sp   = spotipy.Spotify(auth=access_token)
        user = sp.current_user()

        session["display_name"] = user["display_name"]
        session["user_id"]      = user["id"]
        session["token"]        = access_token
        session["collecting"]   = False
        session["collect_done"] = False
        session["collect_error"]= ""

        # Vai para o loading — que fará polling em /api/status
        # A coleta começa quando o browser chama /api/collect
        return redirect("/loading")

    @app.route("/loading")
    def loading():
        if "user_id" not in session:
            return redirect("/")
        force = session.pop("force_collect", False)
        return render_template("loading.html",
            user_id=session.get("user_id", ""),
            force="true" if force else "false",
        )

    @app.route("/api/collect", methods=["POST"])
    def api_collect():
        """
        Inicia a coleta de forma síncrona.
        Chamado via fetch() pelo polling da página de loading.
        Bloqueia até terminar e salva o resultado na sessão.
        """
        if "user_id" not in session:
            return jsonify({"error": "não autenticado"}), 401

        access_token = session.get("token")
        user_id      = session["user_id"]

        try:
            tracks = collect_tracks(access_token, user_id)
            # NÃO salva na sessão — retorna direto no body da resposta
            # o JavaScript recebe e salva no localStorage
            session["collect_done"]  = True
            session["collect_error"] = ""
            return jsonify({"ok": True, "total": len(tracks), "tracks": tracks})
        except Exception as e:
            import traceback
            session["collect_error"] = str(e)
            session["collect_done"]  = True
            print(traceback.format_exc(), flush=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/status")
    def api_status():
        """Polling: retorna se a coleta terminou."""
        if "user_id" not in session:
            return jsonify({"error": "não autenticado"})
        if session.get("collect_error"):
            return jsonify({"error": session["collect_error"]})
        if session.get("collect_done"):
            return jsonify({"ready": True, "message": f"{len(session.get('tracks', []))} músicas coletadas"})
        return jsonify({"ready": False, "message": "coletando..."})

    @app.route("/calendar")
    def calendar():
        if "user_id" not in session:
            return redirect("/")
        # Tracks nunca ficam no servidor — o JS sempre lê do localStorage
        # tracks_json = null sinaliza pro JS carregar do localStorage
        return render_template(
            "calendar.html",
            tracks_json="null",
            user_id=session.get("user_id", ""),
            display_name=session.get("display_name", ""),
        )

    @app.route("/refresh")
    def refresh():
        """Força nova coleta ignorando o localStorage."""
        session["collect_done"]   = False
        session["collect_error"]  = ""
        session["force_collect"]  = True
        session.pop("tracks", None)
        return redirect("/loading")

    @app.route("/logout")
    def logout():
        session.clear()
        return """<!DOCTYPE html><html><head>
<script>localStorage.clear(); window.location='/';</script>
</head></html>"""
