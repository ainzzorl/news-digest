import feedparser
from datetime import datetime
from time import mktime
import re

from util import *


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
                datetime.now() - datetime.fromtimestamp(mktime(item.published_parsed))  # type: ignore
            ).total_seconds()
            <= config["max_time_diff_seconds"]
        )
    ]

    digest = f"<h2>{config['name']} ({len(items)} item(s))</h2>\n\n"

    # h = html2text.HTML2Text()
    # h.ignore_links = True

    stories = [rss_story_to_html(item) for item in items]
    stories = [story.strip() + "\n<br>" for story in stories]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest


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
