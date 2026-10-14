# c0089 Breadth-Sized Bull Longs (openai/gpt-6-sol)
# A rising coin is more likely to sustain its advance when gains are widespread across the market. Size the parent’s bull-regime longs with market breadth, while leaving its shorts unchanged so the bear-market protection remains intact.
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
