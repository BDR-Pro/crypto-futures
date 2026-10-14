# c0228 Blend Parents With Agreement Amplification (z-ai/glm-5.3-flash)
# The two parents share the same core (vol-adjusted cross-sectional momentum with BTC regime gates and chandelier exits) but differ in their defensive sleeves. Averaging them diversifies sleeve-specific noise, and amplifying positions where the books agree (consensus) while damping disagreements should raise Sharpe without adding new parameters that could overfit.
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
