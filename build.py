#!/usr/bin/env python3
"""
build.py — Gera o SpotifyMemoryCalendar.exe com PyInstaller.
Execute: python build.py
"""
import subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))

print("=" * 60)
print("  Spotify Memory Calendar — Build")
print("=" * 60)

# Dependências mínimas
deps = [
    "pyinstaller",
    "flask",
    "spotipy",
    "python-dotenv",
    "requests",
]
print("\n[1/2] Instalando dependências...")
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "--quiet"] + deps
)

print("\n[2/2] Compilando o executável...")
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "--clean", "spotify_calendar.spec"],
    cwd=HERE,
)

if result.returncode == 0:
    exe_path = os.path.join(HERE, "dist", "SpotifyMemoryCalendar.exe")
    print("\n" + "=" * 60)
    print("  ✅  Build concluído!")
    print(f"  📦  Arquivo: {exe_path}")
    print("=" * 60)
else:
    print("\n❌  Erro durante o build. Verifique as mensagens acima.")
    sys.exit(1)
