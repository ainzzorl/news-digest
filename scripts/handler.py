import yaml
import feedparser
from datetime import datetime
from time import mktime
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.users import GetFullUserRequest
import telethon
import shutil
import urllib.request
import json
import base64
import boto3

from reddit import *

CONFIG = None
ITEM_SEPARATOR = "" + "*" * 80 + "\n<br>\n<br>"
PREFERRED_MAX_IMAGE_WITH = 800


def gen_rss_digest(config):
    current_day = datetime.now().weekday() + 1
    if current_day not in config["days"]:
        print(
            f'Skipping {config["name"]}, not in days {config["days"]}. Current day: {current_day}'
        )
        return ""

    feed = feedparser.parse(config["url"])
    print(feed.feed)
    items = feed.entries
    # if items:
    #     print(items[0])
    items = [
        item
        for item in items
        if (
            "published_parsed" in item
            and (
                datetime.now() - datetime.fromtimestamp(mktime(item.published_parsed))
            ).total_seconds()
            <= CONFIG["max_time_diff_seconds"]
        )
    ]

    digest = f"<h2>{config['name']} ({len(items)} item(s))</h2>\n\n"

    # h = html2text.HTML2Text()
    # h.ignore_links = True

    stories = [rss_story_to_html(item) for item in items]
    stories = [story.strip() + "\n<br>" for story in stories]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest


def gen_hn_digest(config):
    feed = feedparser.parse(config["url"])
    print(feed.feed)

    current_day = datetime.now().weekday() + 1
    if current_day not in config["days"]:
        print(
            f'Skipping {config["name"]}, not in days {config["days"]}. Current day: {current_day}'
        )
        return ""

    days_to_take = 1
    if config["include_days_since_last"] == "yes":
        days_to_take = days_since_last_included_day(current_day, config["days"])
    seconds_to_take = days_to_take * 86400
    print(f"Days to take for HN: {days_to_take}")

    items = feed.entries
    items = [
        item
        for item in items
        if (
            "published_parsed" in item
            and (
                datetime.now() - datetime.fromtimestamp(mktime(item.published_parsed))
            ).total_seconds()
            <= seconds_to_take
        )
    ]

    digest = f"<h2>{config['name']} ({len(items)} item(s))</h2>\n\n"

    stories = [hn_item_to_html(config, item) for item in items]
    stories = [story.strip() + "\n<br>" for story in stories]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest


def hn_item_to_html(config, item):
    result = (
        f"{item.title}\n<br>"
        + gen_href(item.link, item.link)
        + "\n<br>"
        + f"{item.published}\n<br>"
        + f"{process_rss_description(item.description)}"
    )
    image_urls = "\n<br>".join(
        [
            f"<img src='{link.href}'/>"
            for link in item.links
            if link.type.startswith("image/")
        ]
    )
    comments_url = item.comments
    story_id = comments_url.replace("https://news.ycombinator.com/item?id=", "")

    comments_html = "Top comments:<br><br>\n"
    try:
        story_content = urllib.request.urlopen(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        ).read()
        story_json = json.loads(story_content)
        per_comment_htmls = []
        for comment_id in story_json["kids"][: config["top_comments"]]:
            comment_content = urllib.request.urlopen(
                f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json"
            ).read()
            comment_json = json.loads(comment_content)
            per_comment_htmls.append(comment_json["text"])
        comments_html += "<br><br>~~~~~~~~~~<br><br>\n".join(per_comment_htmls)
        comments_html += "<br>\n"

    except Exception as e:
        print(f"Error processing story {story_id}: {e}")
    return result + image_urls + comments_html


def rss_story_to_html(item):
    result = (
        f"{item.title}\n<br>"
        + gen_href(item.link, item.link)
        + "\n<br>"
        + f"{item.published}\n<br>"
        + f"{process_rss_description(item.description if hasattr(item, 'description') else 'N/A')}"
    )
    # image_urls = '\n<br>'.join(
    #     [f"<img src='{link.href}'/>" for link in item.links if link.type.startswith('image/')])
    # return result + image_urls
    return result


def process_rss_description(description):
    result = description
    # result = h.handle(result)
    result = re.sub(
        r"ДАННОЕ\s*СООБЩЕНИЕ\s*\(МАТЕРИАЛ\)\s*СОЗДАНО\s*И\s*\(ИЛИ\)\s*РАСПРОСТРАНЕНО\s*ИНОСТРАННЫМ\s*СРЕДСТВОМ\s*МАССОВОЙ\s*ИНФОРМАЦИИ,\s*ВЫПОЛНЯЮЩИМ\s*ФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА, И\s\(ИЛИ\)\sРОССИЙСКИМ\sЮРИДИЧЕСКИМ ЛИЦОМ,\sВЫПОЛНЯЮЩИМ\sФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА.",
        "",
        result,
    )
    result = re.sub(r"Спасите «Медузу»!.*https:\/\/support\.meduza\.io", "", result)
    result = result.strip()
    return result


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


async def gen_source_digest(config):
    print(f"Generating source digest, config: {config}")
    if config["type"] == "rss":
        return gen_rss_digest(config)
    elif config["type"] == "reddit":
        return gen_reddit_digest(config)
    elif config["type"] == "telegram":
        return await gen_telegram_digest(config)
    elif config["type"] == "hn":
        return gen_hn_digest(config)
    else:
        raise f"Unknown type: {config['type']}"


def load_config():
    global CONFIG
    with open("config.yml", "r") as stream:
        try:
            # print("Read config.yml")
            CONFIG = yaml.safe_load(stream)
            # print(CONFIG)
        except yaml.YAMLError as exc:
            print("Failed to read config.yml")
            print(exc)
            exit(1)


async def gen_digest(upload_path):
    load_config()
    source_results = [await gen_source_digest(source) for source in CONFIG["sources"]]
    source_results = [r for r in source_results if r is not None and len(r) > 0]
    result = """<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* Default (light mode) styles */
        body {
        background-color: white;
        color: black;
        }

        /* Dark mode styles */
        @media (prefers-color-scheme: dark) {
        body {
            background-color: #121212;
            color: white;
        }
        }
    </style>
    <script>
    function toggleElement(id) {
        var content = document.getElementById(id);
        if (content.style.display === "none" || content.style.display === "") {
        content.style.display = "block";
        } else {
        content.style.display = "none";
        }
    }
    </script>
</head>
    <body>"""
    if upload_path:
        upload_url = f"https://{CONFIG['s3']['bucket']}.s3.{CONFIG['s3']['region']}.amazonaws.com/{upload_path}"
    result += f'<p><a href="{upload_url}">View on web.</a></p>'
    result += "\n<br>".join(source_results)
    result += "</body></html>"
    return result


def mail_digest(digest):
    load_config()

    ssl_context = ssl.create_default_context()
    service = smtplib.SMTP_SSL(
        CONFIG["mail"]["smtp"]["address"],
        int(CONFIG["mail"]["smtp"]["port"]),
        context=ssl_context,
    )
    service.login(CONFIG["mail"]["smtp"]["user"], CONFIG["mail"]["smtp"]["password"])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "News Digest"
    msg["From"] = CONFIG["mail"]["from"]
    msg["To"] = CONFIG["mail"]["to"]
    part1 = MIMEText(digest, "html")
    msg.attach(part1)

    service.sendmail(
        CONFIG["mail"]["from"], CONFIG["mail"]["to"], msg.as_string().encode("utf-8")
    )


def upload_digest(digest, path):
    load_config()

    if not CONFIG["s3"]:
        print("No S3 config, skipping S3 upload")
        return

    s3 = boto3.client("s3")

    # Upload the text
    s3.put_object(
        Bucket=CONFIG["s3"]["bucket"],
        Key=path,
        Body=digest,
        ContentType="text/html; charset=utf-8",
    )

    print(f"Uploaded digest to s3://{CONFIG['s3']['bucket']}/{path}")
