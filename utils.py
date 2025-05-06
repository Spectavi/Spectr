import csv
import os
from datetime import datetime

LOG_FILE = 'signal_log.csv'


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
