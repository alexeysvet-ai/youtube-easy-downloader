import os
import time

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def ensure_file(path):
    if not os.path.exists(path):
        with open(path, "w"):
            pass
