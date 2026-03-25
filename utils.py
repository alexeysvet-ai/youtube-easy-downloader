import os

def log(msg):
    print(msg, flush=True)

def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()
