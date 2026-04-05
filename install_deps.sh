#!/bin/bash

echo "Memulai instalasi dependensi Python di dalam Wine untuk MT5 OpenClaw V2..."

export WINEPREFIX="$HOME/.wine_mt5"

echo "Mencari lokasi instalasi Python di dalam Wine..."
# Mencari python.exe secara otomatis dan mengambil jalur pertamanya
PYTHON_EXE=$(find "$WINEPREFIX/drive_c" -name "python.exe" 2>/dev/null | head -n 1)

if [ -z "$PYTHON_EXE" ]; then
    echo "❌ python.exe sama sekali tidak ditemukan. Anda belum menginstal Python di dalam Wine."
    exit 1
fi

PYTHON_DIR=$(dirname "$PYTHON_EXE")
echo "✅ Python ditemukan di: $PYTHON_DIR"

# Pindah ke folder yang sudah ditemukan otomatis
cd "$PYTHON_DIR" || exit 1

# Eksekusi instalasi
wine python.exe -m pip install --upgrade pip
wine python.exe -m pip install MetaTrader5 pandas
wine python.exe -m pip install requests anthropic
wine python.exe -m pip install pytz

# Kembali ke folder awal
cd - > /dev/null

echo "🎉 Instalasi selesai! Sistem siap menjalankan mt5_ict_executor.py"
