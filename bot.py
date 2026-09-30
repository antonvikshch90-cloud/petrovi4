#!/usr/bin/env python3
"""
03: Personality & Soul — System prompt identity via SOUL.md.

Builds on 02 by adding:
  - A SOUL.md file loaded as the system prompt
  - Consistent personality across all conversations
  - Behavioral boundaries defined in plain text

Usage:
    uv run python 03-personality-soul/bot.py            # CLI mode
    uv run python 03-personality-soul/bot.py --telegram # Telegram mode (webhook)
"""
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

load_dotenv(override=True)

# --- Логирование ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-coder")
client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=os.environ["GEMINI_API_KEY"],
    max_retries=5,
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
    """Call the LLM with SOUL as system prompt + persisted history (CLI only)."""
    history = load_session(user_id)

    user_msg = {"role": "user", "content": user_text}
    history.append(user_msg)
    append_message(user_id, user_msg)

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
    await update.message.reply_text(
        "Привет! Меня зовут Петрович, мне 40 лет и я алкоголик из Владивостока. "
        "Сегодня я трезв уже 10 лет и готов помочь тебе бросить пить. "
        "Задавай любые вопросы по этой теме, поделюсь опытом и что-нибудь придумаем с твоей ситуацией ;)"
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    session_file = SESSIONS_DIR / f"{user_id}.jsonl"
    if session_file.exists():
        session_file.unlink()
    await update.message.reply_text("Начинаем с чистого листа. О чём поговорим?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_text = update.message.text

    bot_msg = await update.message.reply_text("⏳")

    history = load_session(user_id)
    user_msg = {"role": "user", "content": user_text}
    history.append(user_msg)
    append_message(user_id, user_msg)

    messages = [{"role": "system", "content": SOUL}] + history

    try:
        stream = client.chat.completions.create(
            model="gemini-3.5-flash-lite",
            max_tokens=1024,
            temperature=0.7,
            messages=messages,
            stream=True,
        )

        full_text = ""
        chunk_count = 0

        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_text += chunk.choices[0].delta.content
                chunk_count += 1

                if chunk_count % 15 == 0:
                    try:
                        await bot_msg.edit_text(full_text + " ▌")
                    except Exception:
                        pass

        await bot_msg.edit_text(full_text)

        assistant_msg = {"role": "assistant", "content": full_text}
        append_message(user_id, assistant_msg)

    except Exception as e:
        logger.error(f"Ошибка модели: {e}")
        try:
            await bot_msg.edit_text("Сейчас я немного перегружен. Попробуй написать ещё раз через минуту.")
        except Exception:
            pass


async def error_handler(update, context):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Что-то пошло не так. Попробуй ещё раз."
            )
        except Exception:
            pass


def run_telegram():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    port = int(os.environ.get("PORT", 10000))

    # Render автоматически создаёт эту переменную
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not hostname:
        logger.error("RENDER_EXTERNAL_HOSTNAME не задан. Webhook не сможет работать.")
        sys.exit(1)

    webhook_url = f"https://{hostname}/webhook"

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info(f"Запуск webhook на порту {port}, URL: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )


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
