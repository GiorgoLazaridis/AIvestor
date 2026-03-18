import pandas as pd
import pandas_ta as ta
import config


def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = ta.ema(df["close"], length=config.EMA_FAST)
    df["ema_mid"]  = ta.ema(df["close"], length=config.EMA_MID)
    df["ema_slow"] = ta.ema(df["close"], length=config.EMA_SLOW)
    df["rsi"]      = ta.rsi(df["close"], length=config.RSI_PERIOD)

    macd = ta.macd(df["close"], fast=config.MACD_FAST, slow=config.MACD_SLOW, signal=config.MACD_SIGNAL)
    df["macd"]       = macd[f"MACD_{config.MACD_FAST}_{config.MACD_SLOW}_{config.MACD_SIGNAL}"]
    df["macd_signal"]= macd[f"MACDs_{config.MACD_FAST}_{config.MACD_SLOW}_{config.MACD_SIGNAL}"]
    df["macd_hist"]  = macd[f"MACDh_{config.MACD_FAST}_{config.MACD_SLOW}_{config.MACD_SIGNAL}"]

    df["volume_avg"]   = df["volume"].rolling(config.VOLUME_AVG_PERIOD).mean()
    df["volume_ratio"] = df["volume"] / df["volume_avg"]
    df["atr"]          = ta.atr(df["high"], df["low"], df["close"], length=14)
    return df
