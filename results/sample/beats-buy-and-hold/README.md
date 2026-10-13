# Is there anything that beats buy-and-hold?

10 coins, daily decisions, same paper exchange (fees, slippage, funding, liquidation) for every row.

## Bear market: 20 Sep → 19 Dec 2025 (10-coin basket −35%), `bear_market_*`

| strategy | return | max DD | trades | long / short PnL (USDT) |
|---|---|---|---|---|
| ema_trend (3x) | **+71.2%** | −28.7% | 96 | −235 / +7,353 |
| donchian_breakout (3x) | +57.1% | −27.4% | 90 | −1,112 / +6,819 |
| random (3x) | +10.0% | −22.0% | 466 | −4,290 / +5,288 |
| **Qwen3.6-27B, hold prompt v4** | +1.8% | −22.4% | 105 | −1,732 / +1,909 |
| buy_and_hold (1x) | −33.5% | −35.5% | 10 | −3,349 / – |

Shorting the decline is what wins; Qwen v4 shorted correctly (618 of 900 calls) but at 1.4x average leverage and with
smaller, more cautious trades. In the bull quarter (13 Jul → 11 Oct 2026) it was the reverse: buy-and-hold +28.5%,
Qwen v4 +19.1%, ema_trend −5.9%.

## Full cycle: 1 Sep 2024 → 11 Oct 2026, `full_cycle_*`, `ema_leverage_full_cycle.md`, `ema_1x_robustness.md`

| strategy | return | max DD | Sharpe |
|---|---|---|---|
| **ema_trend, daily, 1x** | **+31.5%** | **−32.7%** | 0.56 |
| ema_trend, daily, 3x | +36.5% | −74.3% | 0.59 |
| buy_and_hold, 1x | +9.7% | −63.1% | 0.39 |
| ema_trend, 4-hourly, 3x | −41.5% | −74.1% | 0.13 |
| donchian_breakout, daily, 3x | −53.2% | −75.7% | 0.15 |

Randomized tests for ema_trend at 1x (100 timing shuffles, 60 random 60-day windows on random coin subsets, 20 random risk settings):

- Timing p-value **0.01**: the real order of its calls beat 99% of shuffles (shuffled median −27%). The first
  statistically significant timing result in this project, and it holds across risk settings (median +17.6%).
- But it beat buy-and-hold in only 30% of random 60-day windows (median −7 pts). Its whole lead comes from the
  2025–26 crash, where shorting paid; most of the time it trails, flat while buy-and-hold rallies.
- The ranking depends on the end date: buy-and-hold was far ahead (peak ~22,000 vs ~12,500) until late 2025
  (`ema_1x_vs_buy_and_hold.png`). What ema_trend reliably delivers is half the drawdown, not a higher return.
- Decision frequency matters: the same rule checked every 4h over-trades and loses 41.5%.

## Verdict

Yes, over a full bull-and-bear cycle a daily trend-following rule at 1x beat buy-and-hold (+31.5% vs +9.7%) with
half the drawdown and significant timing. It's crisis protection, not a better bull-market strategy. No LLM beat
buy-and-hold over a full cycle yet; Qwen v4 beat it by 35 points in the bear market and trailed it in the bull market.
