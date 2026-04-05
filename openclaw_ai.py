#!/usr/bin/env python3
"""
openclaw_ai.py
==============
OpenClaw AI Decision Engine.
Menggunakan Anthropic API (Claude) sebagai otak pengambil keputusan trade.

Flow:
  1. Terima ICT scan result (Silver Bullet setup, macro context, dsb)
  2. Build structured prompt ke Claude
  3. Claude analisis dan putuskan: EXECUTE / WAIT / REJECT
  4. Return keputusan dengan reasoning

Author  : fznrival
Version : 2.0 — OpenClaw AI Integration
"""

import json
import logging
import requests
from datetime import datetime
from typing import Optional

from ict_concepts import SilverBulletSetup, ICTScanResult, format_silver_bullet_summary

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# AI Decision Result
# ─────────────────────────────────────────────────────────────────────────────

class AIDecision:
    EXECUTE = "EXECUTE"
    WAIT    = "WAIT"
    REJECT  = "REJECT"

    def __init__(self, action: str, confidence: float, reasoning: str, raw_response: str = ""):
        self.action      = action
        self.confidence  = confidence
        self.reasoning   = reasoning
        self.raw_response = raw_response
        self.timestamp   = datetime.now()

    def __str__(self):
        return f"[{self.action}] confidence={self.confidence:.0%} | {self.reasoning[:80]}"


# ─────────────────────────────────────────────────────────────────────────────
# Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah AI trading analyst yang spesialis ICT (Inner Circle Trader) 2022 methodology.
Tugasmu adalah menganalisis setup trading yang ditemukan oleh scanner dan memutuskan apakah layak dieksekusi.

ATURAN KETAT:
1. Hanya approve trade jika Silver Bullet 3-step LENGKAP: Liquidity Sweep + FVG + OTE
2. Hanya approve jika dalam Macro Time window ATAU Silver Bullet time window
3. Confidence setup harus >= 70% untuk EXECUTE
4. Jika ada keraguan sedikit pun, pilih WAIT
5. Pertimbangkan risk management: max 2 trade per hari, RR minimal 1:2
6. Selalu prioritaskan keselamatan modal

OUTPUT FORMAT (wajib JSON):
{
  "action": "EXECUTE" | "WAIT" | "REJECT",
  "confidence": 0.0-1.0,
  "reasoning": "penjelasan singkat dalam Bahasa Indonesia (max 150 kata)",
  "key_factors": ["faktor1", "faktor2", "faktor3"],
  "risk_notes": "catatan risiko jika ada"
}

Jangan tambahkan teks apapun di luar JSON."""

def build_trade_prompt(
    scan: ICTScanResult,
    sb: SilverBulletSetup,
    trades_today: int,
    account_balance: float,
    currency: str = "USD"
) -> str:
    """Build prompt lengkap untuk dikirim ke Claude."""
    now_wib = datetime.utcnow()

    prompt = f"""ANALISIS TRADE REQUEST — {now_wib.strftime('%Y-%m-%d %H:%M')} UTC

=== MARKET CONTEXT ===
Symbol        : {scan.symbol}
Session       : {scan.session}
Macro Active  : {'YA — ' + scan.macro_label if scan.macro_active else 'TIDAK'}
SB Window     : {'YA — ' + scan.sb_window_label if scan.sb_window_active else 'TIDAK'}
Trades Hari Ini: {trades_today}/2 (max 2 per hari)
Account Balance: {account_balance:.2f} {currency}

=== ICT SILVER BULLET SETUP ===
{format_silver_bullet_summary(sb)}

=== PERTANYAAN ===
Berdasarkan setup di atas, apakah trade ini layak dieksekusi?
Analisis semua faktor ICT dan risk management, lalu berikan keputusan dalam format JSON."""

    return prompt


def build_no_setup_prompt(scan: ICTScanResult) -> str:
    """Prompt ketika tidak ada setup ditemukan."""
    return f"""MARKET SCAN — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

Symbol  : {scan.symbol}
Session : {scan.session}
Macro   : {'AKTIF — ' + scan.macro_label if scan.macro_active else 'Tidak aktif'}
SB Win  : {'AKTIF — ' + scan.sb_window_label if scan.sb_window_active else 'Tidak aktif'}

Scanner tidak menemukan ICT Silver Bullet setup yang valid.
Tidak ada Liquidity Sweep + FVG + OTE yang terkonfirmasi.

Apakah ada alasan untuk tetap EXECUTE, atau pilih WAIT?
Jawab dalam format JSON yang sama."""


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic API Client
# ─────────────────────────────────────────────────────────────────────────────

class OpenClawAI:
    """
    OpenClaw AI via Anthropic API.
    Menggunakan Claude sebagai otak pengambil keputusan trading.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514",
                 max_tokens: int = 1024, confidence_threshold: float = 0.75):
        self.api_key   = api_key
        self.model     = model
        self.max_tokens = max_tokens
        self.confidence_threshold = confidence_threshold
        self.api_url   = "https://api.anthropic.com/v1/messages"
        self.headers   = {
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }

    def _call_api(self, user_prompt: str) -> str:
        """Panggil Anthropic API dan return raw response text."""
        payload = {
            "model":      self.model,
            "max_tokens": self.max_tokens,
            "system":     SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        }
        try:
            resp = requests.post(self.api_url, headers=self.headers,
                                 json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
        except requests.exceptions.HTTPError as e:
            log.error("Anthropic API HTTP error: %s | %s", e, resp.text[:200])
            raise
        except Exception as e:
            log.error("Anthropic API error: %s", e)
            raise

    def _parse_response(self, raw: str) -> AIDecision:
        """Parse JSON response dari Claude."""
        try:
            # Bersihkan markdown fence jika ada
            clean = raw.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = "\n".join(clean.split("\n")[:-1])

            data = json.loads(clean)
            return AIDecision(
                action     = data.get("action", AIDecision.WAIT),
                confidence = float(data.get("confidence", 0.0)),
                reasoning  = data.get("reasoning", ""),
                raw_response = raw,
            )
        except (json.JSONDecodeError, KeyError) as e:
            log.error("Gagal parse AI response: %s | Raw: %s", e, raw[:200])
            return AIDecision(
                action    = AIDecision.WAIT,
                confidence = 0.0,
                reasoning = f"Parse error: {e}. Default ke WAIT.",
                raw_response = raw,
            )

    def decide_trade(
        self,
        scan: ICTScanResult,
        sb: Optional[SilverBulletSetup],
        trades_today: int,
        account_balance: float,
        currency: str = "USD"
    ) -> AIDecision:
        """
        Minta keputusan trading dari Claude.
        Returns AIDecision dengan action EXECUTE / WAIT / REJECT.
        """
        if sb:
            prompt = build_trade_prompt(scan, sb, trades_today, account_balance, currency)
        else:
            prompt = build_no_setup_prompt(scan)

        log.info("Mengirim request ke OpenClaw AI (model=%s)...", self.model)

        try:
            raw      = self._call_api(prompt)
            decision = self._parse_response(raw)
            log.info("AI Decision: %s", decision)

            # Override ke WAIT jika confidence di bawah threshold
            if decision.action == AIDecision.EXECUTE and decision.confidence < self.confidence_threshold:
                log.info("Confidence %.0f%% < threshold %.0f%%. Override ke WAIT.",
                         decision.confidence * 100, self.confidence_threshold * 100)
                decision.action    = AIDecision.WAIT
                decision.reasoning = (
                    f"[Override] Confidence {decision.confidence:.0%} di bawah threshold "
                    f"{self.confidence_threshold:.0%}. " + decision.reasoning
                )

            return decision

        except Exception as e:
            log.error("OpenClaw AI gagal, default ke WAIT: %s", e)
            return AIDecision(
                action    = AIDecision.WAIT,
                confidence = 0.0,
                reasoning = f"AI tidak dapat dihubungi: {e}. Trade ditunda.",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Message Formatter untuk Telegram
# ─────────────────────────────────────────────────────────────────────────────

def format_ai_decision_telegram(
    symbol: str,
    scan: ICTScanResult,
    sb: Optional[SilverBulletSetup],
    decision: AIDecision,
    lot: float,
    rr: float
) -> str:
    """Format AI decision + setup jadi pesan Telegram."""
    now_wib = (datetime.utcnow()).strftime("%d %b %Y %H:%M") + " WIB"

    action_map = {
        AIDecision.EXECUTE: "⚡ *EXECUTE*",
        AIDecision.WAIT:    "⏳ *WAIT*",
        AIDecision.REJECT:  "🚫 *REJECT*",
    }
    action_str = action_map.get(decision.action, decision.action)

    msg = (
        f"🤖 *OpenClaw AI Decision*\n"
        f"{'─' * 28}\n"
        f"📌 Symbol   : `{symbol}`\n"
        f"🕐 Time     : `{now_wib}`\n"
        f"📊 Session  : `{scan.session}`\n"
    )

    if scan.macro_active:
        msg += f"📰 Macro    : `{scan.macro_label}`\n"
    if scan.sb_window_active:
        msg += f"🎯 SB Window: `{scan.sb_window_label}`\n"

    msg += f"\n{'─' * 28}\n🧠 *AI Decision :* {action_str}\n"
    msg += f"📈 Confidence : `{decision.confidence:.0%}`\n"
    msg += f"💬 Reasoning  :\n_{decision.reasoning}_\n"

    if sb and decision.action == AIDecision.EXECUTE:
        dir_emoji = "🟢 BUY" if sb.direction == "bullish" else "🔴 SELL"
        msg += (
            f"\n{'─' * 28}\n"
            f"📐 *Silver Bullet Setup*\n"
            f"  Direction : {dir_emoji}\n"
            f"  Sweep     : `{sb.sweep.direction}`\n"
            f"  FVG       : `{sb.fvg.type.upper()} ({sb.fvg.size:.5f})`\n"
            f"  OTE       : `{sb.ote_lower:.5f} — {sb.ote_upper:.5f}`\n"
            f"  Entry     : `{sb.entry_price:.5f}`\n"
            f"  SL        : `{sb.sl:.5f}`\n"
            f"  TP        : `{sb.tp:.5f}`\n"
            f"  RR        : `1:{rr}`\n"
            f"  Lot       : `{lot}`\n"
            f"  Setup ✓   : `Sweep → FVG → OTE`\n"
        )

    return msg
