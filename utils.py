import csv
import os
from datetime import datetime
from pathlib import Path
import pandas as pd

LOG_FILE = 'signal_log.csv'
CACHE_PATH_FORMAT_STR = ".{}.spectr_cache.parquet"

def log(txt):
    print(f"{datetime.now().timestamp()} | {txt}")


def log_signal(symbol, signal, price, text=None):
    if text:
        log(text)
    time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    row = [time_str, symbol, signal, price]
    write_header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(['timestamp', 'symbol', 'signal', 'price'])
        writer.writerow(row)


def save_cache(df, mode):
    if df is not None and not df.empty:
        cache_path = CACHE_PATH_FORMAT_STR.format(mode)
        df.to_parquet(cache_path)
        print(f"[Cache] DataFrame cached to {cache_path}")


def load_cache(mode):
    cache_path = Path(CACHE_PATH_FORMAT_STR.format(mode))
    if cache_path.exists():
        print(f"[Cache] Loading cached DataFrame from {cache_path}")
        return pd.read_parquet(cache_path)
    return None