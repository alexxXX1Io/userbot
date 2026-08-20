# userbot

A Telethon-based Telegram userbot: Gemini-powered chat command, voice message
transcription, edited/deleted message logging, a "Russian character" profile
checker, and forwarding from public channels into a group based on
`@usernames` listed in the group's description.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values:

   ```bash
   cp .env.example .env
   ```

   - `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — from https://my.telegram.org
   - `TELEGRAM_SESSION_NAME` — filename (without extension) for the Telethon session
   - `GEMINI_API_KEY` — from https://aistudio.google.com
   - `LOG_CHANNEL` — chat/channel (username, ID, or invite link) where edited/deleted message logs are sent

3. (Optional) Copy `channel_groups.example.json` to `channel_groups.json` if
   you want to pre-seed forwarding groups; otherwise it's created at runtime
   via the `/group_create` command.

4. Run it:

   ```bash
   python userbot.py
   ```

   On first run, Telethon will prompt for your phone number and login code
   to create the session file.

## Commands

Sent by the account owner (outgoing) unless noted:

- `!xgemini <text>` — ask Gemini a question (anyone can trigger this one)
- `!ping` — round-trip latency check
- `!purge <n>` — delete your last `n` messages in the chat
- `!uinfo [id|username]` — dump entity info for a user/chat
- `!auto` — toggle the away auto-reply for private messages
- `!voice` (as a reply to a voice message) — transcribe it to text
- `!whorus @username` — recursively check a user (and users/channels they mention) for Russian-specific characters in their name/bio/messages
- `/group_create`, `/update`, `/group_delete` — manage a forwarding group: `/group_create` in a chat, list source `@usernames` in that chat's description, then `/update` to pick them up

## Security notes

- Never commit `.env`, `*.session`, or `channel_groups.json` — they're
  gitignored. The session file is equivalent to your account's login
  credentials.
- If any of these were ever committed to a repo (this one previously had
  hardcoded API keys and a tracked session file), rotate the Gemini API key
  and terminate the leaked Telegram session from Settings → Devices before
  relying on this repo further.
