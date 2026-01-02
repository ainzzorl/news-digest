import feedparser
from datetime import datetime
from time import mktime
import urllib.request
import urllib.error
import json
import html
import google.generativeai as genai
from bs4 import BeautifulSoup
import re

from news_digest.utils.util import *


def gen_hn_digest(config, source_options=None, global_config={}):
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

    digest = f"<h2>{html.escape(config['name'])} ({len(items)} item(s))</h2>\n\n"

    stories = [hn_item_to_html(config, item, global_config) for item in items]
    stories = [story.strip() + "\n<br>" for story in stories]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest


def hn_item_to_html(config, item, global_config={}):
    comments_url = item.comments
    story_id = comments_url.replace("https://news.ycombinator.com/item?id=", "")

    # Create collapsible structure with title visible
    title_html = f'<a href="javascript:void(0)" onclick="toggleElement(\'hn-item-{story_id}\')" style="cursor:pointer; text-decoration:none; font-weight:bold;">▶ {html.escape(item.title)}</a>\n<br>'

    # All content goes in the collapsible div
    content = (
        gen_href(item.link, item.link)
        + "\n<br>"
        + f"{html.escape(item.published)}\n<br>"
        + f"{item.description.strip()}"
    )

    # Add article summary if AI is configured
    if "ai" in global_config and "vendor" in global_config["ai"]:
        summary = summarize_article(item.link, global_config["ai"])
        if summary:
            content += f"<b>Summary:</b><br><br>{html.escape(summary)}"

    image_urls = "\n<br>".join(
        [
            f"<img src='{html.escape(link.href, quote=True)}'/>"
            for link in item.links
            if link.type.startswith("image/")
        ]
    )

    comments_html = "<br><br><b>Top comments:</b><br><br>\n"
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
            # per_comment_htmls.append(html.escape(comment_json["text"]))
            per_comment_htmls.append(comment_json["text"])
        comments_html += "<br><br>~~~~~~~~~~<br><br>\n".join(per_comment_htmls)
        comments_html += "<br>\n"

    except Exception as e:
        print(f"Error processing story {story_id}: {e}")

    # Wrap content in collapsible div (hidden by default)
    collapsible_content = f'<div id="hn-item-{story_id}" style="display:none; margin-left:20px;">{content + image_urls + comments_html}</div>'

    return title_html + collapsible_content


def extract_main_content(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove unwanted elements
    for element in soup.find_all(
        ["script", "style", "nav", "header", "footer", "aside"]
    ):
        element.decompose()

    # Try to find the main content
    main_content = None

    # Common article content containers
    content_selectors = [
        "article",
        '[role="main"]',
        ".post-content",
        ".article-content",
        ".entry-content",
        "#content",
        ".content",
        "main",
    ]

    for selector in content_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break

    # If no main content found, use the body
    if not main_content:
        main_content = soup.body

    if not main_content:
        return ""

    # Get text content
    text = main_content.get_text(separator=" ", strip=True)

    # Clean up the text
    text = re.sub(r"\s+", " ", text)  # Replace multiple spaces with single space
    text = re.sub(
        r"\n\s*\n", "\n", text
    )  # Replace multiple newlines with single newline

    return text.strip()


def summarize_article(url, ai_config):
    print(f"Summarizing article {url}")
    try:
        # Fetch the article content
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=10)
        html_content = response.read().decode("utf-8")
        print(f"Article content length: {len(html_content)}")
        # Extract main content using BeautifulSoup
        text_content = extract_main_content(html_content)
        print(f"Text content length: {len(text_content)}")

        # Truncate text if it's too long (context limit)
        if len(text_content) > 30000:
            text_content = text_content[:30000]

        # Generate summary based on vendor
        vendor = ai_config.get("vendor", "gemini")
        prompt = f"Please provide a concise summary of the following article in 2-3 sentences:\n\n{text_content}"

        if vendor == "gemini":
            # Configure the Gemini API
            genai.configure(api_key=ai_config["key"])
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            return response.text
        elif vendor == "local":
            # Use local OpenAI-compatible endpoint
            endpoint = ai_config.get(
                "endpoint", "http://framework-desktop.local:1234/v1/chat/completions"
            )
            model_name = ai_config.get("model", "openai/gpt-oss-120b")

            # Prepare the request
            data = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }

            req = urllib.request.Request(
                endpoint,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = urllib.request.urlopen(req, timeout=30)
            response_data = json.loads(response.read().decode("utf-8"))
            return response_data["choices"][0]["message"]["content"]
        else:
            return f"Unknown AI vendor: {vendor}"

    except urllib.error.HTTPError as e:
        print(f"HTTP error. Status: {e.status}, Reason: {e.reason}")
        return f"HTTP error: {html.escape(str(e))}"
    except Exception as e:
        print(f"Error summarizing article {url}: {e}")
        return f"Error summarizing article: {html.escape(str(e))}"
