"""
DashboardGenerator — static HTML dashboard with inline CSS/JS.

Single-file, self-contained. No server. No CDN. No external dependencies.
Pure Canvas API for charts, CSS grid for heatmap, embedded JSON for data.
Open in any browser.
"""
import json
import sqlite3
from datetime import datetime, timezone

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.data.market_data import make_provider
from trading_lab.strategies import get_strategy, list_strategies


class DashboardGenerator:
    """Generate a self-contained static HTML dashboard with embedded data."""

    def __init__(self, db_path: str, cache_db_path: str = "") -> None:
        self.db_path = db_path
        self.cache_db_path = cache_db_path

    def generate(
        self,
        ticker: str = "AAPL_US_EQ",
        data_source: str = "static",
        prices_file: str = "",
    ) -> str:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        strategies = self._collect_strategy_data(ticker, data_source, prices_file)
        calendar = self._collect_signal_calendar()
        recent_signals = self._collect_recent_signals(limit=30)
        account_snapshot = self._collect_snapshot_summary()

        payload = json.dumps({
            "generated_at": generated_at,
            "ticker": ticker,
            "data_source": data_source,
            "strategies": strategies,
            "calendar": calendar,
            "recent_signals": recent_signals,
            "account_snapshot": account_snapshot,
        }, default=str)

        return _HTML_TEMPLATE.replace("__DATA_PAYLOAD__", payload)

    def _collect_strategy_data(self, ticker, data_source, prices_file) -> list[dict]:
        provider = make_provider(
            source=data_source, ticker=ticker, prices_file=prices_file,
            cache_db=self.cache_db_path,
        )
        prices = provider.get_prices(ticker=ticker, lookback=252)

        result = []
        for name in sorted(list_strategies()):
            try:
                strategy = get_strategy(name, **_default_kwargs(name))
                engine = BacktestEngine(strategy)
                bt = engine.run(prices=prices, ticker=ticker)
                result.append({
                    "name": name,
                    "metrics": {k: v for k, v in bt.metrics.items()},
                    "equity_curve": bt.equity_curve,
                    "trades": [
                        {
                            "entry_date": t.entry_date,
                            "exit_date": t.exit_date,
                            "entry_price": t.entry_price,
                            "exit_price": t.exit_price,
                            "pnl": t.pnl,
                            "return_pct": t.return_pct,
                        }
                        for t in bt.trades if t.pnl is not None
                    ],
                    "signal_count": len(bt.signals),
                })
            except Exception:
                result.append({
                    "name": name, "metrics": {}, "equity_curve": [],
                    "trades": [], "signal_count": 0, "error": True,
                })
        return result

    def _collect_signal_calendar(self) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT date(created_at) as day, strategy, action, COUNT(*) as cnt
                       FROM signals
                       WHERE date(created_at) >= date('now', '-84 days')
                       GROUP BY day, strategy, action
                       ORDER BY day ASC"""
                ).fetchall()
                calendar: dict[str, dict] = {}
                for row in rows:
                    r = dict(row)
                    st = r["strategy"]
                    day = r["day"]
                    if st not in calendar:
                        calendar[st] = {}
                    if day not in calendar[st]:
                        calendar[st][day] = {"BUY": 0, "SELL": 0, "HOLD": 0, "total": 0}
                    calendar[st][day][r["action"]] = r["cnt"]
                    calendar[st][day]["total"] += r["cnt"]
                return calendar
        except sqlite3.OperationalError:
            return {}

    def _collect_recent_signals(self, limit: int = 30) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def _collect_snapshot_summary(self) -> dict | None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM snapshots WHERE snapshot_type='account_summary' "
                    "ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row:
                    r = dict(row)
                    try:
                        r["parsed"] = json.loads(r["data_json"])
                    except (json.JSONDecodeError, KeyError):
                        r["parsed"] = {}
                    return r
                return None
        except sqlite3.OperationalError:
            return None


def _default_kwargs(name: str) -> dict:
    if name == "simple_momentum":
        return {"lookback": 5}
    if name == "ma_crossover":
        return {"fast": 10, "slow": 30}
    if name == "mean_reversion":
        return {"period": 14, "oversold": 30, "overbought": 70}
    return {}


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sid Trading Lab — Dashboard</title>
<style>
*,*::before,*::after{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:0;line-height:1.5}
.container{max-width:1200px;margin:0 auto;padding:1.5rem}
.header{border-bottom:1px solid #30363d;padding-bottom:1rem;margin-bottom:1.5rem}
.header h1{font-size:1.6rem;margin:0 0 .25rem;color:#f0f6fc}
.meta{color:#8b949e;font-size:.85rem;margin:0}
section{margin-bottom:2rem}
h2{font-size:1.2rem;color:#f0f6fc;border-bottom:1px solid #21262d;padding-bottom:.4rem;margin-bottom:.8rem}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem;margin-bottom:1rem}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{padding:.4rem .6rem;text-align:left;border-bottom:1px solid #21262d}
th{color:#f0f6fc;font-weight:600;white-space:nowrap}
tr:hover{background:rgba(255,255,255,.03)}
.green{color:#3fb950}
.red{color:#f85149}
.yellow{color:#d29922}
.muted{color:#8b949e}
.positive{color:#3fb950}
.negative{color:#f85149}
footer{margin-top:2rem;padding-top:1rem;border-top:1px solid #30363d;font-size:.8rem;color:#8b949e}
canvas{display:block;width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px}

/* heatmap */
.heatmap-grid{display:grid;gap:3px;overflow-x:auto}
.heatmap-cell{border-radius:3px;text-align:center;font-size:.75rem;padding:4px 2px;min-width:28px;cursor:default}
.heatmap-cell:hover{outline:2px solid #58a6ff;z-index:1}
.hm-0{background:rgba(22,27,34,.6);color:#484f58}
.hm-1{background:rgba(14,68,41,.6);color:#7ee787}
.hm-2{background:rgba(0,109,50,.6);color:#7ee787}
.hm-3{background:rgba(0,140,50,.6);color:#aff5b4}
.hm-4{background:rgba(22,163,0,.6);color:#aff5b4}
.hm-5{background:rgba(46,160,67,.8);color:#dafbe1}

.legend-row{display:flex;gap:1.5rem;flex-wrap:wrap;margin-top:.5rem;font-size:.8rem}
.legend-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}

.tag{padding:1px 6px;border-radius:10px;font-size:.75rem;font-weight:600}
.tag-BUY{background:rgba(46,160,67,.25);color:#3fb950}
.tag-SELL{background:rgba(248,81,73,.25);color:#f85149}
.tag-HOLD{background:rgba(139,148,158,.2);color:#8b949e}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Sid Trading Lab</h1>
<p class="meta" id="page-meta"></p>
</div>

<section>
<h2>Strategy Performance</h2>
<div class="card">
<table>
<thead><tr>
<th>Strategy</th><th>Return</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th>
<th>Win Rate</th><th>Profit Factor</th><th>Trades</th><th>Signals</th>
</tr></thead>
<tbody id="strategy-tbody"></tbody>
</table>
</div>
</section>

<section>
<h2>Equity Curves</h2>
<canvas id="equity-canvas"></canvas>
<div class="legend-row" id="equity-legend"></div>
</section>

<section>
<h2>Signal Heatmap</h2>
<div class="card" id="heatmap-container"></div>
</section>

<section>
<h2>Recent Signals</h2>
<div class="card" style="max-height:400px;overflow-y:auto">
<table>
<thead><tr><th>Time</th><th>Ticker</th><th>Strategy</th><th>Action</th><th>Conf</th><th>Reason</th></tr></thead>
<tbody id="signals-tbody"></tbody>
</table>
</div>
</section>

<section>
<h2>Account Snapshot</h2>
<div class="card">
<pre id="account-display" style="margin:0;white-space:pre-wrap;font-size:.85rem;font-family:SFMono,monospace"></pre>
</div>
</section>

<footer>
<p>Demo environment only — no live trades. Past performance does not guarantee future results.</p>
<p>Generated by Sid Trading Lab dashboard v1.</p>
</footer>
</div>

<script>
const DATA = __DATA_PAYLOAD__;

const COLORS = ['#58a6ff','#3fb950','#d29922','#f78166','#bc8cff','#ff7b72','#79c0ff','#a5d6ff'];

function fmt(v) {
  if (v == null) return '-';
  if (typeof v === 'number') return v.toFixed(2);
  return String(v);
}

function colorClass(v, threshold) {
  if (v == null) return '';
  if (v > 0) return 'positive';
  if (v < 0) return 'negative';
  return '';
}

// -- Strategy table --
(function() {
  var tbody = document.getElementById('strategy-tbody');
  var rows = '';
  DATA.strategies.forEach(function(s) {
    var m = s.metrics || {};
    rows += '<tr>';
    rows += '<td><strong>' + s.name + '</strong></td>';
    rows += '<td class="' + colorClass(m.total_return_pct) + '">' + fmt(m.total_return_pct) + '%</td>';
    rows += '<td>' + fmt(m.cagr_pct) + '%</td>';
    rows += '<td>' + fmt(m.sharpe_ratio) + '</td>';
    rows += '<td class="negative">' + fmt(m.max_drawdown_pct) + '%</td>';
    rows += '<td>' + fmt(m.win_rate) + '%</td>';
    rows += '<td>' + fmt(m.profit_factor) + '</td>';
    rows += '<td>' + (m.total_trades || 0) + '</td>';
    rows += '<td class="muted">' + (s.signal_count || 0) + '</td>';
    rows += '</tr>';
  });
  if (!DATA.strategies.length) {
    rows = '<tr><td colspan="9" class="muted">No strategy data available.</td></tr>';
  }
  tbody.innerHTML = rows;
})();

// -- Equity curves --
(function() {
  var canvas = document.getElementById('equity-canvas');
  var legend = document.getElementById('equity-legend');
  var dpr = window.devicePixelRatio || 1;
  var width = canvas.parentElement.clientWidth - 2;
  var height = 380;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = width + 'px';
  canvas.style.height = height + 'px';
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  var strategies = DATA.strategies.filter(function(s) { return s.equity_curve && s.equity_curve.length > 1; });
  if (!strategies.length) { legend.innerHTML = '<span class="muted">No equity data available.</span>'; return; }

  var allEquities = [];
  strategies.forEach(function(s) {
    s.equity_curve.forEach(function(p) { allEquities.push(p.equity); });
  });
  var minE = Math.min.apply(null, allEquities);
  var maxE = Math.max.apply(null, allEquities);
  var range = maxE - minE || 1;
  var pad = 0.08;
  margin = {top: 20, right: 30, bottom: 40, left: 70};
  var plotW = width - margin.left - margin.right;
  var plotH = height - margin.top - margin.bottom;

  function x(i) { return margin.left + (i / (strategies[0].equity_curve.length - 1)) * plotW; }
  function y(v) { return margin.top + plotH - ((v - minE) / range) * plotH; }

  // Background
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, width, height);

  // Grid lines
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 0.5;
  for (var i = 0; i <= 4; i++) {
    var gy = margin.top + (i / 4) * plotH;
    ctx.beginPath(); ctx.moveTo(margin.left, gy); ctx.lineTo(margin.left + plotW, gy); ctx.stroke();
  }

  // Y-axis labels
  ctx.fillStyle = '#8b949e';
  ctx.font = '11px system-ui';
  ctx.textAlign = 'right';
  for (var i = 0; i <= 4; i++) {
    var val = minE + (range * (4 - i) / 4);
    ctx.fillText('$' + val.toFixed(0), margin.left - 8, margin.top + (i / 4) * plotH + 4);
  }

  // Lines
  var legendHtml = '';
  strategies.forEach(function(s, si) {
    var color = COLORS[si % COLORS.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    s.equity_curve.forEach(function(p, i) {
      var px = x(i), py = y(p.equity);
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.stroke();

    // Dots at first/last
    var first = s.equity_curve[0], last = s.equity_curve[s.equity_curve.length - 1];
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(x(0), y(first.equity), 3, 0, Math.PI*2); ctx.fill();
    ctx.beginPath(); ctx.arc(x(s.equity_curve.length-1), y(last.equity), 3, 0, Math.PI*2); ctx.fill();

    legendHtml += '<span><span class="legend-dot" style="background:' + color + '"></span>' + s.name + '</span>';
  });
  legend.innerHTML = legendHtml;
})();

// -- Heatmap --
(function() {
  var container = document.getElementById('heatmap-container');
  var cal = DATA.calendar;
  var strats = Object.keys(cal).sort();
  if (!strats.length) {
    container.innerHTML = '<p class="muted">No signal data available for heatmap.</p>';
    return;
  }

  // Collect all dates
  var allDates = new Set();
  strats.forEach(function(st) { Object.keys(cal[st]).forEach(function(d) { allDates.add(d); }); });
  var dates = Array.from(allDates).sort();
  if (!dates.length) {
    container.innerHTML = '<p class="muted">No signal dates in range.</p>';
    return;
  }

  // Build grid: rows=strategies, cols=dates(weeks)
  // Group dates by week for column headers
  var grid = '<div class="heatmap-grid" style="grid-template-columns:80px repeat(' + dates.length + ', 1fr)">';
  // Header row
  grid += '<div style="font-size:.7rem;font-weight:600;padding:2px">Strategy</div>';
  dates.forEach(function(d) {
    var short = d.slice(5); // MM-DD
    grid += '<div style="font-size:.65rem;color:#8b949e;text-align:center" title="' + d + '">' + short + '</div>';
  });

  strats.forEach(function(st) {
    grid += '<div style="font-size:.75rem;font-weight:600;padding:2px">' + st + '</div>';
    dates.forEach(function(d) {
      var day = cal[st][d];
      var total = day ? day.total : 0;
      var cls = 'hm-0';
      if (total === 1) cls = 'hm-1';
      else if (total === 2) cls = 'hm-2';
      else if (total === 3) cls = 'hm-3';
      else if (total === 4) cls = 'hm-4';
      else if (total >= 5) cls = 'hm-5';
      var title = d + ': ' + (day ? 'B' + day.BUY + '/S' + day.SELL + '/H' + day.HOLD : 'no signals');
      grid += '<div class="heatmap-cell ' + cls + '" title="' + title + '">' + (total || '') + '</div>';
    });
  });

  grid += '</div>';
  container.innerHTML = grid;
})();

// -- Recent signals --
(function() {
  var tbody = document.getElementById('signals-tbody');
  var rows = '';
  DATA.recent_signals.forEach(function(s) {
    var actionTag = '<span class="tag tag-' + s.action + '">' + s.action + '</span>';
    var time = (s.created_at || '').slice(0, 16).replace('T', ' ');
    var reason = (s.reason || '');
    if (reason.length > 50) reason = reason.slice(0, 47) + '...';
    rows += '<tr>';
    rows += '<td class="muted" style="white-space:nowrap">' + time + '</td>';
    rows += '<td>' + (s.ticker || '?') + '</td>';
    rows += '<td>' + (s.strategy || '?') + '</td>';
    rows += '<td>' + actionTag + '</td>';
    rows += '<td>' + (s.confidence != null ? s.confidence.toFixed(2) : '-') + '</td>';
    rows += '<td class="muted">' + reason + '</td>';
    rows += '</tr>';
  });
  if (!DATA.recent_signals.length) {
    rows = '<tr><td colspan="6" class="muted">No signals recorded yet.</td></tr>';
  }
  tbody.innerHTML = rows;
})();

// -- Account snapshot --
(function() {
  var el = document.getElementById('account-display');
  var snap = DATA.account_snapshot;
  if (!snap) {
    el.textContent = 'No account snapshot available. Run account-summary --save-snapshot to record one.';
    return;
  }
  var parsed = snap.parsed || {};
  if (Object.keys(parsed).length) {
    el.textContent = JSON.stringify(parsed, null, 2);
  } else {
    el.textContent = 'Snapshot recorded at ' + snap.created_at + ' (unable to parse JSON payload)';
  }
})();

// -- Meta --
document.getElementById('page-meta').textContent =
  'Generated: ' + DATA.generated_at + '  |  Ticker: ' + DATA.ticker +
  '  |  Source: ' + DATA.data_source;
</script>
</body>
</html>"""
