import yaml
import feedparser
from datetime import datetime
from time import mktime
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import urllib.request
import json
import boto3

from reddit import *
from telegram import *

CONFIG = None
ITEM_SEPARATOR = "" + "*" * 80 + "\n<br>\n<br>"


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
