import os
import re
import requests
from telegram.ext import ApplicationBuilder, ContextTypes

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# ===== CONFIG =====
SEARCH_TERMS = [
    "wallet",
]

SEEN_URLS = set()
SEEN_COMMITS = set()

# ===== REGEX =====
ETH_REGEX = r"\b0x[a-fA-F0-9]{40}\b"
SOL_REGEX = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"

# ===== ETH BALANCE =====
def get_eth_balance(address):
    try:
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        r = requests.get(url, timeout=10).json()
        if r["status"] != "1":
            return 0
        return int(r["result"]) / 1e18
    except:
        return 0

# ===== SOL BALANCE =====
def get_sol_balance(address):
    try:
        url = "https://api.mainnet-beta.solana.com"
        payload = {
            "jsonrpc":"2.0",
            "id":1,
            "method":"getBalance",
            "params":[address]
        }
        r = requests.post(url, json=payload, timeout=10).json()
        return r["result"]["value"] / 1e9
    except:
        return 0

# ===== ANALISIS =====
def analyze_content(text):
    findings = []

    for addr in re.findall(ETH_REGEX, text):
        bal = get_eth_balance(addr)
        if bal > 0:
            findings.append(f"🟣 ETH: {addr} | 💰 {bal:.4f}")

    for addr in re.findall(SOL_REGEX, text):
        bal = get_sol_balance(addr)
        if bal > 0:
            findings.append(f"🟢 SOL: {addr} | 💰 {bal:.4f}")

    return findings

# ===== GITHUB SEARCH (ARCHIVOS) =====
def search_github():
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    results = []

    for term in SEARCH_TERMS:
        url = f"https://api.github.com/search/code?q={term}+in:file+extension:py+extension:js&sort=indexed&order=desc"

        try:
            r = requests.get(url, headers=headers, timeout=10).json()

            for item in r.get("items", [])[:5]:
                file_url = item["html_url"]

                if file_url in SEEN_URLS:
                    continue

                SEEN_URLS.add(file_url)

                raw_url = file_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

                try:
                    content = requests.get(raw_url, timeout=5).text[:4000]
                except:
                    continue

                if not any(k.lower() in content.lower() for k in SEARCH_TERMS):
                    continue

                findings = analyze_content(content)

                if findings:
                    msg = f"🚨 LEAK EN ARCHIVO 🚨\n\n{file_url}\n\n"
                    msg += "\n".join(findings)
                    results.append(msg)

        except:
            continue

    return results

# ===== GITHUB TIEMPO REAL (COMMITS) =====
def monitor_commits():
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    url = "https://api.github.com/events"

    results = []

    try:
        r = requests.get(url, headers=headers, timeout=10).json()

        for event in r:
            if event["type"] != "PushEvent":
                continue

            repo = event["repo"]["name"]

            for commit in event["payload"]["commits"]:
                sha = commit["sha"]

                if sha in SEEN_COMMITS:
                    continue

                SEEN_COMMITS.add(sha)

                message = commit["message"]

                if not any(k.lower() in message.lower() for k in SEARCH_TERMS):
                    continue

                msg = f"🚨 POSIBLE LEAK EN COMMIT 🚨\n\n📦 {repo}\n📝 {message}\n🔗 https://github.com/{repo}"

                results.append(msg)

    except:
        pass

    return results

from telegram.ext import ApplicationBuilder, ContextTypes

# ===== JOB =====
async def github_monitor(context: ContextTypes.DEFAULT_TYPE):
    results = []

    try:
        results += search_github()
    except Exception as e:
        print("ERROR search_github:", e)

    try:
        results += monitor_commits()
    except Exception as e:
        print("ERROR monitor_commits:", e)

    for r in results:
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=r)
        except Exception as e:
            print("ERROR sending message:", e)


# ===== MAIN =====
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# limpiar webhook automáticamente
app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

# job cada 30s
app.job_queue.run_repeating(github_monitor, interval=30, first=5)

print("🤖 BOT PRO ACTIVO (TIEMPO REAL + DINERO)")

# iniciar bot (SIN asyncio.run)
app.run_polling()