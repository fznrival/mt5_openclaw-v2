#!/usr/bin/env python3
"""
ict_concepts.py
===============
Library lengkap ICT 2022 concepts:
  - Fair Value Gap (FVG)
  - Market Structure Shift (MSS)
  - Optimal Trade Entry (OTE)
  - Liquidity Sweep detection
  - Silver Bullet setup (3-step)
  - Macro Time filter (Eastern)
  - Silver Bullet Time Windows

Author  : fznrival
Version : 2.0 — Full ICT 2022
"""

from datetime import datetime, time as dtime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
import math

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FVG:
    type:    str        # 'bullish' | 'bearish'
    top:     float
    bottom:  float
    mid:     float
    size:    float
    candle_idx: int     # index candle tengah (displacement)
    filled:  bool = False

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class SwingPoint:
    type:  str          # 'high' | 'low'
    price: float
    idx:   int
    swept: bool = False


@dataclass
class LiquiditySweep:
    direction: str      # 'bullish_sweep' (sweep low) | 'bearish_sweep' (sweep high)
    swept_level: float
    sweep_candle_idx: int
    displacement_confirmed: bool = False


@dataclass
class SilverBulletSetup:
    """
    ICT Silver Bullet: 3-step pattern
    1. Liquidity sweep (grab old high/low)
    2. Displacement candle → FVG terbentuk
    3. Price retraces ke FVG → Entry di OTE (0.62-0.79)
    """
    direction:   str            # 'bullish' | 'bearish'
    sweep:       LiquiditySweep
    fvg:         FVG
    ote_lower:   float
    ote_upper:   float
    swing_high:  float
    swing_low:   float
    entry_price: Optional[float] = None
    sl:          Optional[float] = None
    tp:          Optional[float] = None
    confidence:  float = 0.0
    window_label: str = ""


@dataclass
class MacroEvent:
    time_eastern: str   # "08:30"
    label:        str
    window_start: datetime
    window_end:   datetime
    active:       bool = False


@dataclass
class ICTScanResult:
    symbol:          str
    timestamp:       datetime
    session:         str
    macro_active:    bool
    sb_window_active: bool
    macro_label:     str
    sb_window_label: str
    silver_bullet:   Optional[SilverBulletSetup]
    basic_setup:     Optional[dict]   # fallback jika SB tidak ada
    should_trade:    bool
    reason:          str

# ─────────────────────────────────────────────────────────────────────────────
# Macro Time Filter
# ─────────────────────────────────────────────────────────────────────────────

EASTERN_UTC_OFFSET_STANDARD = -5   # EST
EASTERN_UTC_OFFSET_DST      = -4   # EDT (Mar-Nov)

def _is_dst(dt: datetime) -> bool:
    """Cek apakah tanggal dalam DST (simplifikasi: Mar-Nov)."""
    return 3 <= dt.month <= 11

def _eastern_to_utc(et_str: str, ref_date: datetime) -> datetime:
    """Konversi jam Eastern 'HH:MM' ke UTC datetime pada tanggal ref_date."""
    h, m = map(int, et_str.split(":"))
    offset = EASTERN_UTC_OFFSET_DST if _is_dst(ref_date) else EASTERN_UTC_OFFSET_STANDARD
    et_dt = ref_date.replace(hour=h, minute=m, second=0, microsecond=0)
    return et_dt - timedelta(hours=offset)

def _utc_to_wib(utc_dt: datetime) -> datetime:
    """Konversi UTC ke WIB (UTC+7)."""
    return utc_dt + timedelta(hours=7)

def check_macro_time(macro_configs: list, window_minutes: int = 60) -> tuple[bool, str]:
    """
    Cek apakah sekarang dalam Macro Time window.
    Returns: (is_active, label)
    """
    now_utc = datetime.utcnow()
    today   = now_utc.date()
    ref     = datetime(today.year, today.month, today.day)

    for mc in macro_configs:
        macro_utc = _eastern_to_utc(mc["time"], ref)
        window_start = macro_utc
        window_end   = macro_utc + timedelta(minutes=window_minutes)
        if window_start <= now_utc <= window_end:
            wib_str = _utc_to_wib(macro_utc).strftime("%H:%M")
            return True, f"{mc['label']} ({mc['time']} ET / {wib_str} WIB)"

    return False, ""


def check_silver_bullet_window(sb_configs: list) -> tuple[bool, str]:
    """
    Cek apakah sekarang dalam Silver Bullet time window.
    SB Windows (Eastern): 03:00-04:00, 10:00-11:00, 14:00-15:00
    Returns: (is_active, label)
    """
    now_utc = datetime.utcnow()
    today   = now_utc.date()
    ref     = datetime(today.year, today.month, today.day)

    for sb in sb_configs:
        start_utc = _eastern_to_utc(sb["start"], ref)
        end_utc   = _eastern_to_utc(sb["end"],   ref)
        if start_utc <= now_utc <= end_utc:
            start_wib = _utc_to_wib(start_utc).strftime("%H:%M")
            end_wib   = _utc_to_wib(end_utc).strftime("%H:%M")
            return True, f"{sb['label']} ({start_wib}-{end_wib} WIB)"

    return False, ""


def get_current_session_wib(killzone_cfg: dict) -> str:
    """Deteksi session berdasarkan jam WIB sekarang."""
    now_utc = datetime.utcnow()
    now_wib = now_utc + timedelta(hours=7)
    now_t   = dtime(now_wib.hour, now_wib.minute)

    def t(s):
        h, m = map(int, s.split(":"))
        return dtime(h, m)

    if t(killzone_cfg["asia_start"]) <= now_t <= t(killzone_cfg["asia_end"]):
        return "Asia-Killzone"
    if t(killzone_cfg["london_start"]) <= now_t <= t(killzone_cfg["london_end"]):
        return "London-Killzone"
    if t(killzone_cfg["ny_start"]) <= now_t <= t(killzone_cfg["ny_end"]):
        return "NY-Killzone"
    return "Off-Session"


# ─────────────────────────────────────────────────────────────────────────────
# Swing Point Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_swing_points(highs: list, lows: list, lookback: int = 5) -> list[SwingPoint]:
    """
    Deteksi swing high dan swing low menggunakan pivot point method.
    Swing High : high[i] > semua high di kiri dan kanan (dalam lookback)
    Swing Low  : low[i] < semua low di kiri dan kanan (dalam lookback)
    """
    swings = []
    n = len(highs)
    for i in range(lookback, n - lookback):
        # Swing High
        if all(highs[i] >= highs[j] for j in range(i - lookback, i + lookback + 1) if j != i):
            swings.append(SwingPoint("high", highs[i], i))
        # Swing Low
        if all(lows[i] <= lows[j] for j in range(i - lookback, i + lookback + 1) if j != i):
            swings.append(SwingPoint("low", lows[i], i))

    return sorted(swings, key=lambda s: s.idx)


def get_recent_swing_hl(swings: list[SwingPoint], n_recent: int = 3) -> tuple[float, float]:
    """Ambil swing high dan swing low terbaru dari list swings."""
    recent_highs = [s for s in swings if s.type == "high"][-n_recent:]
    recent_lows  = [s for s in swings if s.type == "low"][-n_recent:]
    sh = max(s.price for s in recent_highs) if recent_highs else 0
    sl = min(s.price for s in recent_lows)  if recent_lows  else 0
    return sh, sl


# ─────────────────────────────────────────────────────────────────────────────
# Liquidity Sweep Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_liquidity_sweep(
    highs: list, lows: list, closes: list,
    swings: list[SwingPoint],
    lookback: int = 10,
    displacement_body_pct: float = 0.7
) -> Optional[LiquiditySweep]:
    """
    Deteksi Liquidity Sweep pada candle-candle terbaru.

    Bullish Sweep: Harga turun ke bawah swing low sebelumnya
                   (grab sell-side liquidity), lalu CLOSE di atas low tersebut
                   → displacement bullish (candle besar naik)

    Bearish Sweep: Harga naik ke atas swing high sebelumnya
                   (grab buy-side liquidity), lalu CLOSE di bawah high tersebut
                   → displacement bearish (candle besar turun)
    """
    if len(closes) < 4 or not swings:
        return None

    opens  = []  # akan di-pass terpisah jika butuh, skip untuk sekarang

    recent_highs = sorted([s for s in swings if s.type == "high"], key=lambda s: s.idx)
    recent_lows  = sorted([s for s in swings if s.type == "low"],  key=lambda s: s.idx)

    if not recent_highs or not recent_lows:
        return None

    prev_swing_high = recent_highs[-1].price if recent_highs else None
    prev_swing_low  = recent_lows[-1].price  if recent_lows  else None

    n = len(closes)
    # Cek 3 candle terakhir untuk sweep
    for i in range(max(1, n - 3), n):
        candle_range = highs[i] - lows[i]
        if candle_range == 0:
            continue

        # ── Bullish Sweep ───────────────────────────────────────────────
        if prev_swing_low and lows[i] < prev_swing_low:
            # Harga sempat ke bawah swing low (grab sell-side liquidity)
            # Tapi close di atas swing low (rejection)
            if closes[i] > prev_swing_low:
                # Verifikasi displacement: body candle besar (bullish)
                candle_body = abs(closes[i] - lows[i])
                if candle_body / candle_range >= displacement_body_pct:
                    return LiquiditySweep(
                        direction="bullish_sweep",
                        swept_level=prev_swing_low,
                        sweep_candle_idx=i,
                        displacement_confirmed=True,
                    )

        # ── Bearish Sweep ───────────────────────────────────────────────
        if prev_swing_high and highs[i] > prev_swing_high:
            # Harga ke atas swing high (grab buy-side liquidity)
            # Tapi close di bawah swing high (rejection)
            if closes[i] < prev_swing_high:
                candle_body = abs(highs[i] - closes[i])
                if candle_body / candle_range >= displacement_body_pct:
                    return LiquiditySweep(
                        direction="bearish_sweep",
                        swept_level=prev_swing_high,
                        sweep_candle_idx=i,
                        displacement_confirmed=True,
                    )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fair Value Gap (FVG)
# ─────────────────────────────────────────────────────────────────────────────

def detect_fvg(
    highs: list, lows: list,
    start_idx: int = None,
    min_pips: float = 5.0
) -> Optional[FVG]:
    """
    Deteksi FVG (3-candle pattern) mulai dari start_idx ke depan.
    Jika start_idx None, scan dari candle ke-4 terakhir.

    Bullish FVG : low[i+2] > high[i]   → gap antara candle i dan i+2
    Bearish FVG : high[i+2] < low[i]   → gap antara candle i dan i+2
    """
    n = len(highs)
    pip = min_pips * 0.0001

    scan_from = start_idx if start_idx is not None else max(0, n - 5)

    for i in range(scan_from, n - 2):
        c1_high = highs[i]
        c1_low  = lows[i]
        c3_high = highs[i + 2]
        c3_low  = lows[i + 2]

        # Bullish FVG
        if c3_low > c1_high and (c3_low - c1_high) >= pip:
            mid = (c3_low + c1_high) / 2
            return FVG(
                type="bullish",
                top=c3_low,
                bottom=c1_high,
                mid=mid,
                size=c3_low - c1_high,
                candle_idx=i + 1,
            )

        # Bearish FVG
        if c3_high < c1_low and (c1_low - c3_high) >= pip:
            mid = (c1_low + c3_high) / 2
            return FVG(
                type="bearish",
                top=c1_low,
                bottom=c3_high,
                mid=mid,
                size=c1_low - c3_high,
                candle_idx=i + 1,
            )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Optimal Trade Entry (OTE)
# ─────────────────────────────────────────────────────────────────────────────

def calc_ote(
    swing_high: float, swing_low: float, direction: str,
    fib_low: float = 0.62, fib_high: float = 0.79
) -> tuple[float, float]:
    """
    Hitung OTE zone menggunakan Fibonacci retracement.
    Bullish OTE : retracement dari swing_high (0.62-0.79 dari atas ke bawah)
    Bearish OTE : retracement dari swing_low  (0.62-0.79 dari bawah ke atas)
    """
    rng = swing_high - swing_low
    if direction == "bullish":
        # Retracement: harga turun dari swing_high
        ote_upper = swing_high - rng * fib_low    # 0.62 level
        ote_lower = swing_high - rng * fib_high   # 0.79 level
    else:
        # Retracement: harga naik dari swing_low
        ote_lower = swing_low + rng * fib_low
        ote_upper = swing_low + rng * fib_high
    return ote_lower, ote_upper


# ─────────────────────────────────────────────────────────────────────────────
# Silver Bullet Setup (Main function)
# ─────────────────────────────────────────────────────────────────────────────

def detect_silver_bullet(
    highs: list, lows: list, closes: list,
    ict_cfg: dict,
    window_label: str = ""
) -> Optional[SilverBulletSetup]:
    """
    Deteksi full ICT Silver Bullet setup:

    Step 1: Liquidity Sweep (grab old high/low)
    Step 2: Displacement candle → FVG terbentuk SETELAH sweep
    Step 3: Current price di dalam OTE zone (0.62-0.79 retracement)

    Hanya valid jika ketiga kondisi terpenuhi.
    """
    if len(closes) < 20:
        return None

    fib_low  = ict_cfg.get("ote_fib_low", 0.62)
    fib_high = ict_cfg.get("ote_fib_high", 0.79)
    fvg_pips = ict_cfg.get("fvg_min_pips", 5.0)
    lq_back  = ict_cfg.get("liquidity_lookback", 10)
    displace_pct = ict_cfg.get("displacement_body_pct", 0.7)
    sw_back  = ict_cfg.get("swing_lookback", 20)
    sl_buf   = ict_cfg.get("sl_buffer_pips", 5.0) * 0.0001

    # ── Step 1: Deteksi Swing Points ──────────────────────────────────────
    swings = detect_swing_points(highs, lows, lookback=min(5, len(highs) // 4))
    if not swings:
        return None

    # ── Step 2: Deteksi Liquidity Sweep ──────────────────────────────────
    sweep = detect_liquidity_sweep(
        highs, lows, closes, swings,
        lookback=lq_back,
        displacement_body_pct=displace_pct
    )
    if not sweep:
        return None

    direction = "bullish" if sweep.direction == "bullish_sweep" else "bearish"
    sweep_idx = sweep.sweep_candle_idx

    # ── Step 3: FVG setelah displacement candle ───────────────────────────
    # FVG harus terbentuk SETELAH sweep candle (atau bersamaan)
    fvg = detect_fvg(highs, lows, start_idx=max(0, sweep_idx - 2), min_pips=fvg_pips)
    if not fvg:
        return None

    # FVG harus searah dengan sweep
    if fvg.type != direction:
        return None

    # ── Step 4: OTE Zone ──────────────────────────────────────────────────
    window = sw_back
    swing_highs = highs[-window:]
    swing_lows  = lows[-window:]
    swing_high  = max(swing_highs)
    swing_low   = min(swing_lows)

    ote_lower, ote_upper = calc_ote(swing_high, swing_low, direction, fib_low, fib_high)
    current_price = closes[-1]

    in_ote = ote_lower <= current_price <= ote_upper
    if not in_ote:
        return None

    # ── Step 5: Hitung SL / TP ────────────────────────────────────────────
    rr = 2.0  # akan di-override dari config di executor
    if direction == "bullish":
        entry = current_price
        sl    = round(swing_low - sl_buf, 5)
        risk  = abs(entry - sl)
        tp    = round(entry + risk * rr, 5)
    else:
        entry = current_price
        sl    = round(swing_high + sl_buf, 5)
        risk  = abs(entry - sl)
        tp    = round(entry - risk * rr, 5)

    # ── Step 6: Confidence score ──────────────────────────────────────────
    confidence = 0.5
    if sweep.displacement_confirmed:
        confidence += 0.2
    if fvg.size > fvg_pips * 2 * 0.0001:
        confidence += 0.1
    fib_mid = (fib_low + fib_high) / 2
    if direction == "bullish":
        price_in_fib = (swing_high - current_price) / (swing_high - swing_low) if (swing_high - swing_low) > 0 else 0
    else:
        price_in_fib = (current_price - swing_low) / (swing_high - swing_low) if (swing_high - swing_low) > 0 else 0
    if abs(price_in_fib - fib_mid) < 0.05:
        confidence += 0.2   # harga dekat midpoint OTE = lebih bagus

    return SilverBulletSetup(
        direction=direction,
        sweep=sweep,
        fvg=fvg,
        ote_lower=ote_lower,
        ote_upper=ote_upper,
        swing_high=swing_high,
        swing_low=swing_low,
        entry_price=entry,
        sl=sl,
        tp=tp,
        confidence=round(confidence, 2),
        window_label=window_label,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MSS (Market Structure Shift) — sebagai fallback / konfirmasi tambahan
# ─────────────────────────────────────────────────────────────────────────────

def detect_mss(closes: list, highs: list, lows: list, lookback: int = 5) -> Optional[str]:
    """
    Market Structure Shift:
    Bullish MSS : close terbaru break di atas swing high lookback candle sebelumnya
    Bearish MSS : close terbaru break di bawah swing low lookback candle sebelumnya
    """
    if len(closes) < lookback + 2:
        return None
    prev_highs = highs[-(lookback + 1):-1]
    prev_lows  = lows[-(lookback + 1):-1]
    if not prev_highs:
        return None
    swing_high = max(prev_highs)
    swing_low  = min(prev_lows)
    last_close = closes[-1]
    if last_close > swing_high:
        return "bullish"
    if last_close < swing_low:
        return "bearish"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def format_silver_bullet_summary(sb: SilverBulletSetup) -> str:
    """Format Silver Bullet setup jadi string ringkas untuk logging/AI prompt."""
    dir_emoji = "🟢 BULLISH" if sb.direction == "bullish" else "🔴 BEARISH"
    return (
        f"=== ICT Silver Bullet Setup ===\n"
        f"Direction     : {dir_emoji}\n"
        f"Window        : {sb.window_label}\n"
        f"Confidence    : {sb.confidence * 100:.0f}%\n"
        f"\n[Step 1] Liquidity Sweep\n"
        f"  Direction   : {sb.sweep.direction}\n"
        f"  Swept Level : {sb.sweep.swept_level:.5f}\n"
        f"  Displacement: {'Confirmed ✓' if sb.sweep.displacement_confirmed else 'Weak'}\n"
        f"\n[Step 2] Fair Value Gap\n"
        f"  Type        : {sb.fvg.type.upper()}\n"
        f"  Top         : {sb.fvg.top:.5f}\n"
        f"  Bottom      : {sb.fvg.bottom:.5f}\n"
        f"  Size        : {sb.fvg.size:.5f}\n"
        f"\n[Step 3] OTE Zone (Fib 0.62-0.79)\n"
        f"  OTE Lower   : {sb.ote_lower:.5f}\n"
        f"  OTE Upper   : {sb.ote_upper:.5f}\n"
        f"  Entry Price : {sb.entry_price:.5f}  ← Price in OTE ✓\n"
        f"  Swing High  : {sb.swing_high:.5f}\n"
        f"  Swing Low   : {sb.swing_low:.5f}\n"
        f"\n[Trade Plan]\n"
        f"  Entry       : {sb.entry_price:.5f}\n"
        f"  Stop Loss   : {sb.sl:.5f}\n"
        f"  Take Profit : {sb.tp:.5f}\n"
    )
