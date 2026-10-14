# Survivorship check and the trend hybrid (free experiments suggested by the Fable 5.1 advisor)

All at 1x, daily decisions, no take-profit (let winners run), Sep 2024 → Oct 2026. Per-quarter tables in
`quarterly_tables.md` (bold = beat buy-and-hold that quarter).

`trend_hybrid` = buy-and-hold core with a short overlay: long by default, short only when EMA20 < EMA50, price < EMA200
and ADX > 20; no stops. MATIC and POL are stitched into one series (MATICPOLUSDT) across the Sep 2024 migration.

| coin set | buy-and-hold | ema_trend | trend_hybrid | Sharpe (B&H / ema / hybrid) |
|---|---|---|---|---|
| A. today's top-10 | +9.7% | +93.5% | +123.0% | 0.39 / 1.12 / 1.12 |
| B. 2024 top-10 (TON instead of LINK) | +3.8% | +77.8% | +116.5% | 0.33 / 1.06 / 1.15 |
| **C. wide 16: today's 10 + DOT, LTC, BCH, TON, SHIB, MATIC/POL** | **−10.2%** | **+44.5%** | **+51.6%** | 0.20 / 0.71 / 0.69 |
| only the 6 coins that dropped out | −26.1% | −10.2% | −10.7% | −0.29 / −0.20 / −0.10 |

- Survivorship was inflating results by about 30–50 points, but on the wider set that includes later losers both
  strategies still beat buy-and-hold by 55–60 points with roughly half its drawdown (−30% / −42% vs −67%).
- Randomized tests on set C, 90-day windows (`robustness_wide16_90d_windows.md`): ema_trend beats buy-and-hold in
  **75%** of 40 random 90-day windows on random coin subsets (median +8.5 pts), trend_hybrid in 72% (+7.8 pts);
  trade-bootstrap 5–95% ranges +10%…+84% and +14.5%…+92% vs buy-and-hold −29%…+11%. ema_trend is now the champion
  for this setup (`results/champion.json`), the first time anything has displaced buy-and-hold.
- The timing p-value (0.016 for both) is weaker evidence than it looks: shuffled calls flip often and pay fees.
- Quarter by quarter, both lose every strong bull quarter to buy-and-hold; trend_hybrid keeps more of it
  (e.g. 2024Q4 +40% vs +47%, 2026Q3 +16% vs +35%) and both win every bear quarter.
- The hybrid's rule was proposed after seeing this period (by the advisor), so it has not been validated walk-forward;
  ema_trend's settings have (`results/sample/beats-buy-and-hold/ema_walk_forward.json`).
