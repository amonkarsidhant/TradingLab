# Trade Log

## Open Positions (as of 2026-05-04)

| Ticker | Qty | Entry | Current | P&L % | Strategy | Days Held | Stop | Peak | Drawdown from Peak |
|---|---|---|---|---|---|---|---|---|---|
| GOOGL_US_EQ | 1 | €352.37 | €384.10 | +9.0% | simple_momentum | 5 | €327.70 | €384.74 | -0.2% |
| INTC_US_EQ | 1 | €93.17 | €98.54 | +5.8% | simple_momentum | 5 | €86.65 | €98.54 | 0.0% |
| AMD_US_EQ | 1 | €333.23 | €344.20 | +3.3% | simple_momentum | 5 | €309.90 | €352.72 | -2.4% |
| AAPL_US_EQ | 1 | €269.32 | €276.28 | +2.6% | simple_momentum | 5 | €250.47 | €276.28 | 0.0% |
| AMZN_US_EQ | 1 | €265.23 | €273.27 | +3.0% | simple_momentum | 5 | €246.66 | €273.27 | 0.0% |
| TSLA_US_EQ | 2 | €393.17 | €392.59 | -0.15% | momentum | 0 | — | €393.17 | 0.0% |
| KO_US_EQ | 1 | €78.49 | €78.21 | -0.36% | simple_momentum | 4 | €73.00 | €78.82 | -0.8% |
| CRM_US_EQ | 5 | €186.50 | €185.93 | -0.36% | momentum | 0 | — | €186.50 | 0.0% |
| ADBE_US_EQ | 4 | €254.46 | €254.09 | -0.15% | momentum | 0 | — | €254.46 | 0.0% |
| MSFT_US_EQ | 1 | €425.30 | €414.62 | -2.51% | simple_momentum | 5 | €395.53 | €425.30 | -2.51% |

## Closed Positions

| Date | Ticker | Action | Qty | Price | P&L |
|---|---|---|---|---|---|
| 2026-04-30 | NVDA_US_EQ | STOP (GTC filled) | -1 | €196.55 | -7.0% (-€14.79 realized) |

## Recent Trades

| Date | Ticker | Action | Qty | Price | Reason |
|---|---|---|---|---|---|
| 2026-04-29 | AAPL_US_EQ | BUY | 1 | €269.32 | Momentum +1.71% |
| 2026-04-29 | NVDA_US_EQ | BUY | 1 | €211.34 | Momentum +6.65% |
| 2026-04-29 | MSFT_US_EQ | BUY | 1 | €425.30 | Momentum +1.20% |
| 2026-04-29 | AMZN_US_EQ | BUY | 1 | €265.23 | Momentum +3.92% |
| 2026-04-29 | GOOGL_US_EQ | BUY | 1 | €352.37 | Momentum +5.26% |
| 2026-04-29 | AMD_US_EQ | BUY | 1 | €333.23 | Momentum +13.61% |
| 2026-04-29 | INTC_US_EQ | BUY | 1 | €93.17 | Momentum +27.56% |
| 2026-04-30 | KO_US_EQ | BUY | 1 | €78.49 | Momentum +5.68% — diversification |
| 2026-04-30 | MSFT_US_EQ | STOP (GTC) | -1 | €395.53 | Auto stop at -7% from entry |
| 2026-04-30 | NVDA_US_EQ | STOP (GTC) | -1 | €196.55 | Auto stop at -7% from entry |
| 2026-04-30 | AMZN_US_EQ | STOP (GTC) | -1 | €246.66 | Auto stop at -7% from entry |
| 2026-04-30 | AAPL_US_EQ | STOP (GTC) | -1 | €250.47 | Auto stop at -7% from entry |
| 2026-04-30 | AMD_US_EQ | STOP (GTC) | -1 | €309.90 | Auto stop at -7% from entry |
| 2026-04-30 | GOOGL_US_EQ | STOP (GTC) | -1 | €327.70 | Auto stop at -7% from entry |
| 2026-04-30 | INTC_US_EQ | STOP (GTC) | -1 | €86.65 | Auto stop at -7% from entry |
| 2026-04-30 | KO_US_EQ | STOP (GTC) | -1 | €73.00 | Auto stop at -7% from entry |
| 2026-05-04 | ADBE_US_EQ | BUY | 4 | €254.46 | Scan signal — large-cap quality |
| 2026-05-04 | TSLA_US_EQ | BUY | 2 | €393.17 | Scan signal |
| 2026-05-04 | CRM_US_EQ | BUY | 5 | €186.50 | Scan signal — large-cap quality |
| 2026-05-04 | TSLA_US_EQ | CANCEL | -2 | n/a | Accidental test order — cancelled before fill |

## Performance

- Starting capital: €5,000
- Current value: €5,024.60
- Cash: €1,088.55
- Invested (current): €3,936.05
- Invested (cost): €3,892.28
- Realized P&L: €-12.79 (NVDA stop-loss)
- Unrealized P&L: €+43.77
- Total return: +0.49%
- Cash reserve: 21.7% (safe, above 10% minimum)
- Positions: 10/10 (MAX — no new positions without trimming)
- Active stops: 7 GTC stops on original positions

## Notes

- **NVDA stopped out at -7%** on 2026-04-30. First realized loss. Trailing stop system working as designed.
- **Position limit reached** — 10/10 positions. No new entries without trimming or exiting existing positions.
- **May 4 buys:** ADBE (4 qty), TSLA (2 qty), CRM (5 qty) via jarvis scan signals.
- **TSLA E2E test:** Accidentally placed a SELL market order during SELL 400 fix verification. Order `48550513454` was cancelled before market open — no fill, no harm.
- **MSFT** is the weakest position at -2.51% from entry, approaching its GTC stop at €395.53. Needs watching.
- **Trailing stops** should be upgraded from fixed -7% (entry) to peak-based. GOOGL is +9.0% but a pullback to -7% from peak (€356.22) would still be +1.1% above entry. Fixed stops penalize winners.
