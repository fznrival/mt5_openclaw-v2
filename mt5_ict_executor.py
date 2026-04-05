#!/usr/bin/env python3
"""
mt5_ict_executor.py  (v2.0)
===========================
Full Automated ICT Trading System.

Alur lengkap:
  1. Cek Macro Time window (Eastern) — hanya trade saat macro/news
  2. Cek Silver Bullet time window — 03:00, 10:00, 14:00 ET
  3. Scan MT5: deteksi Silver Bullet (Liquidity Sweep + FVG + OTE)
  4. Kirim setup ke OpenClaw AI (Anthropic API) untuk keputusan final
  5. Jika AI approve → eksekusi order di MT5
  6. Notifikasi lengkap ke Telegram

Author  : fznrival
Version : 2.0 — Silver Bullet + Macro Time + OpenClaw AI
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime
from pathlib import Path

try:
    import MetaTrader5 as mt5
    import pandas as pd
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from ict_concepts import (
    detect_silver_bullet, check_macro_time, check_silver_bullet_window,
    get_current_session_wib, ICTScanResult, SilverBulletSetup,
    detect_mss, detect_fvg, calc_ote
)
from openclaw_ai import OpenClawAI, AIDecision, format_ai_decision_telegram

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/ict_trade.log"),
    ],
)
log = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".openclaw" / "trade_config.json"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error("Config tidak ditemukan: %s", CONFIG_PATH)
        log.error("Jalankan: cp trade_config.example.json ~/.openclaw/trade_config.json")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def send_telegram(token: str, chat_id: str, text: str):
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        log.warning("Telegram token belum dikonfigurasi.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id, "text": text, "parse_mode": "Markdown"
        }, timeout=15)
        if not resp.json().get("ok"):
            log.error("Telegram error: %s", resp.text[:200])
    except Exception as e:
        log.error("Gagal kirim Telegram: %s", e)


def count_trades_today(magic: int) -> int:
    if not MT5_AVAILABLE:
        return 0
    positions = mt5.positions_get()
    if not positions:
        return 0
    today = datetime.now().date()
    return sum(
        1 for p in positions
        if p.magic == magic and datetime.fromtimestamp(p.time).date() == today
    )


TF_MAP = {5: "TIMEFRAME_M5", 15: "TIMEFRAME_M15", 30: "TIMEFRAME_M30",
          60: "TIMEFRAME_H1", 240: "TIMEFRAME_H4"}

# ─────────────────────────────────────────────────────────────────────────────
# Per-Symbol Scanner
# ─────────────────────────────────────────────────────────────────────────────

def scan_symbol(
    symbol: str,
    tconf: dict,
    scan_meta: dict,
    ai_engine: OpenClawAI,
    token: str,
    chat_id: str,
    account_balance: float,
    currency: str,
    demo_mode: bool,
    trades_today: int,
) -> bool:
    """
    Scan satu symbol, minta keputusan AI, eksekusi jika disetujui.
    Return True jika trade dieksekusi.
    """
    if not MT5_AVAILABLE:
        log.error("MT5 tidak tersedia.")
        return False

    ict_cfg  = tconf.get("ict", {})
    tf_int   = tconf.get("timeframe", 15)
    TIMEFRAME = getattr(mt5, TF_MAP.get(tf_int, "TIMEFRAME_M15"))
    lookback  = ict_cfg.get("swing_lookback", 20)
    lot       = tconf.get("lot_size", 0.01)
    rr        = tconf.get("risk_reward_ratio", 2.0)
    magic     = tconf.get("magic_number", 2022001)
    slippage  = tconf.get("slippage_dev", 20)
    sl_buf    = ict_cfg.get("sl_buffer_pips", 5.0) * 0.0001
    max_tr    = tconf.get("max_trades_per_day", 2)

    if not mt5.symbol_select(symbol, True):
        log.warning("Symbol %s tidak tersedia di broker, skip.", symbol)
        return False

    # Ambil OHLCV
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, lookback + 20)
    if rates is None or len(rates) < lookback + 5:
        log.warning("%s: Data tidak cukup (%s candle).", symbol, len(rates) if rates else 0)
        return False

    highs  = [r["high"]  for r in rates]
    lows   = [r["low"]   for r in rates]
    closes = [r["close"] for r in rates]

    # ── Silver Bullet Detection ───────────────────────────────────────────
    sb = detect_silver_bullet(
        highs, lows, closes, ict_cfg,
        window_label=scan_meta.get("sb_window_label", "")
    )

    # ── Build ICT Scan Result ─────────────────────────────────────────────
    scan = ICTScanResult(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        session=scan_meta["session"],
        macro_active=scan_meta["macro_active"],
        sb_window_active=scan_meta["sb_window_active"],
        macro_label=scan_meta.get("macro_label", ""),
        sb_window_label=scan_meta.get("sb_window_label", ""),
        silver_bullet=sb,
        basic_setup=None,
        should_trade=False,
        reason="",
    )

    if sb:
        log.info("%s: Silver Bullet ditemukan! Confidence=%.0f%% | %s",
                 symbol, sb.confidence * 100, sb.direction)
    else:
        log.info("%s: Tidak ada Silver Bullet setup.", symbol)

    # ── Minta Keputusan AI ────────────────────────────────────────────────
    decision = ai_engine.decide_trade(
        scan=scan,
        sb=sb,
        trades_today=trades_today,
        account_balance=account_balance,
        currency=currency,
    )

    # Kirim notifikasi AI decision ke Telegram
    ai_msg = format_ai_decision_telegram(symbol, scan, sb, decision, lot, rr)
    send_telegram(token, chat_id, ai_msg)

    # ── Eksekusi jika AI approve ──────────────────────────────────────────
    if decision.action != AIDecision.EXECUTE:
        log.info("%s: AI tidak approve (%s). Skip.", symbol, decision.action)
        return False

    if not sb:
        log.warning("%s: AI EXECUTE tapi tidak ada Silver Bullet setup. Batalkan untuk safety.", symbol)
        send_telegram(token, chat_id,
                      f"⚠️ *Safety Override*\n`{symbol}`: AI EXECUTE tapi setup tidak valid. Trade dibatalkan.")
        return False

    if trades_today >= max_tr:
        log.info("%s: Max trades per hari sudah tercapai (%d). Skip.", symbol, max_tr)
        return False

    # ── Demo atau Live ────────────────────────────────────────────────────
    if demo_mode:
        log.info("[DEMO] Tidak ada order dikirim ke MT5.")
        return True

    # LIVE ORDER
    tick     = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    digits   = sym_info.digits if sym_info else 5

    if sb.direction == "bullish":
        order_type = mt5.ORDER_TYPE_BUY
        price      = tick.ask
        sl         = round(sb.swing_low - sl_buf, digits)
        risk       = abs(price - sl)
        tp         = round(price + risk * rr, digits)
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price      = tick.bid
        sl         = round(sb.swing_high + sl_buf, digits)
        risk       = abs(price - sl)
        tp         = round(price - risk * rr, digits)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       float(lot),
        "type":         order_type,
        "price":        price,
        "sl":           sl,
        "tp":           tp,
        "deviation":    slippage,
        "magic":        magic,
        "comment":      "ICT_SilverBullet_OpenClaw",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        msg = f"❌ *Order Gagal*\n`{symbol}` — order_send() return None\nError: {mt5.last_error()}"
        log.error(msg)
        send_telegram(token, chat_id, msg)
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        dir_emoji = "🟢 BUY" if sb.direction == "bullish" else "🔴 SELL"
        msg = (
            f"⚡ *TRADE EXECUTED — Silver Bullet*\n\n"
            f"📌 Symbol  : `{symbol}`\n"
            f"🛒 Action  : {dir_emoji}\n"
            f"💰 Entry   : `{price}`\n"
            f"🛑 SL      : `{sl}`\n"
            f"🎯 TP      : `{tp}`\n"
            f"📐 RR      : `1:{rr}`\n"
            f"⚖️ Lot     : `{lot}`\n"
            f"🎫 Ticket  : `{result.order}`\n\n"
            f"🧠 AI conf : `{decision.confidence:.0%}`\n"
            f"✅ Setup   : Sweep → FVG → OTE Confirmed\n"
            f"🕐 _{datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC_"
        )
        log.info("ORDER SUKSES: %s %s ticket=%s", symbol, sb.direction, result.order)
        send_telegram(token, chat_id, msg)
        return True
    else:
        msg = (
            f"❌ *Order Gagal*\n`{symbol}`\n"
            f"Retcode: `{result.retcode}`\n"
            f"Message: `{result.comment}`"
        )
        log.error("ORDER GAGAL: %s retcode=%s %s", symbol, result.retcode, result.comment)
        send_telegram(token, chat_id, msg)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Runner
# ─────────────────────────────────────────────────────────────────────────────

def run():
    cfg     = load_config()
    tconf   = cfg.get("trading", {})
    ai_cfg  = cfg.get("openclaw_ai", {})
    token   = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    api_key = cfg.get("anthropic_api_key", "")
    symbols = tconf.get("symbols", ["USTECm"])
    demo    = tconf.get("demo_mode", True)
    balance = cfg.get("account_balance", 1000.0)
    currency = cfg.get("currency", "USD")
    magic   = tconf.get("magic_number", 2022001)
    max_tr  = tconf.get("max_trades_per_day", 2)

    log.info("=== ICT Silver Bullet Scanner v2.0 ===")
    log.info("Demo mode: %s | Symbols: %s", demo, symbols)

    # ── Step 1: Cek Macro Time ────────────────────────────────────────────
    macro_cfgs   = tconf.get("macro_times_eastern", [])
    macro_window = tconf.get("macro_window_minutes", 60)
    macro_active, macro_label = check_macro_time(macro_cfgs, macro_window)

    # ── Step 2: Cek Silver Bullet Window ─────────────────────────────────
    sb_cfgs = tconf.get("silver_bullet_windows_eastern", [])
    sb_active, sb_label = check_silver_bullet_window(sb_cfgs)

    # Harus salah satu aktif untuk trade
    if not macro_active and not sb_active:
        log.info("Di luar Macro Time dan Silver Bullet window. Scanner berhenti.")
        log.info("Macro windows : %s", [m["time"] for m in macro_cfgs])
        log.info("SB windows    : %s", [(s["start"], s["end"]) for s in sb_cfgs])
        return

    if macro_active:
        log.info("✅ MACRO TIME AKTIF: %s", macro_label)
    if sb_active:
        log.info("✅ SILVER BULLET WINDOW AKTIF: %s", sb_label)

    session = get_current_session_wib(tconf.get("killzone_wib", {}))
    log.info("Session: %s", session)

    # ── Step 3: Init MT5 ──────────────────────────────────────────────────
    if not MT5_AVAILABLE:
        log.error("MetaTrader5 tidak tersedia. Jalankan via: WINEPREFIX=~/.wine_mt5 wine python %s", __file__)
        return

    if not mt5.initialize():
        err = f"❌ Gagal konek MT5: {mt5.last_error()}"
        log.error(err)
        send_telegram(token, chat_id, err)
        return

    account = mt5.account_info()
    if account:
        balance = account.balance
        currency = account.currency
        log.info("MT5 Connected | Login: %s | Balance: %.2f %s",
                 account.login, balance, currency)

    # ── Step 4: Init OpenClaw AI ──────────────────────────────────────────
    if not api_key or api_key == "YOUR_ANTHROPIC_API_KEY_HERE":
        log.error("Anthropic API key belum dikonfigurasi!")
        mt5.shutdown()
        return

    ai_engine = OpenClawAI(
        api_key=api_key,
        model=ai_cfg.get("model", "claude-sonnet-4-20250514"),
        max_tokens=ai_cfg.get("max_tokens", 1024),
        confidence_threshold=ai_cfg.get("confidence_threshold", 0.75),
    )

    # ── Step 5: Cek trades hari ini ───────────────────────────────────────
    trades_today = count_trades_today(magic)
    if trades_today >= max_tr:
        log.info("Max trades per hari (%d) sudah tercapai. Scanner berhenti.", max_tr)
        mt5.shutdown()
        return

    log.info("Trades hari ini: %d/%d", trades_today, max_tr)

    # ── Step 6: Scan semua symbol ─────────────────────────────────────────
    scan_meta = {
        "session":        session,
        "macro_active":   macro_active,
        "macro_label":    macro_label,
        "sb_window_active": sb_active,
        "sb_window_label":  sb_label,
    }

    executed = 0
    for symbol in symbols:
        if trades_today + executed >= max_tr:
            log.info("Max trades tercapai, berhenti scan.")
            break
        log.info("─── Scanning %s ───", symbol)
        try:
            ok = scan_symbol(
                symbol, tconf, scan_meta, ai_engine,
                token, chat_id, balance, currency, demo, trades_today + executed
            )
            if ok:
                executed += 1
        except Exception as e:
            log.error("Error scan %s: %s", symbol, e, exc_info=True)

    log.info("Scan selesai. Dieksekusi: %d/%d symbol.", executed, len(symbols))
    mt5.shutdown()


if __name__ == "__main__":
    run()
