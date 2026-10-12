"""Market data: historical USD-M futures klines + funding from Binance Vision, live via ccxt."""
from __future__ import annotations

import io
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

VISION = "https://data.binance.vision/data/futures/um"
KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


def _months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start[:7], end[:7], freq="M")]


def _get_zip_csv(url: str, session: requests.Session, retries: int = 5) -> pd.DataFrame | None:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=60)
            if resp.status_code < 500:
                break
        except requests.RequestException:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        raw = zf.read(zf.namelist()[0])
    first = raw.split(b"\n", 1)[0]
    header = 0 if first[:1].isalpha() else None   # newer files ship a header row
    return pd.read_csv(io.BytesIO(raw), header=header)


def _download_klines(symbol: str, interval: str, months: list[str]) -> pd.DataFrame:
    session = requests.Session()
    frames = []
    for month in months:
        df = _get_zip_csv(f"{VISION}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip", session)
        if df is None:
            # Current month: monthly archive not published yet, fall back to daily files.
            days = pd.date_range(month + "-01", periods=31, freq="D")
            days = [d for d in days if d.strftime("%Y-%m") == month and d < pd.Timestamp.utcnow().tz_localize(None).normalize()]
            for d in days:
                ddf = _get_zip_csv(f"{VISION}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{d:%Y-%m-%d}.zip", session)
                if ddf is not None:
                    ddf.columns = KLINE_COLS
                    frames.append(ddf)
            continue
        df.columns = KLINE_COLS
        frames.append(df)
    if not frames:
        raise RuntimeError(f"no kline data for {symbol} {interval}")
    df = pd.concat(frames, ignore_index=True)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote"]]
    df = df.astype(float)
    return df[~df.index.duplicated()].sort_index()


def _download_funding(symbol: str, months: list[str]) -> pd.DataFrame:
    session = requests.Session()
    frames = []
    for month in months:
        df = _get_zip_csv(f"{VISION}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip", session)
        if df is not None:
            df.columns = ["calc_time", "funding_interval_hours", "last_funding_rate"][: len(df.columns)]
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["rate"], index=pd.DatetimeIndex([], tz="UTC"))
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["calc_time"], unit="ms", utc=True).dt.floor("h")
    out = pd.DataFrame({"rate": df["last_funding_rate"].astype(float).values}, index=ts)
    return out[~out.index.duplicated()].sort_index()


class MarketData:
    """Loads and caches per-symbol hourly candles and funding rates."""

    def __init__(self, data_dir: str | Path, interval: str = "1h"):
        self.dir = Path(data_dir)
        self.interval = interval
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str, kind: str) -> Path:
        return self.dir / f"{symbol}_{kind}.csv.gz"

    def download(self, symbols: list[str], start: str, end: str, force: bool = False) -> None:
        months = _months(start, end)

        def one(sym: str) -> str:
            kpath, fpath = self._path(sym, self.interval), self._path(sym, "funding")
            if force or not kpath.exists():
                self._write(_download_klines(sym, self.interval, months), kpath)
            if force or not fpath.exists():
                self._write(_download_funding(sym, months), fpath)
            return sym

        with ThreadPoolExecutor(max_workers=5) as pool:
            for sym in pool.map(one, symbols):
                log.info("downloaded %s", sym)

    @staticmethod
    def _write(df: pd.DataFrame, path: Path) -> None:
        df.to_csv(path, index_label="time")

    @staticmethod
    def _read(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, index_col="time")
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    def candles(self, symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        path = self._path(symbol, self.interval)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `cryptofutures download` first")
        df = self._read(path)
        return df.loc[start:end] if (start or end) else df

    def funding(self, symbol: str) -> pd.Series:
        path = self._path(symbol, "funding")
        if not path.exists():
            return pd.Series(dtype=float)
        return self._read(path)["rate"]


def fetch_live_candles(exchange, symbol: str, timeframe: str = "1h", limit: int = 1000) -> pd.DataFrame:
    """Fetch recent candles with a ccxt exchange instance. `symbol` is like BTCUSDT."""
    market = to_ccxt_symbol(symbol)
    rows = exchange.fetch_ohlcv(market, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.set_index("time").astype(float)
    df["quote_volume"] = df["volume"] * df["close"]
    df["taker_buy_quote"] = df["quote_volume"] / 2  # not provided by OHLCV endpoint
    return df


def to_ccxt_symbol(symbol: str) -> str:
    base = symbol.removesuffix("USDT")
    return f"{base}/USDT:USDT"
