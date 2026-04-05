#!/usr/bin/env python3
"""
trade_summary.py  (v2.0)
========================
Baca trade log CSV dari MT5, hitung statistik lengkap,
dan kirim summary ke Telegram. Support harian/mingguan/bulanan/all-time.

Juga include position_monitor: cek posisi open dan floating P&L.

Author  : fznrival
Version : 2.0
"""

import os, sys, csv, json, logging, requests, argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/trade_summary.log")],
)
log = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".openclaw" / "trade_config.json"

# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def send_telegram(token, chat_id, text):
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=15)
        if not resp.json().get("ok"):
            log.error("Telegram error: %s", resp.text[:200])
    except Exception as e:
        log.error("Telegram gagal: %s", e)

def _parse_dt(s):
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except:
            pass
    return None

def _f(v):
    try:
        return float(str(v).replace(",", "."))
    except:
        return 0.0

# ─────────────────────────────────────────────────────────────────────────────

def load_trades(csv_path: str) -> list:
    path = Path(csv_path)
    if not path.exists():
        log.warning("CSV tidak ditemukan: %s", csv_path)
        return []
    trades = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                trades.append({
                    "ticket":       row.get("ticket", ""),
                    "open_time":    _parse_dt(row.get("open_time", "")),
                    "close_time":   _parse_dt(row.get("close_time", "")),
                    "symbol":       row.get("symbol", "").upper(),
                    "type":         row.get("type", "").upper(),
                    "volume":       _f(row.get("volume", 0)),
                    "open_price":   _f(row.get("open_price", 0)),
                    "close_price":  _f(row.get("close_price", 0)),
                    "net_profit":   _f(row.get("net_profit", 0)),
                    "duration_min": int(_f(row.get("duration_min", 0))),
                    "session":      row.get("session", "Unknown"),
                    "comment":      row.get("comment", ""),
                })
            except Exception as e:
                log.debug("Skip row: %s", e)
    log.info("Loaded %d trades dari %s", len(trades), csv_path)
    return trades

def filter_trades(trades, period="today"):
    now = datetime.now()
    if period == "today":
        start = datetime.combine(date.today(), datetime.min.time())
    elif period == "week":
        start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), datetime.min.time())
    elif period == "month":
        start = datetime.combine(date.today().replace(day=1), datetime.min.time())
    else:
        return trades
    return [t for t in trades if t["close_time"] and start <= t["close_time"] <= now]

def _max_consec(trades, win=True):
    max_c = cur = 0
    for t in sorted(trades, key=lambda x: x["close_time"] or datetime.min):
        if (win and t["net_profit"] > 0) or (not win and t["net_profit"] < 0):
            cur += 1; max_c = max(max_c, cur)
        else:
            cur = 0
    return max_c

def calc_stats(trades, config):
    if not trades:
        return {"total": 0}
    wins    = [t for t in trades if t["net_profit"] > 0]
    losses  = [t for t in trades if t["net_profit"] < 0]
    total   = len(trades)
    winrate = len(wins) / total * 100 if total > 0 else 0
    gross_p = sum(t["net_profit"] for t in wins)
    gross_l = abs(sum(t["net_profit"] for t in losses))
    net_pnl = gross_p - gross_l
    pf      = round(gross_p / gross_l, 2) if gross_l > 0 else "∞"
    avg_win  = gross_p / len(wins)    if wins   else 0
    avg_loss = gross_l / len(losses)  if losses else 0
    rr_act   = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    # Max drawdown
    balance = config.get("account_balance", 1000)
    peak = balance; max_dd = 0; running = balance
    for t in sorted(trades, key=lambda x: x["close_time"] or datetime.min):
        running += t["net_profit"]
        if running > peak: peak = running
        dd = peak - running
        if dd > max_dd: max_dd = dd

    # Symbol & session breakdown
    sym_s = defaultdict(lambda: {"total": 0, "wins": 0, "net": 0.0})
    ses_s = defaultdict(lambda: {"total": 0, "wins": 0, "net": 0.0})
    for t in trades:
        sym_s[t["symbol"]]["total"] += 1; sym_s[t["symbol"]]["net"] += t["net_profit"]
        ses_s[t["session"]]["total"] += 1; ses_s[t["session"]]["net"] += t["net_profit"]
        if t["net_profit"] > 0:
            sym_s[t["symbol"]]["wins"] += 1; ses_s[t["session"]]["wins"] += 1

    best  = max(trades, key=lambda t: t["net_profit"])
    worst = min(trades, key=lambda t: t["net_profit"])
    durations = [t["duration_min"] for t in trades if t["duration_min"] > 0]

    return {
        "total": total, "wins": len(wins), "losses": len(losses),
        "winrate": round(winrate, 1),
        "gross_profit": round(gross_p, 2), "gross_loss": round(gross_l, 2),
        "net_pnl": round(net_pnl, 2), "profit_factor": pf,
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "rr_actual": rr_act, "max_drawdown": round(max_dd, 2),
        "max_consec_win":  _max_consec(trades, win=True),
        "max_consec_loss": _max_consec(trades, win=False),
        "best_trade": best, "worst_trade": worst,
        "avg_duration_min": round(sum(durations)/len(durations), 0) if durations else 0,
        "symbol_stats": dict(sym_s), "session_stats": dict(ses_s),
        "currency": config.get("currency", "USD"),
    }

def format_summary(stats, period, config):
    if stats.get("total", 0) == 0:
        return f"📊 *TRADING REPORT — {period.upper()}*\n\nTidak ada trade pada periode ini."

    cur = stats["currency"]
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    tz  = config.get("timezone_label", "WIB")
    period_labels = {
        "today": f"HARIAN — {date.today().strftime('%d %b %Y')}",
        "week":  "MINGGUAN — Minggu ini",
        "month": f"BULANAN — {date.today().strftime('%B %Y')}",
        "all":   "ALL TIME",
    }
    pl = period_labels.get(period, period.upper())
    pnl_e = "🟢" if stats["net_pnl"] >= 0 else "🔴"
    wr_e  = "🔥" if stats["winrate"] >= 60 else ("✅" if stats["winrate"] >= 50 else "⚠️")
    best  = stats["best_trade"]; worst = stats["worst_trade"]

    sym_lines = ""
    for sym, s in sorted(stats["symbol_stats"].items(), key=lambda x: abs(x[1]["net"]), reverse=True)[:3]:
        wr = round(s["wins"]/s["total"]*100) if s["total"] > 0 else 0
        sign = "+" if s["net"] >= 0 else ""
        sym_lines += f"  {sym}: {s['total']} trade | WR {wr}% | {sign}{s['net']:.2f} {cur}\n"

    ses_lines = ""
    for ses, s in sorted(stats["session_stats"].items(), key=lambda x: x[1]["total"], reverse=True):
        wr = round(s["wins"]/s["total"]*100) if s["total"] > 0 else 0
        ses_lines += f"  {ses}: {s['total']} trade | WR {wr}%\n"

    msg = (
        f"📈 *TRADING REPORT — {pl}*\n"
        f"🕐 _{now} {tz}_\n{'─'*30}\n\n"
        f"📊 *OVERVIEW*\n"
        f"Total Trade  : `{stats['total']}`\n"
        f"✅ Win        : `{stats['wins']}`\n"
        f"❌ Loss       : `{stats['losses']}`\n"
        f"{wr_e} Winrate     : `{stats['winrate']}%`\n\n"
        f"💰 *PROFIT & LOSS*\n"
        f"Gross Profit : `+{stats['gross_profit']} {cur}`\n"
        f"Gross Loss   : `-{stats['gross_loss']} {cur}`\n"
        f"{pnl_e} Net P&L    : `{'+' if stats['net_pnl']>=0 else ''}{stats['net_pnl']} {cur}`\n"
        f"Profit Factor: `{stats['profit_factor']}`\n\n"
        f"📐 *RISK & REWARD*\n"
        f"Avg RR Actual: `1:{stats['rr_actual']}`\n"
        f"Avg Win      : `+{stats['avg_win']} {cur}`\n"
        f"Avg Loss     : `-{stats['avg_loss']} {cur}`\n"
        f"Max Drawdown : `-{stats['max_drawdown']} {cur}`\n\n"
        f"🏆 *HIGHLIGHTS*\n"
        f"Best Trade   : `{best.get('symbol','-')} +{best.get('net_profit',0):.2f} {cur}`\n"
        f"Worst Trade  : `{worst.get('symbol','-')} {worst.get('net_profit',0):.2f} {cur}`\n"
        f"Max Con. Win : `{stats['max_consec_win']} trade`\n"
        f"Max Con. Loss: `{stats['max_consec_loss']} trade`\n"
        f"Avg Duration : `{int(stats['avg_duration_min'])} menit`\n\n"
    )
    if sym_lines: msg += f"📌 *TOP PAIRS*\n{sym_lines}\n"
    if ses_lines: msg += f"⏰ *BY SESSION*\n{ses_lines}\n"
    msg += "_Generated by OpenClaw AI + MT5 Reporter v2_"
    return msg

# ─────────────────────────────────────────────────────────────────────────────
# Position Monitor
# ─────────────────────────────────────────────────────────────────────────────

def monitor_positions(cfg, token, chat_id):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.error("MT5 tidak tersedia."); return

    magic    = cfg.get("trading", {}).get("magic_number", 2022001)
    currency = cfg.get("currency", "USD")

    if not mt5.initialize():
        log.error("Gagal konek MT5"); return

    positions = mt5.positions_get()
    now_str   = datetime.now().strftime("%d %b %Y, %H:%M WIB")

    if not positions:
        log.info("Tidak ada posisi open."); mt5.shutdown(); return

    my_pos = [p for p in positions if p.magic == magic]
    if not my_pos:
        log.info("Tidak ada posisi dari bot ini."); mt5.shutdown(); return

    total_pnl = sum(p.profit for p in my_pos)
    pnl_e = "🟢" if total_pnl >= 0 else "🔴"
    lines = [f"📊 *POSISI OPEN — {now_str}*\n{'─'*28}\n"]
    for p in my_pos:
        dir_ = "BUY 🟢" if p.type == 0 else "SELL 🔴"
        sign = "+" if p.profit >= 0 else ""
        open_t = datetime.fromtimestamp(p.time).strftime("%d/%m %H:%M")
        lines.append(
            f"📌 *{p.symbol}* — {dir_}\n"
            f"  Entry / Now : `{p.price_open}` / `{p.price_current}`\n"
            f"  SL / TP     : `{p.sl}` / `{p.tp}`\n"
            f"  Lot / P&L   : `{p.volume}` / `{sign}{p.profit:.2f} {currency}`\n"
            f"  Opened      : `{open_t}`\n"
        )
    lines.append(f"{'─'*28}\n{pnl_e} *Total Floating :* `{'+' if total_pnl>=0 else ''}{total_pnl:.2f} {currency}`")
    send_telegram(token, chat_id, "\n".join(lines))
    mt5.shutdown()

# ─────────────────────────────────────────────────────────────────────────────

def run_summary(period="today", dry_run=False):
    cfg    = load_config()
    token  = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    trades  = load_trades(cfg.get("csv_path", ""))
    filtered = filter_trades(trades, period)
    stats   = calc_stats(filtered, cfg)
    message = format_summary(stats, period, cfg)
    print("\n" + "="*50 + "\n" + message + "\n" + "="*50)
    if not dry_run:
        send_telegram(token, chat_id, message)
    return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", "-p", choices=["today","week","month","all"], default="today")
    parser.add_argument("--dry-run", "-d", action="store_true")
    parser.add_argument("--positions", action="store_true", help="Monitor posisi open saja")
    args = parser.parse_args()

    cfg = load_config()
    token = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")

    if args.positions:
        monitor_positions(cfg, token, chat_id)
    else:
        run_summary(args.period, args.dry_run)
