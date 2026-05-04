import requests
import time
import json
import os
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

KEYWORDS = ["private_key=", "seed phrase=", "mnemonic=", "api_key="]

INTERVAL = 60
MINUTES_BACK = 10

SEEN_FILE = "seen_repos.json"

if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r") as f:
        seen = set(json.load(f))
else:
    seen = set()

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    })

def search_new_repos(keyword):
    time_limit = (datetime.utcnow() - timedelta(minutes=MINUTES_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = f"{keyword} created:>{time_limit}"
    url = f"https://api.github.com/search/repositories?q={query}&sort=created&order=desc"

    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    res = requests.get(url, headers=headers)
    return res.json().get("items", [])

def run():
    print("Bot iniciado...")

    while True:
        for keyword in KEYWORDS:
            repos = search_new_repos(keyword)

            for repo in repos:
                url = repo["html_url"]

                if url not in seen:
                    seen.add(url)

                    msg = f"Nuevo repo ({keyword}):\n{url}"
                    print(msg)
                    send_telegram(msg)

        with open(SEEN_FILE, "w") as f:
            json.dump(list(seen), f)

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()