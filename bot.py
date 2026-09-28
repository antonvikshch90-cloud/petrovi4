#!/usr/bin/env python3
"""
03: Personality & Soul — System prompt identity via SOUL.md.

Builds on 02 by adding:
  - A SOUL.md file loaded as the system prompt
  - Consistent personality across all conversations
  - Behavioral boundaries defined in plain text

Usage:
    uv run python 03-personality-soul/bot.py            # CLI mode
    uv run python 03-personality-soul/bot.py --telegram # Telegram mode
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

load_dotenv(override=True)

MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-coder")
client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=os.environ["GEMINI_API_KEY"],
)

BOT_DIR = Path(__file__).parent
SESSIONS_DIR = BOT_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# Load the soul — the agent's identity
SOUL = (BOT_DIR / "SOUL.md").read_text()


# --- Session persistence (JSONL) ---

def load_session(user_id: str) -> list[dict]:
    """Load conversation history from a JSONL file."""
    path = SESSIONS_DIR / f"{user_id}.jsonl"
    if not path.exists():
        return []
    messages = []
    for line in path.read_text().splitlines():
        if line.strip():
            messages.append(json.loads(line))
    return messages


def append_message(user_id: str, message: dict):
    """Append a single message to the user's JSONL session file."""
    path = SESSIONS_DIR / f"{user_id}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(message) + "\n")


# --- Core: stateful one-shot with personality ---

def reply_with_soul(user_id: str, user_text: str) -> str:
    """Call the LLM with SOUL as system prompt + persisted history."""
    history = load_session(user_id)

    user_msg = {"role": "user", "content": user_text}
    history.append(user_msg)
    append_message(user_id, user_msg)

    # Prepend the system prompt — the soul lives outside the saved history
    messages = [{"role": "system", "content": SOUL}] + history

    response = client.chat.completions.create(
        model="gemini-3.5-flash-lite",
        max_tokens=1024,
        temperature=0.7,
        messages=messages,
    )
    reply = response.choices[0].message.content or ""

    assistant_msg = {"role": "assistant", "content": reply}
    append_message(user_id, assistant_msg)

    return reply


# --- Telegram channel ---

async def start_command(update, context):
    await update.message.reply_text("Привет! Меня зовут Петрович и я алкоголик. Сегодня я трезв уже 10 лет и готов помочь тебе бросить пить. Задавай любые вопросы по этой теме, поделюсь опытом и что-нибудь придумаем с твоей ситуацией ;)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    reply = reply_with_soul(user_id, update.message.text)
    await update.message.reply_text(reply)


def run_telegram():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"Telegram bot running with SOUL — sessions in {SESSIONS_DIR}")
    app.run_polling()


# --- CLI channel ---

def run_cli():
    user_id = "cli-user"
    print(f"OpenClaw CLI (with SOUL) — model: {MODEL}. Type 'exit' to quit.\n")
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_text in {"exit", "quit"}:
            break
        if not user_text:
            continue
        print(f"bot> {reply_with_soul(user_id, user_text)}\n")


def main():
    if "--telegram" in sys.argv:
        run_telegram()
    else:
        run_cli()


if __name__ == "__main__":
    main()
