import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ===== VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ===== KEYWORDS CORREGIDAS =====
KEYWORDS = [
    "mint",
    "privateKey",
    "seedphrase",
    "token",
    "private_key=",
    "seed phrase=",
    "mnemonic=",
    "api_key="
]

# ===== REGEX =====
SOLANA_REGEX = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
PRIVATE_KEY_REGEX = r"\b([A-Fa-f0-9]{64}|[1-9A-HJ-NP-Za-km-z]{64,})\b"
JSON_KEY_REGEX = r'("privateKey"\s*:\s*".+?"|"secret"\s*:\s*".+?")'


def extract_code_blocks(text, entities):
    if not text or not entities:
        return []

    blocks = []
    for ent in entities:
        if ent.type in ["pre", "code"]:
            start = ent.offset
            end = ent.offset + ent.length
            blocks.append(text[start:end])

    return blocks


def contains_exact_keyword(text):
    for word in KEYWORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_crypto(text):
    findings = []

    if re.search(SOLANA_REGEX, text):
        findings.append("🪙 Wallet Solana detectada")

    if re.search(PRIVATE_KEY_REGEX, text):
        findings.append("🔑 Posible private key")

    if re.search(JSON_KEY_REGEX, text):
        findings.append("📦 JSON con claves")

    return findings


def should_alert(message):
    text = message.text or message.caption
    entities = message.entities or message.caption_entities

    code_blocks = extract_code_blocks(text, entities)

    if not code_blocks:
        return False, None, None

    for block in code_blocks:
        if contains_exact_keyword(block):
            crypto_hits = detect_crypto(block)
            return True, block, crypto_hits

    return False, None, None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    alert, block, crypto_hits = should_alert(msg)

    if alert:
        response = "🚨 ALERTA EN CÓDIGO 🚨\n\n"
        response += f"{block}\n\n"

        if crypto_hits:
            response += "⚠️ Detectado:\n"
            for hit in crypto_hits:
                response += f"- {hit}\n"

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=response
        )

        print("✅ Alerta enviada")


app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, handle_message))

print("🤖 Bot activo...")
app.run_polling()