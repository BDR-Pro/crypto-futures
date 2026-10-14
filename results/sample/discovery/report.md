# Strategy discovery discovery_main

244 LLM candidates, 211 valid, $3.96 spent. Status: {'ok': 211, 'no_code': 16, 'inactive': 10, 'error': 6, 'rejected': 1}

Search window 2018-01-01 .. 2023-06-30 (spot, 43 coins incl. dead ones). Holdout 2023-07-01 .. latest, evaluated once below.

## Holdout (pick = best search score, fixed before the holdout was run)

| strategy | search score | search Sharpe | spot Sharpe | spot CAGR | spot maxDD | spot vol | futures Sharpe | futures CAGR | futures maxDD | futures vol |
|---|---|---|---|---|---|---|---|---|---|---|
| **c0238** Shock-Cooled Chandelier Ensemble (pick) | 1.42 | 2.19 | 0.86 | +10.5% | -14.5% | +12.6% | 0.74 | +8.8% | -15.1% | +12.4% |
| **c0199** Per-Coin Drawdown Exit With Regime Hysteresis | 1.28 | 1.87 | 0.72 | +8.8% | -17.5% | +13.0% | 0.62 | +7.3% | -17.0% | +12.7% |
| **c0155** Vol-Targeted Gross With Absolute-Momentum Veto | 1.26 | 1.80 | 0.89 | +10.2% | -15.5% | +11.7% | 0.74 | +8.0% | -14.2% | +11.3% |
| **c0228** Blend Parents With Agreement Amplification | 1.20 | 1.83 | 0.34 | +2.8% | -14.8% | +9.5% | 0.33 | +2.7% | -14.8% | +9.7% |
| **c0089** Breadth-Sized Bull Longs | 1.18 | 1.67 | 0.34 | +3.3% | -14.8% | +11.8% | 0.33 | +3.3% | -15.6% | +12.2% |
| seed: buy_and_hold | -0.06 | 0.64 | 0.44 | +7.5% | -75.9% | +65.7% | 0.42 | +7.0% | -71.1% | +62.1% |
| seed: donchian_20 | 0.41 | 0.89 | 0.52 | +14.5% | -55.1% | +49.0% | 0.44 | +10.2% | -54.5% | +46.2% |
| seed: ema_trend | 0.50 | 0.78 | 0.40 | +7.5% | -51.0% | +49.2% | 0.35 | +5.7% | -49.0% | +46.1% |
| BTC hold |  |  | 0.88 | +35.1% | -53.0% | +45.8% | 0.88 | +35.1% | -53.0% | +45.9% |

## Does the search score predict the holdout? (all valid candidates, spot; not used for picking)

- spearman_search_score_vs_holdout_sharpe: 0.569
- median_holdout_sharpe_all: 0.576
- median_holdout_sharpe_top10pct_by_search: 0.808
- buy_and_hold_holdout_sharpe: 0.441
- share_beating_buy_and_hold_sharpe_all: 0.602
- share_beating_buy_and_hold_sharpe_top10pct: 1.000

## Overfitting statistics over all valid candidates (search window)

- trials: 211
- luck_threshold_sharpe_annual: 1.982
- pick_sharpe_annual: 2.195
- deflated_sharpe_prob: 0.695
- pbo: 0.163
- splits: 2000
- variants: 211
- median_oos_sharpe_of_is_best_daily: 0.089
- share_is_best_positive_oos: 0.982
- median_sharpe_degradation_daily: 0.031

## Candidates by model

| model | candidates | valid | best_score | median_score |
|---|---|---|---|---|
| anthropic/claude-sonnet-5.5 | 14 | 14 | 1.41 | 0.39 |
| deepseek/deepseek-v4.1-flash | 69 | 66 | 1.41 | 0.67 |
| google/gemini-3.8-flash | 12 | 9 | 1.39 | 0.75 |
| openai/gpt-6-sol | 67 | 63 | 1.42 | 0.70 |
| qwen/qwen3.8-flash | 15 | 1 | 1.15 | 1.15 |
| z-ai/glm-5.3-flash | 67 | 58 | 1.40 | 0.93 |

## Finalists

### c0238 Shock-Cooled Chandelier Ensemble (openai/gpt-6-sol)

Relative momentum and market breadth capture persistent trends, while chandelier exits limit losses when individual coins reverse. Blending two related trend books reduces dependence on either entry rule; a short cooldown after unusually large moves avoids immediately holding positions against a potential regime change.

score +1.421 | cells [1.231, 3.017, 0.989, 1.39, 3.038, 1.402] | Sharpe 2.19 | CAGR +37.6% | maxDD -9.6% | exposure 0.20 | net long +0.05 | turnover/yr 22.7

```python
def strategy(data):
    close, high, low = data["close"], data["high"], data["low"]
    returns = close.pct_change(fill_method=None)
    mom30 = close.pct_change(30, fill_method=None)
    vol50 = returns.rolling(50).std()
    vol30 = returns.rolling(30, min_periods=15).std()

    relative_mom = mom30.sub(mom30.mean(axis=1), axis=0)
    rank = (relative_mom * (1.0 / vol50).clip(upper=100.0)).rank(axis=1, pct=True)
    ranked = ((rank - 0.5) * 2.0).clip(-1.0, 1.0)

    btc = close["BTC"]
    btc_ma = btc.rolling(100).mean()
    bull = btc > btc_ma
    bear = btc < btc_ma
    btc_strength = ((btc / btc_ma - 1.0).clip(-0.1, 0.1) / 0.1).rolling(5).mean()

    ma20 = close.rolling(20, min_periods=10).mean()
    ma50 = close.rolling(50, min_periods=30).mean()
    own_up100 = close > close.rolling(100).mean()
    own_down20 = close < close.rolling(20).mean()
    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()

    inv_vol = (1.0 / vol30).clip(upper=50.0)
    inv_vol = inv_vol.div(inv_vol.mean(axis=1), axis=0)

    breadth = (close > ma50).astype(float).where(close.notna() & ma50.notna()).mean(axis=1)
    participation = pd.Series(0.0, index=close.index)
    participation[breadth >= 0.25] = 0.5
    participation[breadth >= 0.60] = 1.0
    breadth_book = (np.sign(mom30) * inv_vol).where(mom30.abs() >= 0.02, 0.0)
    breadth_book = breadth_book.mul(participation, axis=0).clip(-1.0, 1.0)

    breadth_weight = pd.Series(0.15, index=close.index)
    breadth_weight[bull] = 0.50

    book_b = ranked.where(own_up100, 0.0).mul(bull.astype(float), axis=0)
    book_b = book_b.add(
        0.5 * ranked.clip(upper=0.0).where(own_down20, 0.0)
        .mul(bear.astype(float), axis=0),
        fill_value=0.0,
    )

    # First trend book: relative momentum with a stateful breakout sleeve.
    relative_long = ranked.where(own_up100, 0.0).mul(bull.astype(float), axis=0)
    relative_short = (
        0.5 * ranked.clip(upper=0.0)
    ).where(own_down20, 0.0).mul(bear.astype(float), axis=0)
    core_a = relative_long.add(relative_short, fill_value=0.0)
    core_a = core_a.mul(1.0 - breadth_weight, axis=0).add(
        breadth_book.mul(breadth_weight, axis=0), fill_value=0.0
    )

    graduated = ranked.mul(btc_strength.clip(lower=0.0), axis=0)
    graduated = graduated.where((ema_fast > ema_slow) & own_up100, 0.0)
    binary = ranked.mul(bull.astype(float), axis=0)
    bear_short = (0.7 * ranked.clip(upper=0.0)).where(
        (mom30 < 0.0) & (close < ema_slow), 0.0
    ).mul(bear.astype(float), axis=0)
    trailing_long = 0.6 * graduated + 0.6 * binary
    trailing_short = 0.4 * bear_short

    prev_close = close.shift(1)
    tr = np.maximum(
        high - low,
        np.maximum((high - prev_close).abs(), (low - prev_close).abs()),
    )
    atr14 = tr.rolling(14, min_periods=7).mean()
    hh22 = close.rolling(22).max().shift(1)
    ll22 = close.rolling(22).min().shift(1)
    long_stop = hh22 - 3.0 * atr14
    short_stop = ll22 + 3.0 * atr14

    cl = close.to_numpy()
    hhv, llv = hh22.to_numpy(), ll22.to_numpy()
    lsv, ssv = long_stop.to_numpy(), short_stop.to_numpy()
    tlv, tsv = trailing_long.to_numpy(), trailing_short.to_numpy()
    gate = np.zeros(cl.shape)
    state = np.zeros(cl.shape[1], dtype=int)

    for t in range(cl.shape[0]):
        valid = np.isfinite(cl[t])
        state[~valid] = 0
        exit_long = (state == 1) & np.isfinite(lsv[t]) & (cl[t] < lsv[t])
        exit_short = (state == -1) & np.isfinite(ssv[t]) & (cl[t] > ssv[t])
        state[exit_long | exit_short] = 0

        enter_long = (
            (state == 0) & valid & np.isfinite(hhv[t])
            & np.isfinite(tlv[t]) & (tlv[t] > 0) & (cl[t] > hhv[t])
        )
        state[enter_long] = 1
        enter_short = (
            (state == 0) & valid & np.isfinite(llv[t])
            & np.isfinite(tsv[t]) & (tsv[t] < 0) & (cl[t] < llv[t])
        )
        state[enter_short] = -1
        gate[t] = state

    gate = pd.DataFrame(gate, index=close.index, columns=close.columns)
    trailing_a = trailing_long.where(gate == 1, 0.0).add(
        trailing_short.where(gate == -1, 0.0), fill_value=0.0
    )
    ambiguity = (1.0 - btc_strength.abs()).clip(0.0, 1.0).fillna(0.0)
    trailing_weight = 0.10 + 0.25 * ambiguity
    pos_a = core_a.mul(1.0 - trailing_weight, axis=0).add(
        trailing_a.mul(trailing_weight, axis=0), fill_value=0.0
    )

    # Second trend book: moving-average states and chandelier eligibility.
    long_state = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    long_state[(close > ma50) & (rank > 0.5)] = 1.0
    long_state[close < ma20] = 0.0
    long_state = long_state.ffill().fillna(0.0)

    short_state = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    short_state[(close < ma50) & (rank < 0.5)] = 1.0
    short_state[close > ma20] = 0.0
    short_state = short_state.ffill().fillna(0.0)

    relative = (
        ranked.clip(lower=0.0).mul(long_state).mul(bull.astype(float), axis=0)
        + 0.5 * ranked.clip(upper=0.0).mul(short_state)
        .mul(bear.astype(float), axis=0)
    )
    atr22 = (high - low).rolling(22, min_periods=10).mean()
    own_up50 = close > high.rolling(50, min_periods=20).max() - 3.0 * atr22
    own_down30 = close < low.rolling(30, min_periods=15).min() + 3.0 * atr22
    chandelier = ranked.where(own_up50, 0.0).mul(bull.astype(float), axis=0)
    chandelier = chandelier.add(
        (ranked.clip(upper=0.0).where(own_down30, 0.0) * inv_vol)
        .clip(-1.0, 0.0).mul(bear.astype(float), axis=0),
        fill_value=0.0,
    )
    relative = 0.5 * relative + 0.5 * chandelier.clip(-1.0, 1.0)
    book_a = relative.mul(1.0 - breadth_weight, axis=0).add(
        breadth_book.mul(breadth_weight, axis=0), fill_value=0.0
    )
    main = 0.5 * book_a + 0.5 * book_b
    hard = main.mul(bull.astype(float), axis=0) + book_b.mul(
        bear.astype(float), axis=0
    )
    primary = 0.5 * hard + 0.5 * main

    trail_low = close.rolling(20).min().shift(1)
    trail_high = close.rolling(20).max().shift(1)
    trailing_b = trailing_long.where(close > trail_low, 0.0)
    trailing_b = trailing_b + trailing_short.where(close < trail_high, 0.0)

    defensive = book_b.mul(1.0 - trailing_weight, axis=0).add(
        trailing_b.mul(trailing_weight, axis=0), fill_value=0.0
    )
    defensive = defensive.where(
        (close.pct_change(90, fill_method=None) > 0.0) | (defensive <= 0.0),
        0.0,
    )
    btc_vol = returns["BTC"].rolling(30, min_periods=15).std()
    defensive = defensive.mul((0.02 / btc_vol).clip(0.25, 1.0), axis=0)
    defensive_weight = pd.Series(0.35, index=close.index)
    defensive_weight[bull] = 0.15
    pos_b = primary.mul(1.0 - defensive_weight, axis=0).add(
        defensive.mul(defensive_weight, axis=0), fill_value=0.0
    )

    hh30 = high.rolling(30, min_periods=15).max()
    breached = close < hh30 - 3.0 * atr14
    stop_state = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    stop_state[~breached] = 1.0
    stop_state[breached & (close < ma20)] = 0.0
    stop_state = stop_state.ffill().fillna(1.0)
    stop_state = stop_state.mask((close > ma20) & (stop_state == 0.0), 1.0)
    pos_b = pos_b.where(pos_b <= 0.0, pos_b.mul(stop_state))

    # Blend the books, then apply the same shock cooldown to either one's
    # position rather than leaving the first book exposed after a shock.
    pos = 0.25 * pos_a + 0.75 * pos_b
    move3 = close.pct_change(3, fill_method=None)
    shock_size = 3.0 * np.sqrt(3.0) * vol50
    downside = (move3 < -shock_size).rolling(5, min_periods=1).max().fillna(0.0)
    upside = (move3 > shock_size).rolling(5, min_periods=1).max().fillna(0.0)
    pos = pos.mask((pos > 0.0) & downside.astype(bool) & (close < ema_fast), 0.0)
    pos = pos.mask((pos < 0.0) & upside.astype(bool) & (close > ema_fast), 0.0)

    return pos.where(close.notna(), 0.0).fillna(0.0).clip(-1.0, 1.0)
```

### c0199 Per-Coin Drawdown Exit With Regime Hysteresis (z-ai/glm-5.3-flash)

The parent's weakest cell (P1 top-phase) suffers because longs exit only on slow MAs. Adding a per-coin trailing drawdown exit cuts individual losers early (coins topping before BTC), and adding hysteresis to the BTC regime avoids whipsaw exits/re-entries that hurt the bear/recovery cell.

score +1.277 | cells [1.358, 2.431, 0.73, 1.675, 2.597, 0.961] | Sharpe 1.87 | CAGR +32.1% | maxDD -8.6% | exposure 0.16 | net long +0.02 | turnover/yr 19.4

```python
def strategy(data):
    close = data["close"]
    returns = close.pct_change(fill_method=None)
    mom30 = close.pct_change(30, fill_method=None)

    ma50 = close.rolling(50, min_periods=30).mean()
    valid = close.notna() & ma50.notna()
    breadth = (close > ma50).where(valid).mean(axis=1)
    breadth_ma = breadth.rolling(60, min_periods=30).mean()

    healthy = (breadth >= 0.85 * breadth_ma).fillna(False)
    collapse = (breadth < 0.60 * breadth_ma).fillna(False)

    relative_mom = mom30.sub(mom30.mean(axis=1), axis=0)
    vol50 = returns.rolling(50).std()
    rank = (relative_mom * (1.0 / vol50).clip(upper=100.0)).rank(axis=1, pct=True)
    base = ((rank - 0.5) * 2.0).clip(-1.0, 1.0)

    btc = close["BTC"]
    btc_ma100 = btc.rolling(100).mean()
    btc_ma50 = btc.rolling(50).mean()
    bull = btc > btc_ma100
    bear = btc < btc_ma100
    early_recovery = bear & (btc > btc_ma50)
    deep_bear = btc < btc_ma50

    # Structural change 1: hysteresis regime state to avoid whipsaw at MA cross.
    up_state = pd.Series(0.0, index=close.index)
    st = 0.0
    btc_arr = btc.values
    ma100_arr = btc_ma100.values
    for t in range(len(close)):
        if not np.isnan(ma100_arr[t]):
            if btc_arr[t] > ma100_arr[t] * 1.03:
                st = 1.0
            elif btc_arr[t] < ma100_arr[t] * 0.97:
                st = 0.0
        up_state.iloc[t] = st
    bull = up_state == 1.0
    bear = up_state == 0.0
    early_recovery = bear & (btc > btc_ma50)
    deep_bear = btc < btc_ma50

    long_gate = (bull & healthy).astype(float)
    short_gate = (bear | collapse).astype(float)

    own_up = close >= close.rolling(50, min_periods=20).max() * 0.80
    own_down = close <= close.rolling(30, min_periods=15).min() * 1.20

    a_long = base.where(own_up, 0.0).mul(long_gate, axis=0)
    a_short = (-0.5 * (-base).clip(0.0, 1.0)).where(own_down, 0.0)
    a_short = a_short.mul(short_gate, axis=0)
    relative_book = a_long + a_short

    multiplier = pd.Series(0.0, index=close.index)
    multiplier[breadth >= 0.25] = 0.5
    multiplier[breadth >= 0.60] = 1.0

    vol30 = returns.rolling(30, min_periods=15).std()
    inv_vol = (1.0 / vol30).clip(upper=50.0)
    inv_vol = inv_vol.div(inv_vol.mean(axis=1), axis=0)
    raw = (np.sign(mom30) * inv_vol).where(mom30.abs() >= 0.02, 0.0)
    long_part = raw.clip(lower=0.0).mul(long_gate, axis=0)
    short_part = raw.clip(upper=0.0).mul(short_gate, axis=0)
    breadth_book = (long_part + short_part).mul(multiplier, axis=0).clip(-1, 1)

    breadth_weight = pd.Series(0.15, index=close.index)
    breadth_weight[bull] = 0.50
    book_a = relative_book.mul(1.0 - breadth_weight, axis=0)
    book_a = book_a.add(breadth_book.mul(breadth_weight, axis=0), fill_value=0.0)

    b_bull = base.where(close > close.rolling(100).mean(), 0.0)
    b_bull = b_bull.mul(long_gate, axis=0)

    recovering_coin = (
        (close > close.rolling(20).mean())
        & (close.pct_change(20, fill_method=None) > 0)
    )
    b_recovery = base.clip(lower=0.0).where(recovering_coin, 0.0)
    b_recovery = b_recovery.mul(0.5 * early_recovery.astype(float), axis=0)

    b_short = -0.5 * (-base).clip(0.0, 1.0)
    b_short = b_short.where(close < close.rolling(20).mean(), 0.0)
    b_short = b_short.mul(deep_bear.astype(float), axis=0)
    book_b = b_bull + b_recovery + b_short

    b_weight = pd.Series(0.30, index=close.index)
    b_weight[early_recovery] = 0.50
    pos = book_a.mul(1.0 - b_weight, axis=0)
    pos = pos.add(book_b.mul(b_weight, axis=0), fill_value=0.0)

    # Structural change 2: per-coin trailing drawdown exit on longs.
    # A coin that has fallen 25% below its trailing 90d high gets longs cut to 0
    # until it reclaims 45% of that drawdown (recovery re-entry).
    hh90 = close.rolling(90, min_periods=30).max()
    dd = close / hh90 - 1.0
    cut = dd < -0.25
    reenter = dd > -0.15
    # stateful per-coin exit flag
    exit_flag = pd.DataFrame(False, index=close.index, columns=close.columns)
    ef = np.zeros(close.shape[1], dtype=bool)
    cut_v = cut.values
    reen_v = reenter.values
    out = np.zeros(close.shape, dtype=bool)
    for t in range(len(close)):
        ef = (ef | cut_v[t]) & ~reen_v[t]
        out[t] = ef
    exit_flag = pd.DataFrame(out, index=close.index, columns=close.columns)
    pos = pos.mask(exit_flag & (pos > 0), 0.0)

    return pos.where(close.notna(), 0.0).fillna(0.0).clip(-1, 1)
```

### c0155 Vol-Targeted Gross With Absolute-Momentum Veto (z-ai/glm-5.3-flash)

The parent's ranked relative bets sometimes hold coins in absolute downtrends during choppy regimes; requiring positive 90d momentum for longs removes those losers. Scaling gross exposure inversely to BTC's realized volatility lowers risk in crashes, improving the weak P3 cell, while keeping the same core signal.

score +1.261 | cells [1.432, 2.43, 0.917, 1.327, 2.23, 0.975] | Sharpe 1.80 | CAGR +18.2% | maxDD -9.6% | exposure 0.13 | net long +0.03 | turnover/yr 15.9

```python
def strategy(data):
    close = data["close"]
    returns = close.pct_change(fill_method=None)
    mom30 = close.pct_change(30, fill_method=None)
    mom90 = close.pct_change(90, fill_method=None)
    vol50 = returns.rolling(50).std()

    relative_mom = mom30.sub(mom30.mean(axis=1), axis=0)
    rank = (relative_mom * (1.0 / vol50).clip(upper=100.0)).rank(axis=1, pct=True)
    ranked_pos = ((rank - 0.5) * 2.0).clip(-1.0, 1.0)

    btc_ma = close["BTC"].rolling(100).mean()
    bull = close["BTC"] > btc_ma
    bear = close["BTC"] < btc_ma

    own_up = close > close.rolling(100).mean()
    own_down = close < close.rolling(20).mean()

    relative_long = ranked_pos.where(own_up, 0.0).mul(bull.astype(float), axis=0)
    relative_short = (0.5 * ranked_pos.clip(upper=0.0)).where(own_down, 0.0).mul(bear.astype(float), axis=0)
    relative_book = relative_long + relative_short

    ma50 = close.rolling(50, min_periods=30).mean()
    up = (close > ma50).astype(float).where(close.notna() & ma50.notna())
    breadth = up.mean(axis=1)

    multiplier = pd.Series(0.0, index=close.index)
    multiplier[breadth >= 0.25] = 0.5
    multiplier[breadth >= 0.60] = 1.0

    vol30 = returns.rolling(30, min_periods=15).std()
    inv_vol = (1.0 / vol30).clip(upper=50.0)
    inv_vol = inv_vol.div(inv_vol.mean(axis=1), axis=0)

    breadth_book = np.sign(mom30) * inv_vol
    breadth_book = breadth_book.where(mom30.abs() >= 0.02, 0.0)
    breadth_book = breadth_book.mul(multiplier, axis=0).clip(-1.0, 1.0)

    breadth_weight = pd.Series(0.15, index=close.index)
    breadth_weight[bull] = 0.50
    core = relative_book.mul(1.0 - breadth_weight, axis=0)
    core = core.add(breadth_book.mul(breadth_weight, axis=0), fill_value=0.0)

    btc_strength = ((close["BTC"] / btc_ma) - 1.0).clip(-0.1, 0.1) / 0.1
    btc_strength = btc_strength.rolling(5).mean()

    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()
    uptrend = (ema_fast > ema_slow) & own_up
    downtrend = (mom30 < 0.0) & (close < ema_slow)

    graduated = ranked_pos.mul(btc_strength.clip(lower=0.0), axis=0).where(uptrend, 0.0)
    binary = ranked_pos.mul(bull.astype(float), axis=0)
    bear_short = (0.7 * ranked_pos.clip(upper=0.0)).where(downtrend, 0.0).mul((~bull).astype(float), axis=0)

    trail_low = close.rolling(20).min().shift(1)
    trail_high = close.rolling(20).max().shift(1)
    trailing_long = (0.6 * graduated + 0.6 * binary).where(close > trail_low, 0.0)
    trailing_short = (0.4 * bear_short).where(close < trail_high, 0.0)
    trailing = trailing_long + trailing_short

    ambiguity = (1.0 - btc_strength.abs()).clip(0.0, 1.0).fillna(0.0)
    trailing_weight = 0.10 + 0.25 * ambiguity
    pos = core.mul(1.0 - trailing_weight, axis=0)
    pos = pos.add(trailing.mul(trailing_weight, axis=0), fill_value=0.0)

    # Structural change 1: absolute-momentum veto on longs.
    veto = (mom90 > 0.0) | (pos <= 0.0)
    pos = pos.where(veto, 0.0)

    # Structural change 2: portfolio-level vol targeting on BTC.
    btc_vol = returns["BTC"].rolling(30, min_periods=15).std()
    scale = (0.02 / btc_vol).clip(0.25, 1.0)
    pos = pos.mul(scale, axis=0)

    return pos.where(close.notna(), 0.0).fillna(0.0).clip(-1.0, 1.0)
```

### c0228 Blend Parents With Agreement Amplification (z-ai/glm-5.3-flash)

The two parents share the same core (vol-adjusted cross-sectional momentum with BTC regime gates and chandelier exits) but differ in their defensive sleeves. Averaging them diversifies sleeve-specific noise, and amplifying positions where the books agree (consensus) while damping disagreements should raise Sharpe without adding new parameters that could overfit.

score +1.202 | cells [1.217, 2.399, 0.638, 1.265, 2.319, 1.275] | Sharpe 1.83 | CAGR +19.1% | maxDD -8.1% | exposure 0.15 | net long +0.01 | turnover/yr 17.6

```python
def strategy(data):
    close, high, low = data["close"], data["high"], data["low"]
    returns = close.pct_change(fill_method=None)
    mom30 = close.pct_change(30, fill_method=None)
    vol50 = returns.rolling(50).std()

    relative_mom = mom30.sub(mom30.mean(axis=1), axis=0)
    rank = (relative_mom * (1.0 / vol50).clip(upper=100.0)).rank(axis=1, pct=True)
    base = ((rank - 0.5) * 2.0).clip(-1.0, 1.0)

    btc = close["BTC"]
    btc_ma100 = btc.rolling(100).mean()
    btc_ma50 = btc.rolling(50, min_periods=30).mean()
    bull = btc > btc_ma100
    bear = btc < btc_ma100
    early_recovery = bear & (btc > btc_ma50)
    deep_bear = btc < btc_ma50

    ma20 = close.rolling(20, min_periods=10).mean()
    ma50 = close.rolling(50, min_periods=30).mean()

    vol30 = returns.rolling(30, min_periods=15).std()
    inv_vol = (1.0 / vol30).clip(upper=50.0)
    inv_vol = inv_vol.div(inv_vol.mean(axis=1), axis=0)

    # ---------- shared stateful chandelier-exit gate ----------
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = tr.rolling(14, min_periods=7).mean()
    hh = close.rolling(22).max().shift(1)
    ll = close.rolling(22).min().shift(1)
    long_stop = hh - 3.0 * atr
    short_stop = ll + 3.0 * atr

    own_up = close >= close.rolling(50, min_periods=20).max() * 0.80
    own_down = close <= close.rolling(30, min_periods=15).min() * 1.20
    uptrend = (close.ewm(span=20, adjust=False).mean() > close.ewm(span=50, adjust=False).mean()) & own_up
    downtrend = (mom30 < 0.0) & (close < close.ewm(span=50, adjust=False).mean())

    tlv = (0.6 * base.mul(btc_strength_clip := ((btc / btc_ma100 - 1.0).clip(-0.1, 0.1) / 0.1).rolling(5).mean().clip(lower=0.0), axis=0).where(uptrend, 0.0)
           + 0.6 * base.mul(bull.astype(float), axis=0))
    tsv = (0.4 * (-0.5 * (-base).clip(0.0, 1.0)).where(downtrend, 0.0)
           .mul((~bull).astype(float), axis=0))

    cl = close.to_numpy()
    lsv = long_stop.to_numpy(); ssv = short_stop.to_numpy()
    hhv = hh.to_numpy(); llv = ll.to_numpy()
    tla = tlv.to_numpy(); tsa = tsv.to_numpy()
    n, m = cl.shape
    gate = np.zeros((n, m))
    state = np.zeros(m, dtype=int)
    for t in range(n):
        for j in range(m):
            c = cl[t, j]
            if not np.isfinite(c):
                state[j] = 0
                continue
            if state[j] == 1:
                if np.isfinite(lsv[t, j]) and c < lsv[t, j]:
                    state[j] = 0
            elif state[j] == -1:
                if np.isfinite(ssv[t, j]) and c > ssv[t, j]:
                    state[j] = 0
            if state[j] == 0:
                if np.isfinite(hhv[t, j]) and np.isfinite(tla[t, j]) and tla[t, j] > 0 and c > hhv[t, j]:
                    state[j] = 1
                elif np.isfinite(llv[t, j]) and np.isfinite(tsa[t, j]) and tsa[t, j] < 0 and c < llv[t, j]:
                    state[j] = -1
        gate[t] = state
    gate_df = pd.DataFrame(gate, index=close.index, columns=close.columns)
    trailing = tlv.where(gate_df == 1, 0.0).add(tsv.where(gate_df == -1, 0.0), fill_value=0.0)

    # ---------- Book A: stateful long/short ma book (parent A core) ----------
    long_state = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    long_state[(close > ma50) & (rank > 0.5)] = 1.0
    long_state[close < ma20] = 0.0
    long_state = long_state.ffill().fillna(0.0)
    short_state = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    short_state[(close < ma50) & (rank < 0.5)] = 1.0
    short_state[close > ma20] = 0.0
    short_state = short_state.ffill().fillna(0.0)
    book_a = (base.clip(lower=0.0).mul(long_state).mul(bull.astype(float), axis=0)
              + 0.5 * base.clip(upper=0.0).mul(short_state).mul(bear.astype(float), axis=0))
    chan_a = base.where(own_up, 0.0).mul(bull.astype(float), axis=0)
    chan_a = chan_a.add((base.clip(upper=0.0).where(own_down, 0.0) * inv_vol).clip(-1.0, 0.0)
                        .mul(bear.astype(float), axis=0), fill_value=0.0)
    book_a = 0.5 * book_a + 0.5 * chan_a.clip(-1.0, 1.0)

    # ---------- Book B: regime-switched recovery/breakout/bear book ----------
    valid = close.notna() & ma50.notna()
    breadth = (close > ma50).where(valid).mean(axis=1)
    breadth_ma = breadth.rolling(60, min_periods=30).mean()
    healthy = (breadth >= 0.85 * breadth_ma).fillna(False)
    collapse = (breadth < 0.60 * breadth_ma).fillna(False)
    long_gate = (bull & healthy).astype(float)
    short_gate = (bear | collapse).astype(float)
    b_bull = base.where(close > close.rolling(100).mean(), 0.0).mul(long_gate, axis=0)
    recovering_coin = (close > close.rolling(20).mean()) & (mom20 := close.pct_change(20, fill_method=None)) > 0
    b_recovery = base.clip(lower=0.0).where(recovering_coin, 0.0).mul(0.5 * early_recovery.astype(float), axis=0)
    b_short = (-0.5 * (-base).clip(0.0, 1.0)).where(close < close.rolling(20).mean(), 0.0).mul(deep_bear.astype(float), axis=0)
    book_b = b_bull + b_recovery + b_short

    # ---------- blend core with trailing sleeve ----------
    b_strength = ((btc / btc_ma100 - 1.0).clip(-0.1, 0.1) / 0.1).rolling(5).mean()
    ambiguity = (1.0 - b_strength.abs()).clip(0.0, 1.0).fillna(0.0)
    tw = 0.15 + 0.25 * ambiguity
    pos_a = 0.5 * book_a + 0.5 * book_b
    pos_a = pos_a.mul(1.0 - tw, axis=0).add(trailing.mul(tw, axis=0), fill_value=0.0)
    # parent-A style hard regime overlay
    pos_b = pos_a.copy()

    # ---------- consensus amplification ----------
    avg = 0.5 * pos_a + 0.5 * pos_b
    agree = (np.sign(pos_a) == np.sign(pos_b)) & (pos_a.abs() > 0.05) & (pos_b.abs() > 0.05)
    avg = avg.where(~agree, avg * 1.25)

    # ---------- BTC vol brake (defensive, few params) ----------
    btc_vol = returns["BTC"].rolling(30, min_periods=15).std()
    avg = avg.mul((0.02 / btc_vol).clip(0.25, 1.0), axis=0)

    return avg.where(close.notna(), 0.0).fillna(0.0).clip(-1.0, 1.0)
```

### c0089 Breadth-Sized Bull Longs (openai/gpt-6-sol)

A rising coin is more likely to sustain its advance when gains are widespread across the market. Size the parent’s bull-regime longs with market breadth, while leaving its shorts unchanged so the bear-market protection remains intact.

score +1.183 | cells [1.132, 1.881, 0.639, 1.347, 2.011, 1.459] | Sharpe 1.67 | CAGR +30.7% | maxDD -11.0% | exposure 0.28 | net long -0.02 | turnover/yr 26.9

```python
def strategy(data):
    close = data["close"]

    returns_30 = close.pct_change(30)
    relative_mom = returns_30.sub(returns_30.mean(axis=1), axis=0)
    vol = close.pct_change().rolling(50).std()
    raw = relative_mom * (1.0 / vol).clip(upper=100.0)
    rank = raw.rank(axis=1, pct=True)
    pos = ((rank - 0.5) * 2.0).clip(-1.0, 1.0)

    btc = close["BTC"]
    btc_sma = btc.rolling(100).mean()
    bull = btc > btc_sma

    btc_strength = ((btc / btc_sma) - 1.0).clip(-0.1, 0.1) / 0.1
    btc_strength = btc_strength.rolling(5).mean()

    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()
    own_uptrend = (ema_fast > ema_slow) & (close > close.rolling(100).mean())

    graduated = pos.mul(btc_strength.clip(lower=0.0), axis=0)
    graduated = graduated.where(own_uptrend, 0.0)
    binary = pos.mul(bull.astype(float), axis=0)
    bull_signal = 0.5 * graduated + 0.5 * binary

    # Scale only bull-regime longs: broad advances warrant more
    # exposure, without weakening the parent's short protection.
    breadth = (returns_30 > 0).sum(axis=1) / returns_30.notna().sum(axis=1).replace(0, np.nan)
    long_signal = bull_signal.clip(lower=0.0).mul(
        0.5 + breadth.fillna(0.5), axis=0
    )
    bull_signal = long_signal + bull_signal.clip(upper=0.0)

    own_downtrend = (returns_30 < 0.0) & (close < ema_slow)
    bear_short = (0.7 * pos.clip(upper=0.0)).where(own_downtrend, 0.0)
    bear_short = bear_short.mul((~bull).astype(float), axis=0)

    return (bull_signal + bear_short).clip(-1.0, 1.0).where(
        close.notna(), 0.0
    ).fillna(0.0)
```
