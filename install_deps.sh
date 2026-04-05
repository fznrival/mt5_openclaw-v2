#!/bin/bash

echo "Memulai instalasi dependensi Python di dalam Wine untuk MT5 OpenClaw V2..."

# 1. Pastikan pip di dalam Wine sudah versi terbaru
WINEPREFIX=~/.wine_mt5 wine python -m pip install --upgrade pip

# 2. Instal library inti untuk algoritma ICT dan MT5
WINEPREFIX=~/.wine_mt5 wine python -m pip install MetaTrader5 pandas

# 3. Instal library untuk komunikasi API eksternal (Telegram & OpenClaw AI)
WINEPREFIX=~/.wine_mt5 wine python -m pip install requests anthropic

# 4. Instal library untuk manajemen zona waktu (Macro Time / EST ke WIB)
WINEPREFIX=~/.wine_mt5 wine python -m pip install pytz

echo "Instalasi selesai! Sistem siap menjalankan mt5_ict_executor.py"