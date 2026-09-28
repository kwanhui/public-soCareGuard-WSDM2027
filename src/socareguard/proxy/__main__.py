import argparse
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()
ap = argparse.ArgumentParser(prog="python3 -m socareguard.proxy")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
a = ap.parse_args()
uvicorn.run("socareguard.proxy.app:app", host=a.host, port=a.port)
