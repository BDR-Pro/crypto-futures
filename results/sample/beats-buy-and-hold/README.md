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

## Let winners run: `ride_*`, `ema_ride_robustness.md`, `ema_walk_forward.json`, `ema_trend_ride.toml`

The risk layer's default take-profit (about 2x the stop) was capping every trend. With no take-profit and ATR stops,
1x leverage, daily decisions (full cycle, Sep 2024 -> Oct 2026):

| strategy (1x) | return | Sharpe | max DD | trades |
|---|---|---|---|---|
| **ema_trend, no take-profit, 3x-ATR stop** | **+90.5%** | **1.11** | **−28.0%** | 209 |
| donchian_breakout, same settings | +38.7% | 0.61 | −40.9% | 192 |
| ema_trend, default take-profit | +31.5% | 0.56 | −32.7% | 694 |
| buy_and_hold | +9.7% | 0.39 | −63.1% | 10 |

- Randomized tests: timing p = 0.01 (shuffled median −29.8%); trade bootstrap 5–95% **+34.8% … +152.8%**;
  beats buy-and-hold in 32% of random 60-day windows (it wins big in trends, trails in between).
- Half-years vs buy-and-hold: +45.2% vs +41.6%, −6.7% vs +28.4%, **+33.3% vs −39.7%**, +6.0% vs +12.4%.
- Walk-forward (`ema_walk_forward.json`): with "no take-profit" as just one option, tuning on past data only chose
  it in **every** fold (with 1.5x-ATR stops) and beat the defaults out of sample (Sharpe 0.72 vs 0.53).
- An independent review (Fable 5.1 advisor session, fresh data, own scripts) reached the same result: ema_trend
  +74.8% vs buy-and-hold +5.7% (Aug 2024 → Oct 2026), all 10 coins profitable, 46 of 50 neighbouring settings
  beating buy-and-hold on Sharpe.
- The LLM does not benefit: Qwen v4 under these settings made +10.0% (bull) and −3.0% (bear), worse than with its own stops.

The ready-made config `ema_trend_ride.toml` (1.5x-ATR stop, the walk-forward choice) gives +93.5%, Sharpe 1.12,
max drawdown −28.7% on the same period.

Open caveats: the coin list is today's top 10 (survivorship); the bear window and start date were chosen after seeing
the data; two years is one cycle. Paper trading only.

## Verdict

Yes. A daily EMA trend rule at 1x that lets winners run (no take-profit, ATR stop) beat buy-and-hold over the full
cycle: +90.5% vs +9.7%, Sharpe 1.11 vs 0.39, max drawdown −28% vs −63%. Its timing is significant, its bootstrap
range sits above buy-and-hold, and walk-forward tuning picks the same settings without hindsight. It still trails
buy-and-hold in strong bull runs; its edge is riding trends both ways and shorting crashes. No LLM has beaten it yet.
