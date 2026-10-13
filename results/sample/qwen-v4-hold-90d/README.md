# Hold-position prompt (v4) on Qwen3.6-27B, 10 coins, 90 days (13 Jul → 11 Oct 2026), daily

v4 adds HOLD ("keep whatever position is open"), tells the model to let trends run (pullbacks are HOLD, not FLAT),
and asks for wider stops (2–3× ATR) with targets at least 3× the stop. 899 of 900 answers (1 failed → FLAT); ~$5.10.

| | v2 (re-decide daily) | **v4 (hold)** | buy-and-hold 1x |
|---|---|---|---|
| return | +5.0% | **+19.1%** | +28.5% |
| Sharpe | 0.85 | 1.95 | 2.90 |
| max drawdown | −8.2% | −11.3% | −10.4% |
| profit factor | 1.19 | 1.75 | – |
| avg holding time | 2.5 days | 7.1 days | whole period |
| calls LONG / SHORT / HOLD / FLAT | 220 / 34 / – / 646 | 264 / 70 / 427 / 139 | – |
| timing p-value (200 shuffles) | 0.64 | 0.28 | – |
| beats B&H in random 30-day windows | 25% | 38% | – |
| median excess vs B&H in those windows | −5.6 pts | −1.1 pts | 0 |

- Holding fixed the "sitting out the rally" problem and nearly quadrupled the return.
- Shuffled versions of v4's own calls still make +14.5% on median, so most of the gain comes from the
  trading style (staying in positions longer), not from better-than-random timing. Timing is not significant yet.
- Buy-and-hold remains the champion for this setup.
