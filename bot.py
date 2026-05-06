import os
import re
import requests
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# ===== CONFIG =====
MIN_ETH = 0
MIN_SOL = 0

SEARCH_TERMS = [
    "password",
    "config",
    "token"
]

SEEN_URLS = set()

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

# ===== TELEGRAM HANDLER =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    findings = detect_and_validate(msg.text)

    if findings:
        response = "🚨 ALERTA 🚨\n\n"
        response += msg.text + "\n\n"

        for f in findings:
            response += f"- {f}\n"

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=response
        )

# ===== GITHUB SEARCH =====
def search_github():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    results = []

    for term in SEARCH_TERMS:
        url = f"https://api.github.com/search/code?q={term}&sort=indexed&order=desc"

        try:
            r = requests.get(url, headers=headers).json()

            for item in r.get("items", [])[:3]:
                file_url = item["html_url"]

                if file_url in SEEN_URLS:
                    continue

                SEEN_URLS.add(file_url)

                results.append(f"🔍 {term}:\n{file_url}")

        except:
            continue

    return results

# ===== GITHUB MONITOR =====
async def github_monitor(context: ContextTypes.DEFAULT_TYPE):
    results = search_github()

    for r in results:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🚨 GITHUB ALERT 🚨\n\n{r}"
        )

# ===== MAIN =====
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# limpiar conflictos
asyncio.get_event_loop().run_until_complete(
    app.bot.delete_webhook(drop_pending_updates=True)
)

app.add_handler(MessageHandler(filters.ALL, handle_message))

# loop github cada 60s
app.job_queue.run_repeating(github_monitor, interval=60, first=10)

print("🤖 BOT PRO ACTIVO (Telegram + GitHub + Wallets)")
app.run_polling()