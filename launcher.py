"""
Spotify Memory Calendar — Launcher
Roda o Flask diretamente na thread (sem subprocess),
compatível com PyInstaller --onefile.
"""
import os
import sys
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

# ── Resolve caminho de recursos (funciona em .py e no .exe do PyInstaller) ────
def resource_path(rel=""):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel) if rel else base

# Garante que o diretório dos módulos do projeto esteja no sys.path
_proj = resource_path()
if _proj not in sys.path:
    sys.path.insert(0, _proj)

# ── Paleta de cores ───────────────────────────────────────────────────────────
BG       = "#1f1e1e"
CARD     = "#272626"
BORDER   = "#333333"
GREEN    = "#1DB954"
GREEN_HV = "#1ed760"
FG       = "#f0f0f0"
FG_DIM   = "#aaaaaa"
FG_DARK  = "#555555"
FONT     = "Segoe UI"

# Referência global ao app Flask (para poder parar)
_flask_thread = None
_flask_server = None   # werkzeug.serving.BaseWSGIServer


class RoundedEntry(tk.Frame):
    def __init__(self, parent, show="", **kw):
        super().__init__(parent, bg=CARD)
        self._border = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        self._border.pack(fill="x")
        inner = tk.Frame(self._border, bg="#1a1a1a")
        inner.pack(fill="x")
        self.var = tk.StringVar()
        self.entry = tk.Entry(
            inner, textvariable=self.var, show=show,
            font=(FONT, 11), bg="#1a1a1a", fg=FG,
            insertbackground=FG, relief="flat", bd=0,
        )
        self.entry.pack(fill="x", padx=10, pady=8)
        self.entry.bind("<FocusIn>",  lambda _: self._border.config(bg=GREEN))
        self.entry.bind("<FocusOut>", lambda _: self._border.config(bg=BORDER))

    def get(self):
        return self.var.get().strip()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spotify Memory Calendar")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(480, 560)
        self._server = None      # werkzeug server (para shutdown)
        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, bg=BG, padx=24, pady=24)
        outer.pack(fill="both", expand=True)

        card = tk.Frame(outer, bg=CARD, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)

        inner = tk.Frame(card, bg=CARD, padx=32, pady=32)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="🎵", font=(FONT, 38), bg=CARD, fg=GREEN).pack()
        tk.Label(inner, text="Spotify Memory Calendar",
                 font=(FONT, 16, "bold"), bg=CARD, fg=FG).pack(pady=(8, 4))
        tk.Label(inner,
                 text="Insira as credenciais do seu app Spotify para iniciar.",
                 font=(FONT, 10), bg=CARD, fg=FG_DIM,
                 wraplength=360, justify="center").pack(pady=(0, 24))

        tk.Label(inner, text="CLIENT_ID", font=(FONT, 10, "bold"),
                 bg=CARD, fg=FG, anchor="w").pack(fill="x")
        self._id_entry = RoundedEntry(inner)
        self._id_entry.pack(fill="x", pady=(4, 16))

        tk.Label(inner, text="CLIENT_SECRET", font=(FONT, 10, "bold"),
                 bg=CARD, fg=FG, anchor="w").pack(fill="x")
        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(4, 8))
        self._secret_entry = RoundedEntry(row, show="•")
        self._secret_entry.pack(side="left", fill="x", expand=True)
        self._show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row, text="Mostrar", variable=self._show_var,
                       command=self._toggle_secret,
                       bg=CARD, fg=FG_DIM, selectcolor=CARD,
                       activebackground=CARD, activeforeground=FG_DIM,
                       font=(FONT, 9), bd=0, relief="flat").pack(side="left", padx=(8, 0))

        tk.Label(inner, text="Crie o app em: developer.spotify.com/dashboard",
                 font=(FONT, 9), bg=CARD, fg=FG_DARK).pack(pady=(0, 20))

        self._btn = tk.Button(
            inner, text="▶  Iniciar",
            font=(FONT, 12, "bold"), bg=GREEN, fg="#000",
            activebackground=GREEN_HV, activeforeground="#000",
            relief="flat", bd=0, cursor="hand2", padx=20, pady=10,
            command=self._start,
        )
        self._btn.pack(fill="x")

        self._status = tk.Label(inner, text="", font=(FONT, 10),
                                bg=CARD, fg=FG_DIM, wraplength=360)
        self._status.pack(pady=(12, 0))

        self._progress = ttk.Progressbar(inner, mode="indeterminate", length=360)
        self.bind("<Return>", lambda _: self._start())

    def _toggle_secret(self):
        self._secret_entry.entry.config(show="" if self._show_var.get() else "•")

    def _set_status(self, msg, color=FG_DIM):
        self._status.config(text=msg, fg=color)
        self.update_idletasks()

    # ── Iniciar ───────────────────────────────────────────────────────────────
    def _start(self):
        cid    = self._id_entry.get()
        csecret = self._secret_entry.get()
        if not cid or not csecret:
            messagebox.showwarning("Campos obrigatórios",
                                   "Preencha CLIENT_ID e CLIENT_SECRET.")
            return

        self._btn.config(state="disabled", text="Iniciando…")
        self._progress.pack(pady=(8, 0))
        self._progress.start(12)
        self._set_status("Iniciando servidor Flask…")

        threading.Thread(
            target=self._run_flask,
            args=(cid, csecret),
            daemon=True,
        ).start()

    def _run_flask(self, client_id, client_secret):
        # Seta variáveis de ambiente ANTES de importar os módulos do projeto
        os.environ["CLIENT_ID"]        = client_id
        os.environ["CLIENT_SECRET"]    = client_secret
        os.environ["REDIRECT_URI"]     = "http://127.0.0.1:5000/callback"
        os.environ["FLASK_ENV"]        = "production"
        os.environ["FLASK_SECRET_KEY"] = os.urandom(24).hex()

        try:
            # Importa o app Flask do projeto
            # (o sys.path já inclui o diretório do projeto)
            import importlib, main as flask_main  # noqa: F401
            importlib.reload(flask_main)           # garante env vars frescos
            flask_app = flask_main.app

            # Cria o servidor Werkzeug manualmente para poder desligá-lo
            from werkzeug.serving import make_server
            self._server = make_server("127.0.0.1", 5000, flask_app)
        except Exception as exc:
            self.after(0, self._set_status, f"Erro: {exc}", "#e05252")
            self.after(0, self._reset_btn)
            return

        # Aguarda o servidor estar de pé antes de abrir o browser
        import urllib.request
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

        for _ in range(40):
            time.sleep(0.3)
            try:
                urllib.request.urlopen("http://127.0.0.1:5000/", timeout=1)
                break
            except Exception:
                pass
        else:
            self.after(0, self._set_status,
                       "Servidor não respondeu. Verifique as credenciais.", "#e05252")
            self.after(0, self._reset_btn)
            return

        webbrowser.open("http://127.0.0.1:5000/")
        self.after(0, self._on_ready)

    def _on_ready(self):
        self._progress.stop()
        self._progress.pack_forget()
        self._set_status("✅  Rodando em http://127.0.0.1:5000", GREEN)
        self._btn.config(
            state="normal", text="⏹  Parar servidor",
            bg="#c0392b", activebackground="#e74c3c",
            command=self._stop,
        )

    # ── Parar ─────────────────────────────────────────────────────────────────
    def _stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._set_status("Servidor encerrado.", FG_DIM)
        self._reset_btn()

    def _reset_btn(self):
        self._btn.config(
            state="normal", text="▶  Iniciar",
            bg=GREEN, activebackground=GREEN_HV,
            command=self._start,
        )
        self._progress.stop()
        self._progress.pack_forget()

    def _center(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def destroy(self):
        if self._server:
            self._server.shutdown()
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
