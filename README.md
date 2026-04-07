# Gemini Telegram Bot

A Telegram bot that lets you have multi-turn text conversations with Google Gemini, with live web search enabled via Google Search grounding.

## Features

- Multi-turn conversations with memory (Gemini remembers context within a session)
- Google Search grounding — Gemini can search the web for up-to-date information
- Markdown formatting converted to Telegram-native formatting (bold, italic, code blocks, etc.)
- Per-user sessions — each user has their own independent conversation
- Clear button to reset the conversation and start fresh

## Requirements

- Python 3.10+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Google Gemini API key (from [Google AI Studio](https://aistudio.google.com))

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/Gemini-telegram-Bot.git
   cd Gemini-telegram-Bot
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and fill in your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-2.0-flash
   ```

5. **Run the bot**
   ```bash
   python bot.py
   ```

## Usage

| Action | How |
|---|---|
| Start a conversation | Send any text message |
| Clear conversation history | Tap the **🗑 Clear conversation** button or send `/clear` |

## Configuration

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token | required |
| `GEMINI_API_KEY` | Your Google Gemini API key | required |
| `GEMINI_MODEL` | Gemini model to use | `gemini-2.5-flash` |

## Notes

- Conversation history is stored in memory and is lost when the bot restarts.
- Google Search grounding is only supported on Gemini 2.0+ models.

## License

MIT
