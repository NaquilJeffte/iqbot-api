#!/usr/bin/env python3
"""
instalar.py — Instala las dependencias y arranca el servidor
Ejecuta: python instalar.py
"""
import subprocess
import sys
import os

print("=" * 55)
print("  IQ Option Bot API — Instalador")
print("=" * 55)

paquetes = [
    "flask",
    "flask-cors",
    "requests",
    "websocket-client==0.56",
]

print("\n📦 Instalando dependencias...\n")
for paq in paquetes:
    print(f"  → {paq}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", paq, "-q"])

print("\n✅ Todo instalado correctamente.")
print("\n🚀 Iniciando servidor...\n")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.execv(sys.executable, [sys.executable, "server.py"])
