import os
import re
import time
import asyncio
import requests

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# ===== CONFIG =====
SEARCH_TERMS = [
    "privateKey",
    "mnemonic",
    "seed phrase",
    "api_key",
    "SECRET_KEY",
    "PRIVATE_KEY"
]

MAX_SEEN = 5000

SEEN_URLS = set()
SEEN_COMMITS = set()

monitor_running = False

# ===== SESSION =====
session = requests.Session()

# ===== REGEX =====
ETH_REGEX = r"\b0x[a-fA-F0-9]{40}\b"
SOL_REGEX = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
PRIVATE_KEY_REGEX = r"\b([A-Fa-f0-9]{64}|[1-9A-HJ-NP-Za-km-z]{64,})\b"

# ===== CLEANUP =====
def cleanup_sets():
    global SEEN_URLS
    global SEEN_COMMITS

    if len(SEEN_URLS) > MAX_SEEN:
        SEEN_URLS = set(list(SEEN_URLS)[-2000:])

    if len(SEEN_COMMITS) > MAX_SEEN:
        SEEN_COMMITS = set(list(SEEN_COMMITS)[-2000:])

# ===== ETH BALANCE =====
def get_eth_balance(address):
    try:
        url = (
            "https://api.etherscan.io/api"
            f"?module=account"
            f"&action=balance"
            f"&address={address}"
            f"&tag=latest"
            f"&apikey={ETHERSCAN_API_KEY}"
        )

        r = session.get(url, timeout=10)

        if r.status_code != 200:
            print("ETH API ERROR:", r.text)
            return 0

        data = r.json()

        if data.get("status") != "1":
            return 0

        return int(data["result"]) / 1e18

    except Exception as e:
        print("ETH ERROR:", e)
        return 0

# ===== SOL BALANCE =====
def get_sol_balance(address):
    try:
        url = "https://api.mainnet-beta.solana.com"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [address]
        }

        r = session.post(url, json=payload, timeout=10)

        if r.status_code != 200:
            print("SOL API ERROR:", r.text)
            return 0

        data = r.json()

        return data.get("result", {}).get("value", 0) / 1e9

    except Exception as e:
        print("SOL ERROR:", e)
        return 0

# ===== ANALYSIS =====
def analyze_content(text):
    findings = []

    try:
        for addr in set(re.findall(ETH_REGEX, text)):
            bal = get_eth_balance(addr)

            if bal > 0:
                findings.append(f"🟣 ETH: {addr} | 💰 {bal:.4f}")

        for addr in set(re.findall(SOL_REGEX, text)):
            bal = get_sol_balance(addr)

            if bal > 0:
                findings.append(f"🟢 SOL: {addr} | 💰 {bal:.4f}")

        if re.search(PRIVATE_KEY_REGEX, text):
            findings.append("🔑 POSIBLE PRIVATE KEY DETECTADA")

    except Exception as e:
        print("ANALYZE ERROR:", e)

    return findings

# ===== GITHUB SEARCH =====
def search_github():

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    results = []

    for term in SEARCH_TERMS:

        time.sleep(2)

        url = (
            "https://api.github.com/search/code"
            f"?q={term}+in:file+extension:py+extension:js"
            "&sort=indexed"
            "&order=desc"
            "&per_page=2"
        )

        try:

            r = session.get(
                url,
                headers=headers,
                timeout=15
            )

            if r.status_code != 200:
                print("GitHub Search Error:", r.status_code)
                print(r.text)
                continue

            data = r.json()

            for item in data.get("items", []):

                file_url = item.get("html_url")

                if not file_url:
                    continue

                if file_url in SEEN_URLS:
                    continue

                SEEN_URLS.add(file_url)

                raw_url = (
                    file_url
                    .replace("github.com", "raw.githubusercontent.com")
                    .replace("/blob/", "/")
                )

                try:

                    content = session.get(
                        raw_url,
                        timeout=10
                    ).text[:4000]

                except Exception:
                    continue

                if not any(
                    k.lower() in content.lower()
                    for k in SEARCH_TERMS
                ):
                    continue

                findings = analyze_content(content)

                if findings:

                    msg = (
                        "🚨 LEAK EN ARCHIVO 🚨\n\n"
                        f"{file_url}\n\n"
                        + "\n".join(findings)
                    )

                    results.append(msg)

        except Exception as e:
            print("SEARCH ERROR:", e)

    return results

# ===== COMMITS =====
def monitor_commits():

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    results = []

    try:

        r = session.get(
            "https://api.github.com/events",
            headers=headers,
            timeout=15
        )

        if r.status_code != 200:
            print("Commits Error:", r.status_code)
            print(r.text)
            return results

        data = r.json()

        for event in data:

            if event.get("type") != "PushEvent":
                continue

            repo = event.get(
                "repo",
                {}
            ).get("name", "unknown")

            for commit in event.get(
                "payload",
                {}
            ).get("commits", []):

                sha = commit.get("sha")

                if not sha:
                    continue

                if sha in SEEN_COMMITS:
                    continue

                SEEN_COMMITS.add(sha)

                message = commit.get("message", "")

                if not any(
                    k.lower() in message.lower()
                    for k in SEARCH_TERMS
                ):
                    continue

                msg = (
                    "🚨 POSIBLE LEAK EN COMMIT 🚨\n\n"
                    f"📦 {repo}\n"
                    f"📝 {message}\n"
                    f"🔗 https://github.com/{repo}"
                )

                results.append(msg)

    except Exception as e:
        print("COMMITS ERROR:", e)

    return results

# ===== JOB =====
async def github_monitor(context: ContextTypes.DEFAULT_TYPE):

    global monitor_running

    if monitor_running:
        print("Monitor ya ejecutándose...")
        return

    monitor_running = True

    try:

        cleanup_sets()

        results = []

        try:
            results.extend(search_github())
        except Exception as e:
            print("ERROR search_github:", e)

        try:
            results.extend(monitor_commits())
        except Exception as e:
            print("ERROR monitor_commits:", e)

        results = results[:10]

        for result in results:

            try:

                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=result[:4000]
                )

                await asyncio.sleep(1)

            except Exception as e:
                print("SEND ERROR:", e)

    except Exception as e:
        print("MONITOR ERROR:", e)

    finally:
        monitor_running = False

# ===== MESSAGE HANDLER =====
async def handle_message(update, context):

    try:

        text = update.message.text.strip()

        findings = []

        for addr in set(re.findall(ETH_REGEX, text)):
            bal = get_eth_balance(addr)

            findings.append(
                f"🟣 ETH: {addr} | 💰 {bal:.6f}"
            )

        for addr in set(re.findall(SOL_REGEX, text)):
            bal = get_sol_balance(addr)

            findings.append(
                f"🟢 SOL: {addr} | 💰 {bal:.6f}"
            )

        if re.search(PRIVATE_KEY_REGEX, text):
            findings.append(
                "🔑 POSIBLE PRIVATE KEY DETECTADA"
            )

        if findings:

            await update.message.reply_text(
                "\n".join(findings)[:4000]
            )

        else:

            await update.message.reply_text(
                "❌ No se detectó nada válido"
            )

    except Exception as e:
        print("HANDLE ERROR:", e)

# ===== SETUP =====
async def setup(app):

    try:

        await app.bot.delete_webhook(
            drop_pending_updates=True
        )

        print("Webhook eliminado")

    except Exception as e:
        print("SETUP ERROR:", e)

# ===== APP =====
app = (
    ApplicationBuilder()
    .token(TELEGRAM_TOKEN)
    .read_timeout(30)
    .write_timeout(30)
    .connect_timeout(30)
    .pool_timeout(30)
    .build()
)

app.post_init = setup

# ===== HANDLER =====
app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)

# ===== JOB =====
app.job_queue.run_repeating(
    github_monitor,
    interval=300,
    first=10,
    name="github_monitor"
)

print("🤖 BOT PRO ACTIVO (TIEMPO REAL + DINERO)")

# ===== START =====
async def main():

    while True:

        try:

            print("🚀 Iniciando bot...")

            await app.initialize()
            await app.start()

            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )

            while True:
                await asyncio.sleep(60)

        except Conflict:

            print("⚠️ Otra instancia detectada...")
            await asyncio.sleep(20)

        except Exception as e:

            print("❌ ERROR GENERAL:", e)
            await asyncio.sleep(20)

        finally:

            try:
                await app.updater.stop()
            except:
                pass

            try:
                await app.stop()
            except:
                pass

            try:
                await app.shutdown()
            except:
                pass

# ===== RUN =====
if __name__ == "__main__":
    asyncio.run(main())