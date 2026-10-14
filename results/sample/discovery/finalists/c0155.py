# c0155 Vol-Targeted Gross With Absolute-Momentum Veto (z-ai/glm-5.3-flash)
# The parent's ranked relative bets sometimes hold coins in absolute downtrends during choppy regimes; requiring positive 90d momentum for longs removes those losers. Scaling gross exposure inversely to BTC's realized volatility lowers risk in crashes, improving the weak P3 cell, while keeping the same core signal.
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
