# Leverage sweep, 10 coins, 90 days (13 Jul → 11 Oct 2026), from cached decisions (no API cost)

`cryptofutures leverage` forces one leverage on every trade, under three ways of handling the liquidation price:
`reduce_leverage` (keep the stop, lower leverage until the stop sits inside liquidation; the effective cap is ~25x),
`tighten_stop` (keep the leverage, pull the stop in front of liquidation: ~0.3% at 100x),
`off` (keep both; liquidation can hit first and takes the whole margin).
Each position posts 8% of equity as margin, so 10x on 10 coins is up to 8x the account in exposure.

| leverage | Qwen v4 (hold) | Qwen v2 | buy-and-hold |
|---|---|---|---|
| 1x | +8.4% (DD −9%) | +1.1% (DD −4%) | +28.5% (DD −10%) |
| 2x | +15.3% (DD −16%) | +1.8% (DD −8%) | +57.0% (DD −17%) |
| 3x | +20.7% (DD −24%) | +2.1% (DD −12%) | +85.4% (DD −22%) |
| 5x | **+26.2%** (DD −38%) | +1.7% (DD −20%) | +142.3% (DD −28%) |
| 10x | +6.2% (DD −68%) | −5.1% (DD −38%) | +284.1% (DD −36%) |
| 20x, guard off | −54.2%, 23 liquidations | −44.7%, 25 liquidations | +257.7%, 6 liquidations |
| 50x, guard off | −99.6%, blown up | −100%, blown up | −5.4%, equity fell to 12% |
| 100x, guard off | −100%, blown up | −100%, blown up | +93.3%, but equity fell to 10% first |
| 50–100x, tighten_stop | −98.7% to −99.3% (0.3–1% stops hit constantly) | −90% to −99% | – |

- Up to about 5x, leverage scales the models' results; past 10x it destroys them.
- At 50–100x every strategy blows up or nearly does. Buy-and-hold's 100x "+93%" came after the account first fell
  to 10%: survival there was luck, not a strategy.
- Qwen chooses its own leverage better than any fixed level for v2 (+5.0% with its own choices vs at best +2.1%).
- Leveraged buy-and-hold wins hugely only because this quarter went up; leverage amplifies the market, not skill.
