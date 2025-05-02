from datetime import datetime
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.users import GetFullUserRequest
import telethon
import shutil
import base64

from util import *


async def gen_telegram_digest(config):
    res = ""
    res += "<h2>Telegram</h2>"

    shutil.copyfile("session_name.session", "/tmp/session_name.session")

    async with TelegramClient(
        "/tmp/session_name.session", config["api_id"], config["api_hash"]
    ) as client:
        # For testing one channel
        # return await gen_telegram_channel_digest(config, client, <id>)

        channel_id_to_text = {}

        async for dialog in client.iter_dialogs():
            if (datetime.now().astimezone() - dialog.date).days >= 3:
                print(f"Date too far: {dialog.date}, stopping")
                break

            channel_entity = await client.get_entity(dialog.id)
            if not isinstance(
                channel_entity, telethon.tl.types.Chat
            ) and not isinstance(channel_entity, telethon.tl.types.Channel):
                print(f"Skipping {dialog.id}, wrong type")
                continue

            channel_id_to_text[channel_entity.id] = await gen_telegram_channel_digest(
                config, client, channel_entity
            )

        # First add channels that are in config['channels']
        for channel in config["channels"]:
            if channel["id"] in channel_id_to_text:
                res += channel_id_to_text[channel["id"]]

        # Then add channels that are not in config['channels']
        for channel_id, text in channel_id_to_text.items():
            if channel_id not in [c["id"] for c in config["channels"]]:
                res += text

    return res


async def gen_telegram_channel_digest(config, client, channel_entity):
    res = ""
    print(f"Processing chat: {channel_entity.title}, channel id: {channel_entity.id}")
    if channel_entity.id in config["except_chat_ids"]:
        print(f"Excluding {channel_entity.id} ({channel_entity.title})")
        return ""

    # Get config for this channel
    channel_config = next(
        (c for c in config["channels"] if c["id"] == channel_entity.id), None
    )

    current_day = datetime.now().weekday() + 1

    if channel_config is not None and "days" in channel_config:
        if current_day not in channel_config["days"]:
            print(
                f'Skipping {channel_entity.id} ({channel_entity.title}), not in days {channel_config["days"]}. Current day: {current_day}'
            )
            return ""

    filters = (
        channel_config["filters"]
        if channel_config is not None and "filters" in channel_config
        else {}
    )
    include_filters = filters["include"] if "include" in filters else []

    posts = await client(
        GetHistoryRequest(
            peer=channel_entity,
            limit=100,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0,
        )
    )
    posts_str = ""
    total_posts = 0

    selected_posts = []
    for post in posts.messages:
        ago = datetime.now().astimezone() - post.date
        days = (
            channel_config["days"]
            if channel_config is not None and "days" in channel_config
            else default_days()
        )
        days_to_take = 1
        if (
            channel_config is not None
            and "include_days_since_last" in channel_config
            and channel_config["include_days_since_last"] == "yes"
        ):
            days_to_take = days_since_last_included_day(current_day, days)
        if ago.days >= days_to_take:
            break
        if include_filters:
            if not any(filter in str(post.message) for filter in include_filters):
                continue

        total_posts += 1
        selected_posts.append(post)

    for post in selected_posts[::-1]:
        if isinstance(post.action, telethon.tl.types.MessageActionChatAddUser):
            # print("Ignoring MessageActionChatAddUser")
            continue

        if hasattr(post, "from_id") and hasattr(post.from_id, "user_id"):
            user_id = post.from_id.user_id
            full_user = await get_telegram_user(client, user_id)
        else:
            user_id = "undefined"
            full_user = None
        if user_id in config["silenced_user_ids"]:
            posts_str += f"<span><i>Silenced user: {user_id}</i></span>"
            posts_str += "<br>\n"
            continue

        user_info_suffix = ""
        if full_user is not None:
            user_info_suffix += f" - {full_user.username}"
            if full_user.first_name is not None:
                user_info_suffix += f" ({full_user.first_name}"
                if full_user.last_name is not None:
                    user_info_suffix += f" {full_user.last_name}"
                user_info_suffix += f")"

        posts_str += f"<b>{str(post.date)}{user_info_suffix}</b>" + "<br>\n"
        if hasattr(channel_entity, "username") and channel_entity.username is not None:
            usr = channel_entity.username
            url = "https://t.me/" + str(usr) + "/" + str(post.id)
            posts_str += gen_href(url, url) + "<br>\n"

        post_message = str(post.message).replace("\n", "<br>\n")
        posts_str += post_message
        posts_str += "<br>\n"

        media_tag = await get_post_media_tag(
            client, post, no_media=channel_entity.id in config["no_media"]
        )
        posts_str += media_tag

        if len(str(post.message)) == 0 and len(media_tag) == 0:
            posts_str += str(post)

        posts_str += "<br>\n"

    if total_posts == 0:
        print(f"Chat with no messages: {channel_entity.title}, id={channel_entity.id}.")
        return ""
    else:
        res += f"<h4>{channel_entity.title} ({total_posts} item(s), id={channel_entity.id})</h4>"
        res += posts_str
    return res


telegram_users_cache = {}


async def get_telegram_user(client, user_id):
    if user_id in telegram_users_cache:
        return telegram_users_cache[user_id]
    users = await client(GetFullUserRequest(user_id))
    if len(users.users) < 1:
        result = None
    else:
        result = users.users[0]
    telegram_users_cache[user_id] = result
    return result


def default_days():
    return [1, 2, 3, 4, 5, 6, 7]


def days_since_last_included_day(current_day, included_days):
    result = None
    for day in included_days:
        if current_day == day:
            continue
        if current_day > day:
            result = current_day - day
    if result is None:
        result = 7 - included_days[-1] + current_day
    return result


async def get_post_media_tag(client, post, no_media=False):
    if post.audio is not None:
        return "<span><i>Unsupported message type: audio</i></span>"
    if post.gif is not None:
        return "<span><i>Unsupported message type: gif</i></span>"
    if post.sticker is not None:
        return "<span><i>Unsupported message type: sticker</i></span>"
    if post.video is not None:
        return "<span><i>Unsupported message type: video</i></span>"
    if post.video_note is not None:
        return "<span><i>Unsupported message type: video note</i></span>"
    if post.voice is not None:
        return "<span><i>Unsupported message type: voice</i></span>"
    if post.poll is not None:
        return "<span><i>Unsupported message type: poll</i></span>"

    if post.photo is None:
        return ""
    if no_media:
        return "<span><i>Not including media for this channel</i></span>"

    ext_to_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    if post.file.ext not in ext_to_mime:
        return f"<span><i>Unsupported image extension: {post.file.ext}</i></span>"
    mime = ext_to_mime[post.file.ext]

    thumb = None
    for i, size in enumerate(post.photo.sizes):
        if hasattr(size, "w") and size.w <= PREFERRED_MAX_IMAGE_WITH:
            thumb = i

    blob = await client.download_media(post, bytes, thumb=thumb)
    encoded = base64.b64encode(blob).decode("utf-8")

    return f'<img src="data:{mime};base64, {encoded}" alt="Image"/>'
