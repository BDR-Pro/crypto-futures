# Strategy discovery: 244 LLM-written strategies, one locked holdout

`cryptofutures discover` has models on OpenRouter write trading strategies as Python code. Each candidate is
checked for look-ahead and scored only on **spot 2018-01 → 2023-06** (43 coins, including dead ones). The pick
is the best search score, fixed in advance. It and the next four distinct candidates were then run **once**
on **2023-07 → 2026-10**, on both spot and futures (with funding).

The run had 6 model families, 244 candidates (211 valid) and cost **$3.96**. It stopped early when the
OpenRouter account ran out of credit.

## Guards against "cheap compute finds noise"

- **Locked holdout.** Candidates only ever see data up to the end of the search window; the panel is cut there.
- **Look-ahead check.** Every candidate is re-run on truncated history and rejected if any past position
  changes. This catches `shift(-1)`, centred windows, `bfill` and full-sample statistics.
- **Anonymous data.** Coins are anonymised (except BTC) and rows are a day counter. Year literals and
  calendar attributes are rejected, so code cannot hard-code dates or famous crashes.
- **Consistency score.** Score = mean − 0.5 × std of Sharpe in 6 cells (2 disjoint coin halves × 3 market
  periods).
- **Overfitting statistics.** The deflated Sharpe and PBO count every valid trial.

## Holdout, 2023-07-01 → 2026-10-12 (1,200 days, never seen during the search)

| | search Sharpe | spot Sharpe | spot CAGR | spot maxDD | futures Sharpe | futures CAGR | futures maxDD |
|---|---|---|---|---|---|---|---|
| **c0238 pick**, shock-cooled chandelier ensemble | 2.19 | **0.86** | +10.5% | **−14.5%** | **0.74** | +8.8% | −15.1% |
| c0199 per-coin drawdown exit + regime hysteresis | 1.87 | 0.72 | +8.8% | −17.5% | 0.62 | +7.3% | −17.0% |
| c0155 vol-targeted, absolute-momentum veto | 1.80 | **0.89** | +10.2% | −15.5% | 0.74 | +8.0% | −14.2% |
| c0228 blended parents | 1.83 | 0.34 | +2.8% | −14.8% | 0.33 | +2.7% | −14.8% |
| c0089 breadth-sized bull longs | 1.67 | 0.34 | +3.3% | −14.8% | 0.33 | +3.3% | −15.6% |
| buy-and-hold, 43 coins equal weight | 0.64 | 0.44 | +7.5% | −75.9% | 0.42 | +7.0% | −71.1% |
| Donchian 20 (earlier best rule) | 0.89 | 0.52 | +14.5% | −55.1% | 0.44 | +10.2% | −54.5% |
| EMA trend (live paper since 14 Oct) | 0.78 | 0.40 | +7.5% | −51.0% | 0.35 | +5.7% | −49.0% |
| BTC hold | – | **0.88** | **+35.1%** | −53.0% | 0.88 | +35.1% | −53.0% |

The pick holds only ~18% gross exposure on average. Sizing it up puts the idle cash to work without any
exchange leverage:

| c0238 holdout, spot | Sharpe | CAGR | total | maxDD |
|---|---|---|---|---|
| ×1 | 0.86 | +10.5% | +39% | −14.5% |
| ×2 | 0.86 | +20.2% | +83% | −27.3% |
| ×3 | 0.82 | +25.6% | +112% | −37.5% |
| BTC hold | 0.88 | +35.1% | +169% | −53.0% |

## Does the search find something real?

On the holdout, evaluated for every valid candidate as a diagnostic (not used for picking):

- The search score predicts holdout Sharpe with a rank correlation of **0.57**. If the search were pure noise
  this would be about 0.
- The top 10% by search score have a median holdout Sharpe of **0.81**, against 0.58 for all candidates.
  **All of them** beat buy-and-hold's 0.44.
- The decay is large: the pick's Sharpe fell from **2.19 → 0.86**. The deflated-Sharpe probability is 0.70
  (luck threshold 1.98 for 211 trials) and PBO is 16%.

## Verdict

- **Real, but smaller than the search said.** The discovered strategies roughly doubled the risk-adjusted
  return of the 43-coin basket (Sharpe 0.86 vs 0.44) and of the old rules (0.40–0.52) on unseen data. Their
  drawdowns were 15% instead of 50–76%.
- **They did not beat holding BTC.** The holdout was BTC-led, with altcoins lagging. The pick matched BTC's
  Sharpe (0.86 vs 0.88), but even at ×3 it returned +112% vs BTC's +169%. Its advantage is a much smaller
  drawdown.
- **Simpler is as good.** The winning family is relative momentum with a BTC-regime switch and trailing
  stops. The pick is heavily evolved (about 150 lines). The simpler c0155 did as well on the holdout and is
  the one to prefer.

Reproduce: `cryptofutures discover --out results/discovery_main` then `cryptofutures discover-report --out
results/discovery_main`. All candidates with code and scores are in `candidates.jsonl`; finalists are in
`finalists/`. Paper-trade one with `cryptofutures paper-portfolio --code results/sample/discovery/finalists/c0155.py`.
