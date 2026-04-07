import asyncio
import html
import logging
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

client = genai.Client(api_key=GEMINI_API_KEY)

GENERATION_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())],
)

MAX_HISTORY_TURNS = 15  # keep last N user+model turn pairs

CLEAR_BUTTON = "🗑 Clear conversation"
REPLY_KEYBOARD = ReplyKeyboardMarkup([[CLEAR_BUTTON]], resize_keyboard=True)

# Maps user_id -> active async chat session
chat_sessions: dict[int, genai.chats.AsyncChat] = {}


def get_or_create_session(user_id: int) -> genai.chats.AsyncChat:
    if user_id not in chat_sessions:
        chat_sessions[user_id] = client.aio.chats.create(
            model=GEMINI_MODEL,
            config=GENERATION_CONFIG,
        )
    return chat_sessions[user_id]


def maybe_trim_history(user_id: int) -> None:
    """Recreate the session with only the most recent turns if history is too long."""
    session = chat_sessions.get(user_id)
    if session is None:
        return
    history = getattr(session, 'history', None) or session._curated_history
    max_messages = MAX_HISTORY_TURNS * 2  # 1 turn = 1 user message + 1 model message
    if len(history) > max_messages:
        chat_sessions[user_id] = client.aio.chats.create(
            model=GEMINI_MODEL,
            config=GENERATION_CONFIG,
            history=list(history[-max_messages:]),
        )


# Use a conservative limit to leave headroom for HTML tag expansion after md_to_html
MAX_MESSAGE_LENGTH = 3800


def split_message(text: str) -> list[str]:
    """Split raw text into chunks under Telegram's 4096-char limit, then convert each to HTML."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [md_to_html(text)]

    chunks = []
    while len(text) > MAX_MESSAGE_LENGTH:
        # Prefer splitting at a paragraph break, line break, sentence end, then hard-cut
        split_at = text.rfind("\n\n", 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = text.rfind(". ", 0, MAX_MESSAGE_LENGTH)
            if split_at != -1:
                split_at += 1  # include the period in the current chunk
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH
        chunks.append(md_to_html(text[:split_at].strip()))
        text = text[split_at:].strip()

    if text:
        chunks.append(md_to_html(text))

    return chunks


def md_to_html(text: str) -> str:
    """Convert Gemini markdown output to Telegram HTML."""
    code_blocks: list[str] = []

    def save_code_block(m: re.Match) -> str:
        code = html.escape(m.group(1))
        code_blocks.append(f"<pre><code>{code}</code></pre>")
        return f"\x00BLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n?([\s\S]*?)```", save_code_block, text)

    inline_codes: list[str] = []

    def save_inline_code(m: re.Match) -> str:
        code = html.escape(m.group(1))
        inline_codes.append(f"<code>{code}</code>")
        return f"\x00INLINE{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", save_inline_code, text)

    text = html.escape(text)

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"_(.+?)_", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.DOTALL)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00BLOCK{i}\x00", block)
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", code)

    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Hello! I'm a Gemini-powered assistant ({GEMINI_MODEL}).\n\n"
        "Just send me a text message and I'll reply using Gemini.\n"
        "Use the button below or /clear to reset the conversation and start fresh.",
        reply_markup=REPLY_KEYBOARD,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_sessions.pop(user_id, None)
    await update.message.reply_text(
        "Conversation cleared. Starting a fresh session.",
        reply_markup=REPLY_KEYBOARD,
    )


async def keep_typing(chat_id: int, context: ContextTypes.DEFAULT_TYPE, stop: asyncio.Event) -> None:
    """Send typing action every 4 seconds until stop is set."""
    while not stop.is_set():
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        keep_typing(update.effective_chat.id, context, stop_typing)
    )

    session = get_or_create_session(user_id)
    try:
        response = await session.send_message(user_text)
        maybe_trim_history(user_id)
        reply_text = response.text
        if not reply_text or not reply_text.strip():
            await update.message.reply_text(
                "Gemini returned an empty response. This may be due to a content safety filter.",
                reply_markup=REPLY_KEYBOARD,
            )
            return
        chunks = split_message(reply_text)
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            try:
                await update.message.reply_text(
                    chunk,
                    parse_mode=ParseMode.HTML,
                    reply_markup=REPLY_KEYBOARD if is_last else None,
                )
            except Exception:
                # HTML parse failed — fall back to plain text
                plain = re.sub(r"<[^>]+>", "", chunk)
                await update.message.reply_text(
                    plain,
                    reply_markup=REPLY_KEYBOARD if is_last else None,
                )
    except Exception as e:
        logger.error("Gemini API error for user %s: %s", user_id, e)
        await update.message.reply_text(
            "Sorry, something went wrong while contacting Gemini. Please try again.",
            reply_markup=REPLY_KEYBOARD,
        )
    finally:
        stop_typing.set()
        typing_task.cancel()


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{CLEAR_BUTTON}$"), clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started with model: %s", GEMINI_MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
