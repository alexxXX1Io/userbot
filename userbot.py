from google import genai
from google.genai import types
from telethon import TelegramClient, events, functions
from collections import OrderedDict
from datetime import datetime, timedelta
from telethon.tl.functions.messages import SendReactionRequest, DeleteMessagesRequest
from telethon.tl.types import ReactionEmoji
from telethon.tl.functions.account import UpdateProfileRequest
import asyncio
from voice_recognition import process_audio
from checkprofile import start_check
import os
import time
import pytz
from zoneinfo import ZoneInfo
import io
import json
import re
from dotenv import load_dotenv
from telethon.tl.functions.channels import GetFullChannelRequest

load_dotenv()

api_id = os.environ['TELEGRAM_API_ID']
api_hash = os.environ['TELEGRAM_API_HASH']
session_name = os.environ.get('TELEGRAM_SESSION_NAME', 'session_name')
gemini_api_key = os.environ['GEMINI_API_KEY']
log_channel = os.environ['LOG_CHANNEL']

client = TelegramClient(session_name, api_id, api_hash)
gemini_client = genai.Client(api_key=gemini_api_key)

MAX_MESSAGES = 5000
recent_messages = OrderedDict()
last_replied = {}
REPLY_COOLDOWN = timedelta(hours=1)
is_on = False

channel_groups = {}
CONFIG_FILE = 'channel_groups.json'

def load_groups():
    global channel_groups
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            channel_groups = json.load(f)
            channel_groups = {int(k): v for k, v in channel_groups.items()}

def save_groups():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(channel_groups, f, indent=2)

load_groups()

@client.on(events.NewMessage(pattern='!xgemini (.+)'))
async def gemini_handler(event):
    response = gemini_client.models.generate_content(
        model="gemma-3-4b-it",
        contents=event.pattern_match.group(1),
        config=types.GenerateContentConfig(
            temperature=0.3,  # higher = more creative, lower = more factual
            top_p=0.95,       # nucleus sampling; default is 0.95
            top_k=40          # top-K sampling; limits the pool of tokens
        )
    )
    await event.respond(response.text)

@client.on(events.NewMessage(outgoing=True, pattern="!purge (\\d+)"))
async def purge_handler(event):
    n = int(event.pattern_match.group(1))

    msgs = []
    async for msg in client.iter_messages(event.chat_id):
        if msg.out:
            msgs.append(msg)
        if len(msgs) >= n + 1:
            break

    await client.delete_messages(event.chat_id, msgs)

@client.on(events.NewMessage(outgoing=True, pattern=r"!uinfo(?: (.+))?"))
async def user_info(event):
    arg = event.pattern_match.group(1)

    try:
        if arg:
            arg = arg.strip()

            if arg.isdigit():
                target = int(arg)
            else:
                target = arg  # username or @username

            entity = await client.get_entity(target)
        else:
            entity = await event.get_chat()  # no argument -> use the current chat

        await event.respond(str(entity))

    except Exception as e:
        await event.respond(f"Error: {e}")


@client.on(events.NewMessage(pattern='/group_create', outgoing=True))
async def create_group(event):
    chat_id = event.chat_id
    if chat_id in channel_groups:
        await event.respond("⚠️ Group already exists")
        return
    channel_groups[chat_id] = {'target': chat_id, 'sources': []}
    save_groups()
    await event.respond("✅ Group created!\n\nAdd @usernames to the chat description and call /update")

@client.on(events.NewMessage(pattern='/update', outgoing=True))
async def update_group_sources(event):
    chat_id = event.chat_id
    if chat_id not in channel_groups:
        await event.respond("⚠️ Run /group_create first")
        return
    try:
        channel = await client.get_entity(chat_id)
        full_channel = await client(GetFullChannelRequest(channel=channel))
        description = full_channel.full_chat.about
        print("DESCRIPTION:\n", repr(description))

        usernames = re.findall(r'@(\w+)', description or "")
        print("FOUND USERNAMES: ", usernames)
        if not usernames:
            await event.respond("⚠️ No @usernames found")
            return
        source_ids = []
        for username in usernames:
            try:
                entity = await client.get_entity(username)
                source_ids.append(entity.id)
                await event.respond(f"✅ {entity.title} (ID: {entity.id})")
            except Exception as e:
                await event.respond(f"❌ @{username}: {str(e)[:80]}")
        channel_groups[chat_id]['sources'] = source_ids
        save_groups()
        await event.respond(f"📊 Tracking {len(source_ids)} channels")
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")

@client.on(events.NewMessage(pattern='/group_delete', outgoing=True))
async def delete_group(event):
    chat_id = event.chat_id
    if chat_id in channel_groups:
        del channel_groups[chat_id]
        save_groups()
        await event.respond("✅ Group deleted")
    else:
        await event.respond("⚠️ Group not found")

# Polling for public channels the account isn't subscribed to
async def poll_channels():
    last_ids = {}
    while True:
        for group in channel_groups.values():
            for src_id in group['sources']:
                try:
                    msgs = await client.get_messages(src_id, limit=1)
                    if msgs:
                        msg = msgs[0]
                        if last_ids.get(src_id) != msg.id:
                            last_ids[src_id] = msg.id
                            await client.forward_messages(group['target'], msg)
                except Exception as e:
                    print(f"poll error for {src_id}: {e}")
        await asyncio.sleep(10)

async def get_tg_id_from_username(username):
    global client
    try:
        user = await client.get_entity(username)
        print(f'User ID: {user.id}')
        tg_id = user.id
        return tg_id
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def get_username_safe(user):
    if hasattr(user, "username") and user.username:
        return user.username
    if hasattr(user, "first_name") or hasattr(user, "last_name"):
        return f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    if hasattr(user, "title"):
        return user.title
    return f"Unknown ({user.id})"


@client.on(events.NewMessage(pattern="!whorus"))
async def check_profile_command(event):
    message = event.raw_text
    errors = []
    try:
        parts = message.split()
        command, username = parts
    except:
        await event.respond("Error: you need to provide @username after the command. Example: !whorus @xypeq")
        return

    if not await get_tg_id_from_username(username):
        errors.append("nonexistent @username")

    if errors:
        await event.respond(f"Errors:\n {'; '.join(errors)}")
        return

    result = await start_check(client, username)

    await event.respond(json.dumps(result, ensure_ascii=False, indent=2))


def add_message_to_cache(msg_id, data):
    if len(recent_messages) >= MAX_MESSAGES:
        recent_messages.popitem(last=False)
    recent_messages[msg_id] = data

@client.on(events.NewMessage(pattern='!ping', outgoing=True))
async def ping(event):
    start = time.perf_counter()
    msg = await event.respond("X")
    end = time.perf_counter()
    ms = int((end - start) * 1000)
    await msg.edit(f"{ms}ms")
    await client(DeleteMessagesRequest(id=[event.id], revoke=True))
    return


@client.on(events.NewMessage)
async def auto_reply(event):
    global is_on
    sender = await event.get_sender()
    text = event.text

    if event.out:
        if text.lower() in ["!auto"]:
            is_on = not is_on
            print("is_on =", is_on)
            await client(SendReactionRequest(
                peer=sender,
                msg_id=event.id,
                reaction=[ReactionEmoji(emoticon='👍' if is_on else '👎')]
            ))
            await asyncio.sleep(1)
            await client(DeleteMessagesRequest(id=[event.id], revoke=True))
            return

    if not event.out and event.is_private:
        if is_on and not sender.bot:
            user_id = sender.id
            now = datetime.now()
            if user_id in last_replied and now - last_replied[user_id] < REPLY_COOLDOWN:
                return
            if (8 <= now.hour < 23):
                await event.reply("auto-reply:\n\nI'm asleep right now, you'll most likely get a reply in the morning")
                await client(SendReactionRequest(
                    peer=event.peer_id,
                    msg_id=event.id,
                    reaction=[ReactionEmoji(emoticon="😴")]
                ))
                last_replied[user_id] = now

@client.on(events.NewMessage)
async def handle_new_message(event):
    if event.message.out:
        return
    user = await event.get_sender()
    if not user:
        return
    if getattr(user, 'bot', False):
        return

    username = get_username_safe(user)

    if event.is_private or event.is_group or event.is_channel:
        add_message_to_cache(event.id, {
            'chat_id': event.chat_id,
            'username': username,
            'text': event.raw_text,
            'date': event.date
        })

@client.on(events.MessageEdited)
async def handle_edited_message(event):
    user = await event.get_sender()
    username = get_username_safe(user)

    old = recent_messages.get(event.id)
    if old:
        new_text = event.raw_text or ""
        old_text = old['text'] or ""

        if new_text.strip() == old_text.strip():
            return

        try:
            chat = await client.get_entity(old['chat_id'])
            chat_name = chat.title if hasattr(chat, 'title') else getattr(chat, 'first_name', f"Unknown ({old['chat_id']})")
        except Exception:
            chat_name = f"Unknown ({old['chat_id']})"

        text = (
            f" Message edited:\n"
            f" Sender: `{'@'+old['username']}`\n"
            f" Chat: `{chat_name}`\n"
            f" MsgID: {event.id}\n"
            f" Original date: {old['date'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f" *Before:*\n`{old_text}`\n\n"
            f" *After:*\n`{new_text}`"
        )
        await client.send_message(log_channel, text, parse_mode='markdown')

        add_message_to_cache(event.id, {
            'chat_id': event.chat_id,
            'username': username,
            'text': new_text,
            'date': old['date']
        })

@client.on(events.NewMessage)
async def handle_voice_to_text(event):
    text = event.text
    if text.lower() in ["!voice"]:
        await client(DeleteMessagesRequest(id=[event.id], revoke=True))

        if not event.is_reply:
            await event.reply("You need to reply to a voice message with the !voice command.")
            return

        replied = await event.get_reply_message()

        if not replied.voice:
            await event.reply("This message isn't a voice message. Reply to a voice message.")
            return

        voice = replied.voice
        file_id = voice.file_reference.hex()
        os.makedirs("audios", exist_ok=True)
        file_path = f"audios/{file_id}.ogg"

        await client.download_media(voice, file_path)

        if not os.path.exists(file_path):
            print(f"Failed to download file: {file_path}")
            return

        try:
            transcribed_text = await process_audio(file_path)
        except Exception as e:
            transcribed_text = f"Transcription error: {e}"

        await event.respond(
            f"Text: {transcribed_text}",
            reply_to=replied.id
        )

        try:
            os.remove(file_path)
            os.remove(file_path.replace(".ogg", ".wav"))
        except Exception as e:
            print(f"Couldn't delete file: {e}")


@client.on(events.MessageDeleted)
async def handle_deleted_message(event):
    for msg_id in event.deleted_ids:
        deleted = recent_messages.get(msg_id)
        if deleted:
            try:
                chat = await client.get_entity(deleted['chat_id'])
                chat_name = chat.title if hasattr(chat, 'title') else getattr(chat, 'first_name', f"Unknown ({deleted['chat_id']})")
            except Exception:
                chat_name = f"Unknown ({deleted['chat_id']})"

            text = (
                f" Message deleted:\n"
                f" Sender: `{'@'+deleted['username']}`\n"
                f" Text: `{deleted['text']}`\n"
                f" Date: {deleted['date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                f" Chat: `{chat_name}`\n"
                f" MsgID: {msg_id}"
            )
            await client.send_message(log_channel, text, parse_mode='markdown')

client.start()
print("polling...")
client.loop.create_task(poll_channels())
client.run_until_disconnected()
