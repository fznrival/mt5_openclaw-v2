# 🦞 MT5 + OpenClaw AI — Full ICT Silver Bullet System v2.0

**Full Automated Trading** berbasis **ICT 2022 Silver Bullet** + **Macro Time** + **OpenClaw AI (Anthropic)** di Linux.

---

## ✅ Fitur Lengkap v2.0

| Fitur | Status |
|-------|--------|
| Full Automated Trading (SL/TP otomatis) | ✅ |
| ICT 2022 — Liquidity Sweep detection | ✅ |
| ICT 2022 — Fair Value Gap (FVG) | ✅ |
| ICT 2022 — OTE (Fib 0.62–0.79) | ✅ |
| ICT Silver Bullet (3-step: Sweep→FVG→OTE) | ✅ |
| Only Macro Time filter (ET spesifik) | ✅ |
| Silver Bullet Time Windows (03:00/10:00/14:00 ET) | ✅ |
| OpenClaw AI via Anthropic API sebagai otak | ✅ |
| Telegram: notif signal + execution + daily report | ✅ |
| Demo mode (aman untuk testing) | ✅ |
| Backtest engine | ✅ |

---

## 📁 Struktur File

```
mt5_openclaw/
├── python/
│   ├── ict_concepts.py         ← ICT library: FVG, MSS, Silver Bullet, Macro Time
│   ├── openclaw_ai.py          ← OpenClaw AI: Anthropic API decision engine
│   ├── mt5_ict_executor.py     ← Main runner: scan + AI decide + MT5 execute
│   ├── trade_summary.py        ← Summary + position monitor
│   └── backtest_ict.py         ← Backtesting engine
├── mql5/
│   └── TradeExporter.mq5       ← EA MT5: export trade ke CSV
├── openclaw_skill/
│   └── ict-silver-bullet.skill.json
├── trade_config.example.json   ← Config lengkap dengan semua parameter
├── setup_mt5_wine.sh           ← Install Wine + MT5
├── install_deps.sh             ← Install Python dependencies
└── setup_cron.sh               ← Setup semua jadwal otomatis
```

---

## 🚀 Quick Start

```bash
# 1. Install Wine + MT5
bash ~/mt5_openclaw-v2/setup_mt5_wine.sh

# 2. Install dependencies
bash ~/mt5_openclaw-v2/install_deps.sh

# 3. Buat config
cp ~/mt5_openclaw-v2/trade_config.example.json ~/.openclaw/trade_config.json
nano ~/.openclaw/trade_config.json
# Isi: telegram_bot_token, telegram_chat_id, anthropic_api_key

# 4. Test scanner (demo mode)
cd ~/mt5_openclaw/python
WINEPREFIX=~/.wine_mt5 wine python mt5_ict_executor.py

# 5. Setup jadwal otomatis
bash ~/mt5_openclaw-v2/setup_cron.sh
```

---

## 🧠 Alur Kerja Silver Bullet

```
Setiap 15 menit:
│
├─ [1] Cek Macro Time (Eastern)?
│       08:30 / 10:00 / 14:00 / 14:30 / 15:30 ET
│       ATAU Silver Bullet Window: 03:00-04:00 / 10:00-11:00 / 14:00-15:00 ET
│       ↓ Jika tidak aktif → BERHENTI (tidak trade di luar macro time)
│
├─ [2] Scan semua symbol di config
│
├─ [3] Deteksi ICT Silver Bullet (3 step):
│       Step 1: Liquidity Sweep — harga grab old high/low
│       Step 2: Displacement candle → FVG terbentuk
│       Step 3: Price retraces ke FVG → harga masuk OTE 0.62–0.79
│       ↓ Jika tidak ada → WAIT
│
├─ [4] Kirim ke OpenClaw AI (Anthropic API):
│       Claude analisis: setup valid? risk OK? session tepat?
│       → EXECUTE / WAIT / REJECT + reasoning
│
└─ [5] Jika EXECUTE:
        → Send order ke MT5 (BUY/SELL + SL + TP)
        → Notif Telegram lengkap
```

---

## ⚙️ Macro Time (Eastern → WIB konversi)

| Waktu ET | WIB (DST) | Label |
|----------|-----------|-------|
| 08:30 ET | 19:30 WIB | NFP / CPI / PPI |
| 10:00 ET | 21:00 WIB | ISM / Consumer Confidence |
| 14:00 ET | 01:00 WIB | FOMC Minutes |
| 14:30 ET | 01:30 WIB | Fed Chair Speech |
| 15:30 ET | 02:30 WIB | PM Macro Window |

## 🎯 Silver Bullet Windows (Eastern → WIB)

| Window ET | WIB | Label |
|-----------|-----|-------|
| 03:00–04:00 | 14:00–15:00 | London SB Window |
| 10:00–11:00 | 21:00–22:00 | AM SB Window |
| 14:00–15:00 | 01:00–02:00 | PM SB Window |

---

## 💬 Perintah via Telegram ke OpenClaw

| Perintah | Aksi |
|----------|------|
| `scan market` | Jalankan ICT scanner manual |
| `cek sinyal` | Scan semua symbol |
| `cek posisi` | Status posisi open + floating |
| `laporan trading hari ini` | Daily report |
| `laporan minggu ini` | Weekly report |

---

## ⚠️ PENTING — Selalu mulai dari demo_mode: true

1. Set `"demo_mode": true` di config → AI hanya kirim sinyal, tidak eksekusi
2. Pantau sinyal di Telegram minimal 2 minggu
3. Bandingkan dengan chart manual
4. Setelah winrate > 55% di demo → ubah ke `false` dengan lot 0.01
