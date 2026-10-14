# Long history: 8.5 years, 43 coins, including the ones that died

Answering "can more compute make up for little data?": first get more real data, then use compute to measure
overfitting. All runs: 1x, daily decisions, no take-profit (let winners run), 80% total exposure cap
(43 positions x 1.86% margin), fees and slippage as in every other test.

## Data (`spot_43coins_2017_2026.toml`, `futures_coins_2020_2026.toml`)

- **Spot, Aug 2017 → Oct 2026**, daily candles, 43 coins: the large coins of 2017–2023, including ones that collapsed
  or were delisted (LUNA cut at its May 2022 collapse, FTT at the FTX failure, XMR/WAVES/EOS delisted, and FIL, ICP,
  ONT, QTUM, IOTA, NEO down 93–99%). No funding on spot, which slightly flatters longs in bull years.
- **USD-M perpetual futures, Jan 2020 → Oct 2026**, same coins, with real funding payments.
- Prepared with `cryptofutures download --market spot|futures --interval 1d` and `clean_long_history()`, which cuts
  a series at its first gap of more than 14 days (delisting, or a ticker reused for a new asset) and stitches MATIC→POL.

## Yearly results (`yearly_tables.md`)

| | buy-and-hold | ema_trend | trend_hybrid | donchian_breakout | trend_filter_long |
|---|---|---|---|---|---|
| **spot 2018–2026** total | +310% | +390% | +1,301% | **+1,799%** | +748% |
| Sharpe | 0.59 | 0.71 | 0.88 | **1.07** | 0.85 |
| max drawdown | −84.6% | −43.6% | −65.1% | −43.9% | −50.9% |
| 2022 (bear) | −78.4% | +15.2% | −38.1% | −3.3% | −27.5% |
| **futures 2020–2026** total | +51.5% | +150.8% | +132.8% | **+392.7%** | +188.8% |
| Sharpe | 0.58 | 0.59 | 0.53 | **0.82** | 0.62 |
| max drawdown | −93.6% | −45.6% | −81.7% | −46.0% | −51.9% |

## Overfitting statistics: 72-variant trend family (`overfit_*.json`, `variants_*.csv`)

3 EMA pairs x 2 long EMAs x 3 ADX filters x {trend with 3 exit settings, hybrid}. CSCV with 16 blocks, 2,000 splits.

| | spot 2018–2026 | futures 2020–2026 |
|---|---|---|
| probability of backtest overfitting (PBO) | **14.8%** | 36.4% |
| in-sample best still profitable out of sample | 96% of splits | 82% of splits |
| best variant (annual Sharpe) | 10/30/100, no ADX, 3x-ATR stop (1.09) | 10/30/100, no ADX, 1.5x-ATR stop (0.90) |
| Sharpe the best of 72 would reach by luck | 0.80 | 0.66 |
| deflated Sharpe (P that the best is real) | 0.79 | 0.72 |
| variants with positive returns | 93% | 93% |

By exit rule, share of the 18 variants each that beat buy-and-hold's Sharpe:

| exit | spot | futures |
|---|---|---|
| hybrid, no stops | 100% (median Sharpe 0.86) | 56% (0.61) |
| no take-profit, 3x-ATR stop | 67% (0.74) | 56% (0.59) |
| no take-profit, 1.5x-ATR stop | 61% (0.70) | 56% (0.60) |
| **take-profit at 2x the stop** | **0% (0.12)** | **0% (0.06)** |

## Randomized tests (`robustness_*.md`), 90-day windows on random coin subsets

| | timing p | shuffled median | trade bootstrap 5–95% | beats B&H in random 90-day windows | median gap |
|---|---|---|---|---|---|
| **spot 2018–2026** donchian_breakout | 0.01 | −77% | – | 50% | −0.2 pts |
| ema_trend | 0.01 | −73% | – | 48% | −0.3 pts |
| **futures 2020–2026** donchian_breakout | 0.016 | −68% | **+190% … +617%** | 50% | −1.0 pts |
| ema_trend | 0.016 | −61% | +63% … +252% | 42% | −4.2 pts |
| buy_and_hold | – | – | −58% … +188% | – | – |

On futures, Donchian's pessimistic bootstrap end (+190%) is above buy-and-hold's optimistic end (+188%).
(The random-risk-settings column in the spot report is not comparable: some draws set a confidence filter above
these rules' fixed 0.7 and switch them off.)

## What it means

- The edge is **avoiding catastrophes, not winning typical quarters**. In an average 90-day window trend following
  is a coin flip against buy-and-hold; it wins over years because it sidesteps the −78% / −85% crashes and compounds
  from a higher base. Its drawdowns are about half of buy-and-hold's in every dataset.
- **Take-profits break trend following**: 0 of 36 take-profit variants beat buy-and-hold, across both datasets.
- **Donchian breakout** is the most consistent rule (Sharpe 1.07 spot / 0.82 futures, drawdown −44% / −46%).
  It was a fixed baseline from the start, not picked from the 72-variant search.
- On futures the Sharpe advantage shrinks (most variants ≈ buy-and-hold's 0.58) and PBO rises to 36%: evidence
  is weaker on the shorter, funding-inclusive dataset. Deflated Sharpe is below the 0.95 bar in both.
- Not yet covered: coins that never made a top list, exchange failures, and live (out-of-sample) results;
  live paper trading of ema_trend started on 14 Oct 2026 (`results/live/`).
