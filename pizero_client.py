"""Contoh client di Pi Zero: python3 pizero_client.py foto.jpg"""
import sys

import requests

BRIDGE_URL = "https://twotrash.wbesoft.com/classify"
API_TOKEN = "ganti-token-rahasia-ini"

with open(sys.argv[1], "rb") as f:
    resp = requests.post(
        BRIDGE_URL,
        headers={"X-API-Token": API_TOKEN},
        files={"image": ("photo.jpg", f, "image/jpeg")},
        timeout=60,
    )
resp.raise_for_status()
print(resp.json())
