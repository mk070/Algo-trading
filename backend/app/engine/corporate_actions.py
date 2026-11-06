import datetime
import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

# Verified Corporate Actions Master for Tracked Universe Equities (2020 - 2026)
# Sources: Official NSE/BSE corporate action circular filings & SEC corporate action disclosures.
# ratio: multiplier on shares (prices prior to ex_date are divided by ratio; volume multiplied by ratio)
VERIFIED_SPLITS: Dict[str, List[Dict]] = {
    # -------------------------------------------------------------
    # Indian Equities (NSE)
    # -------------------------------------------------------------
    "TATASTEEL": [
        {"ex_date": datetime.date(2022, 7, 28), "ratio": 10.0, "type": "SPLIT", "detail": "10:1 split (FV 10 to 1)"}
    ],
    "RELIANCE": [
        {"ex_date": datetime.date(2024, 10, 28), "ratio": 2.0, "type": "BONUS", "detail": "1:1 bonus issue"}
    ],
    "NESTLEIND": [
        {"ex_date": datetime.date(2024, 1, 5), "ratio": 10.0, "type": "SPLIT", "detail": "10:1 split (FV 10 to 1)"}
    ],
    "BAJAJFINSV": [
        {"ex_date": datetime.date(2022, 9, 13), "ratio": 5.0, "type": "SPLIT", "detail": "5:1 split (FV 5 to 1)"}
    ],
    "EICHERMOT": [
        {"ex_date": datetime.date(2020, 8, 24), "ratio": 10.0, "type": "SPLIT", "detail": "10:1 split (FV 10 to 1)"}
    ],
    "DIXON": [
        {"ex_date": datetime.date(2021, 3, 18), "ratio": 5.0, "type": "SPLIT", "detail": "5:1 split (FV 10 to 2)"}
    ],
    "BEL": [
        {"ex_date": datetime.date(2022, 9, 15), "ratio": 3.0, "type": "BONUS", "detail": "2:1 bonus issue"}
    ],
    "BPCL": [
        {"ex_date": datetime.date(2024, 6, 21), "ratio": 2.0, "type": "BONUS", "detail": "1:1 bonus issue"}
    ],
    "PERSISTENT": [
        {"ex_date": datetime.date(2024, 3, 28), "ratio": 2.0, "type": "SPLIT", "detail": "2:1 split (FV 10 to 5)"}
    ],
    "DRREDDY": [
        {"ex_date": datetime.date(2024, 10, 28), "ratio": 5.0, "type": "SPLIT", "detail": "5:1 split (FV 5 to 1)"}
    ],
    "IRCTC": [
        {"ex_date": datetime.date(2021, 10, 28), "ratio": 5.0, "type": "SPLIT", "detail": "5:1 split (FV 10 to 2)"}
    ],
    "POWERGRID": [
        {"ex_date": datetime.date(2021, 7, 29), "ratio": 1.3333333333333333, "type": "BONUS", "detail": "1:3 bonus issue"},
        {"ex_date": datetime.date(2023, 9, 12), "ratio": 1.3333333333333333, "type": "BONUS", "detail": "1:3 bonus issue"},
    ],
    "ASTRAL": [
        {"ex_date": datetime.date(2021, 3, 18), "ratio": 1.3333333333333333, "type": "BONUS", "detail": "1:3 bonus issue"},
        {"ex_date": datetime.date(2023, 3, 14), "ratio": 1.3333333333333333, "type": "BONUS", "detail": "1:3 bonus issue"},
    ],
    "WIPRO": [
        {"ex_date": datetime.date(2024, 12, 3), "ratio": 2.0, "type": "BONUS", "detail": "1:1 bonus issue"}
    ],

    # -------------------------------------------------------------
    # US Equities (NYSE / NASDAQ)
    # -------------------------------------------------------------
    "NVDA": [
        {"ex_date": datetime.date(2024, 6, 10), "ratio": 10.0, "type": "SPLIT", "detail": "10:1 stock split"},
        {"ex_date": datetime.date(2021, 7, 20), "ratio": 4.0, "type": "SPLIT", "detail": "4:1 stock split"},
    ],
    "TSLA": [
        {"ex_date": datetime.date(2022, 8, 25), "ratio": 3.0, "type": "SPLIT", "detail": "3:1 stock split"},
        {"ex_date": datetime.date(2020, 8, 31), "ratio": 5.0, "type": "SPLIT", "detail": "5:1 stock split"},
    ],
    "AMZN": [
        {"ex_date": datetime.date(2022, 6, 6), "ratio": 20.0, "type": "SPLIT", "detail": "20:1 stock split"}
    ],
    "GOOGL": [
        {"ex_date": datetime.date(2022, 7, 18), "ratio": 20.0, "type": "SPLIT", "detail": "20:1 stock split"}
    ],
    "GOOG": [
        {"ex_date": datetime.date(2022, 7, 18), "ratio": 20.0, "type": "SPLIT", "detail": "20:1 stock split"}
    ],
    "AAPL": [
        {"ex_date": datetime.date(2020, 8, 31), "ratio": 4.0, "type": "SPLIT", "detail": "4:1 stock split"}
    ],
    "WMT": [
        {"ex_date": datetime.date(2024, 2, 26), "ratio": 3.0, "type": "SPLIT", "detail": "3:1 stock split"}
    ],
    "DECK": [
        {"ex_date": datetime.date(2024, 9, 17), "ratio": 6.0, "type": "SPLIT", "detail": "6:1 stock split"}
    ],
    "WSM": [
        {"ex_date": datetime.date(2024, 7, 9), "ratio": 2.0, "type": "SPLIT", "detail": "2:1 stock split"}
    ],
}


def apply_verified_corporate_actions(
    df: pd.DataFrame, symbol: str, market: str = "IN"
) -> Tuple[pd.DataFrame, bool]:
    """Applies verified split and bonus adjustments across all 4 OHLC price points and volume.
    
    Mathematical Invariants:
    1. For every split with ratio S at ex_date:
       For all t < ex_date:
         O_adj = O / S
         H_adj = H / S
         L_adj = L / S
         C_adj = C / S
         V_adj = V * S
    2. Proportionality is strictly preserved:
       (H - L) / (H_adj - L_adj) == S
       (C - O) / (C_adj - O_adj) == S
    3. Dividend adjustments are isolated in dividend_factor and never mutate chart levels.
    """
    if df.empty or "date" not in df.columns:
        return df, False

    df = df.copy()
    sym_clean = symbol.replace("NSE:", "").replace("BSE:", "").strip().upper()
    actions = VERIFIED_SPLITS.get(sym_clean, [])

    # Initialize columns if not present
    if "split_adj_open" not in df.columns:
        df["split_adj_open"] = df["open"].astype(float)
    if "split_adj_high" not in df.columns:
        df["split_adj_high"] = df["high"].astype(float)
    if "split_adj_low" not in df.columns:
        df["split_adj_low"] = df["low"].astype(float)
    if "split_adj_close" not in df.columns:
        df["split_adj_close"] = df["close"].astype(float)
    if "dividend_factor" not in df.columns:
        df["dividend_factor"] = 1.0
    if "is_split_adjusted" not in df.columns:
        df["is_split_adjusted"] = True
    if "volume" in df.columns:
        df["volume"] = df["volume"].astype(float)

    if not actions:
        # No verified split in master; prices remain 1:1
        return df, False

    dates = pd.to_datetime(df["date"]).dt.date

    for action in actions:
        ex_d = action["ex_date"]
        ratio = float(action["ratio"])
        if ratio <= 1.0:
            continue

        mask_before = dates < ex_d
        mask_after = dates >= ex_d
        if not mask_before.any():
            continue

        # Inspect split_adj_close across the ex_date boundary if both sides exist.
        # If the series is already split-adjusted (either by the provider or a previous run),
        # then C_pre / C_post will be ~1.0 (normal market day return).
        # If unadjusted, C_pre / C_post will be approximately equal to ratio.
        if mask_after.any():
            c_pre = float(df.loc[mask_before, "split_adj_close"].iloc[-1])
            c_post = float(df.loc[mask_after, "split_adj_close"].iloc[0])
            observed_ratio = (c_pre / c_post) if c_post > 0 else 1.0
            if observed_ratio < (ratio * 0.65):
                logger.debug(
                    f"{symbol} corporate action {action['type']} ({ratio}:1) at {ex_d} is ALREADY split-adjusted (obs ratio: {observed_ratio:.2f}). Skipping double adjustment."
                )
                continue

        df.loc[mask_before, "split_adj_open"] = round(df.loc[mask_before, "split_adj_open"] / ratio, 4)
        df.loc[mask_before, "split_adj_high"] = round(df.loc[mask_before, "split_adj_high"] / ratio, 4)
        df.loc[mask_before, "split_adj_low"] = round(df.loc[mask_before, "split_adj_low"] / ratio, 4)
        df.loc[mask_before, "split_adj_close"] = round(df.loc[mask_before, "split_adj_close"] / ratio, 4)
        if "volume" in df.columns:
            df.loc[mask_before, "volume"] = round(df.loc[mask_before, "volume"] * ratio, 2)
        logger.info(
            f"Applied verified {action['type']} ({ratio}:1) to {symbol} before {ex_d} on {mask_before.sum()} historical bars."
        )

    # Compute dividend factor if adj_close is available from provider
    if "adj_close" in df.columns:
        safe_split_close = df["split_adj_close"].replace(0, 1.0)
        df["dividend_factor"] = (df["adj_close"] / safe_split_close).round(4)

    return df, True
