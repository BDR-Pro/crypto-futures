# c0199 Per-Coin Drawdown Exit With Regime Hysteresis (z-ai/glm-5.3-flash)
# The parent's weakest cell (P1 top-phase) suffers because longs exit only on slow MAs. Adding a per-coin trailing drawdown exit cuts individual losers early (coins topping before BTC), and adding hysteresis to the BTC regime avoids whipsaw exits/re-entries that hurt the bear/recovery cell.
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
