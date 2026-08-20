import re
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import Channel, User

RUSSIAN_PATTERN = re.compile(r"[ёЁыЫэЭъЪ]")


def find_russian(text: str):
    """Returns any Russian-specific characters found in the text."""
    if not text:
        return ""
    matches = RUSSIAN_PATTERN.findall(text)
    return "".join(matches) if matches else ""


async def check_channel(client: TelegramClient, entity):
    """Checks a specific channel or group for Russian-specific characters."""
    found = []
    async for msg in client.iter_messages(entity, limit=50):
        if msg.text:
            rus = find_russian(msg.text)
            if rus:
                found.append((getattr(entity, 'title', str(entity)), msg.text))
    return found


async def check_user_channels(client: TelegramClient, full):
    """Checks a user's channels for Russian-specific characters."""
    found = []
    for chat in getattr(full, 'chats', []):
        if isinstance(chat, Channel):
            async for msg in client.iter_messages(chat, limit=50):
                if msg.text:
                    rus = find_russian(msg.text)
                    if rus:
                        found.append((chat.title, msg.text))
    return found


async def check_user(client: TelegramClient, username: str, checked: set):
    """
    Checks a single user and returns the results.
    :param client: a TelegramClient instance
    :param username: username in @name or plain name format
    :param checked: set of already-checked users
    :return: (results, next_username)
    """
    results = []
    next_username = None

    if username in checked:
        return results, None
    checked.add(username)

    try:
        user = await client.get_entity(username)
        full = await client(GetFullUserRequest(user.id))
    except Exception as e:
        results.append(f"❌ Error processing {username}: {e}")
        return results, None

    for field_name, value in [
        ("First name", user.first_name),
        ("Last name", user.last_name),
        ("Bio", full.full_user.about),
        ("Username", f"@{user.username}" if user.username else None),
    ]:
        rus = find_russian(value)
        if rus:
            results.append(f"{field_name}: {value} -> {rus}")

    if user.phone and user.phone.startswith("7"):
        results.append(f"Phone starts with 7: {user.phone}")

    channels_rus = await check_user_channels(client, full)
    for title, msg_text in channels_rus:
        results.append(f"Channel '{title}': {msg_text}")

    mentions = re.findall(
        r'@([a-zA-Z0-9_]{5,32})',
        (full.full_user.about or "") + " " + (user.first_name or "") + " " + (user.last_name or "")
    )
    mentions = ['@' + m for m in mentions]

    for m in mentions:
        if m not in checked:
            try:
                ent = await client.get_entity(m)
                if isinstance(ent, User):
                    next_username = m
                    break
                else:
                    channel_rus = await check_channel(client, ent)
                    for title, msg_text in channel_rus:
                        results.append(f"Channel '{title}': {msg_text}")
            except Exception as e:
                results.append(f"⚠️ Could not process {m}: {e}")
                continue

    return results, next_username


async def start_check(client: TelegramClient, start_username: str):
    """
    Runs the check starting from a given user.
    :param client: an already-connected TelegramClient
    :param start_username: who to check
    :return: dict {username: results_list}
    """
    checked = set()
    results_map = {}

    username = start_username
    while username and username not in checked:
        results, next_username = await check_user(client, username, checked)
        results_map[username] = results
        username = next_username

    return results_map
