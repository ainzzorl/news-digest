import feedparser
from datetime import datetime
from time import mktime
import urllib.request
import json

from util import *


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
                datetime.now() - datetime.fromtimestamp(mktime(item.published_parsed))  # type: ignore
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
        + f"{item.description.strip()}"
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
