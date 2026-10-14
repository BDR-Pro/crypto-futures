# c0238 Shock-Cooled Chandelier Ensemble (openai/gpt-6-sol)
# Relative momentum and market breadth capture persistent trends, while chandelier exits limit losses when individual coins reverse. Blending two related trend books reduces dependence on either entry rule; a short cooldown after unusually large moves avoids immediately holding positions against a potential regime change.
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
