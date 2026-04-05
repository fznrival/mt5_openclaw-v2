#!/bin/bash
# setup_cron.sh v2.0 — Full Automated Trading System
set -e
PYTHON="python3"
BASE="$HOME/mt5_openclaw/python"
LOG="/tmp"

echo "======================================================"
echo "  Setup Cron v2 — ICT Silver Bullet + Macro Time"
echo "======================================================"

crontab -l 2>/dev/null > /tmp/crontab_backup_$(date +%Y%m%d_%H%M).txt
echo "Backup: /tmp/crontab_backup_$(date +%Y%m%d_%H%M).txt"

(
  crontab -l 2>/dev/null | grep -v "mt5_openclaw\|trade_summary\|ict_executor\|position_monitor"

  echo "# ========================================================"
  echo "# MT5 + OpenClaw AI — Full ICT Silver Bullet System v2"
  echo "# Generated: $(date)"
  echo "# ========================================================"

  # ICT Silver Bullet Scanner — setiap 15 menit
  echo "# Silver Bullet Scanner — setiap 15 menit"
  echo "*/15 * * * * cd $HOME/mt5_openclaw/python && WINEPREFIX=$HOME/.wine_mt5 wine python mt5_ict_executor.py >> $LOG/ict_trade.log 2>&1"

  # Position Monitor — setiap 30 menit
  echo "# Position Monitor — setiap 30 menit"
  echo "*/30 * * * * $PYTHON $BASE/trade_summary.py --positions >> $LOG/position_monitor.log 2>&1"

  # Daily Report — Senin-Jumat 23:00 WIB = 16:00 UTC
  echo "# Daily Report — Senin-Jumat 23:00 WIB"
  echo "0 16 * * 1-5 $PYTHON $BASE/trade_summary.py --period today >> $LOG/trade_summary.log 2>&1"

  # Weekly Report — Jumat 23:30 WIB
  echo "# Weekly Report — Jumat 23:30 WIB"
  echo "30 16 * * 5 $PYTHON $BASE/trade_summary.py --period week >> $LOG/trade_summary.log 2>&1"

  # Monthly Report — Akhir bulan
  echo "# Monthly Report — Akhir bulan 23:45 WIB"
  echo "45 16 28-31 * * [ \"\$(date +\%d -d tomorrow)\" = '01' ] && $PYTHON $BASE/trade_summary.py --period month >> $LOG/trade_summary.log 2>&1"

) | crontab -

echo ""
echo "Cron jobs aktif:"
crontab -l | grep -v "^#" | grep -v "^$"
echo ""
echo "Logs:"
echo "  Scanner     : tail -f /tmp/ict_trade.log"
echo "  Positions   : tail -f /tmp/position_monitor.log"
echo "  Reports     : tail -f /tmp/trade_summary.log"
