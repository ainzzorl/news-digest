import yaml
import feedparser
from datetime import datetime
from time import mktime
import html2text
import re
import smtplib
import ssl
import praw

CONFIG = None
ITEM_SEPARATOR = "*" * 80 + "\n\n"


def get_subreddits(session, config):
    # TODO: make configurable
    isweek = datetime.now().weekday() == 5 # Saturday

    subs = []
    for subreddit in list(session.user.subreddits(limit=None)):
        if subreddit.display_name in config['exclude']:
            continue
        if get_frequency(config,
                         subreddit.display_name) == 'week' and not isweek:
            continue
        subs.append(subreddit)
    return subs


def gen_submission_digest(config, subreddit, submission):
    digest = f"{submission.title} (score: {submission.score})\n"
    if subreddit.display_name in config['showself'] and submission.is_self:
        digest += submission.selftext + "\n"
    digest += f"{submission.url}\nhttps://old.reddit.com{submission.permalink}\n"
    return digest


def get_frequency(config, subreddit_name):
    if subreddit_name in config['overrides'] and 'frequency' in config[
            'overrides'][subreddit_name]:
        return config['overrides'][subreddit_name]['frequency']
    return config['frequency']


def gen_subreddit_digest(session, config, subreddit):
    frequency = get_frequency(config, subreddit.display_name)
    submissions = session.subreddit(subreddit.display_name).top(frequency)

    if frequency == 'day':
        max_time_diff = 86400 * 2
    elif frequency == 'week':
        max_time_diff = 86400 * 7 * 2
    else:
        print(f"Unknown frequency: {frequency}")
        exit(1)
    submissions = [
        s for s in submissions
        if (datetime.now() - datetime.utcfromtimestamp(s.created_utc)
            ).total_seconds() <= max_time_diff
    ]

    submissions = submissions[:config['submissions_per_subreddit']]

    if not submissions:
        return None

    if frequency == 'day':
        frequency_readable = 'daily'
    else:
        frequency_readable = f'{frequency}ly'
    digest = f"## /r/{subreddit.display_name} ({frequency_readable})\n\n"

    digest += "\n".join(
        [gen_submission_digest(config, subreddit, s) for s in submissions])

    return digest


def gen_reddit_digest(config):
    session = praw.Reddit(user_agent='USERAGENT',
                          client_id=config['client_id'],
                          client_secret=config['secret'],
                          username=config['user'],
                          password=config['password'])

    subreddits = get_subreddits(session, config)

    digest = f"# Reddit ({len(subreddits)} subreddits)\n\n"

    subreddit_digests = [
        gen_subreddit_digest(session, config, s) for s in subreddits
    ]
    subreddit_digests = [d for d in subreddit_digests if d is not None]

    digest += ITEM_SEPARATOR.join(subreddit_digests)

    return digest


def gen_rss_digest(config):
    feed = feedparser.parse(config['url'])
    print(feed.feed)
    items = feed.entries
    if items:
        print(items[0])
    items = [
        item for item in items
        if ('published_parsed' in item and
            (datetime.now() -
             datetime.fromtimestamp(mktime(item.published_parsed))
             ).total_seconds() <= CONFIG['max_time_diff_seconds'])
    ]

    digest = f"# {feed.feed.title} ({len(items)} item(s))\n\n"

    h = html2text.HTML2Text()
    h.ignore_links = True

    stories = [
        f"{item.title}\n" + f"{item.link}\n" + f"{item.published}\n" +
        f"{process_rss_description(item.description, h)}" for item in items
    ]
    stories = [
        re.sub(
            '!\[\]\(http://feeds\.feedburner.com\/~[\s\S]*\/rss\/cnn_topstories.*\)',
            '', story).strip() + "\n" for story in stories
    ]
    digest += ITEM_SEPARATOR.join(stories)

    return digest

def process_rss_description(description, h):
    result = description
    result = h.handle(result)
    result = re.sub(r'ДАННОЕ\s*СООБЩЕНИЕ\s*\(МАТЕРИАЛ\)\s*СОЗДАНО\s*И\s*\(ИЛИ\)\s*РАСПРОСТРАНЕНО\s*ИНОСТРАННЫМ\s*СРЕДСТВОМ\s*МАССОВОЙ\s*ИНФОРМАЦИИ,\s*ВЫПОЛНЯЮЩИМ\s*ФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА, И\s\(ИЛИ\)\sРОССИЙСКИМ\sЮРИДИЧЕСКИМ ЛИЦОМ,\sВЫПОЛНЯЮЩИМ\sФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА.', '', result)
    result = re.sub(r'Спасите «Медузу»!\s+https:\/\/support\.meduza\.io', '', result)
    result = result.strip()
    return result

def gen_source_digest(config):
    print(f"Generating source digest, config: {config}")
    if config['type'] == 'rss':
        return gen_rss_digest(config)
    elif config['type'] == 'reddit':
        return gen_reddit_digest(config)
    else:
        raise f"Unknown type: {config['type']}"


def load_config():
    global CONFIG
    with open("config.yml", 'r') as stream:
        try:
            print("Read config.yml")
            CONFIG = yaml.safe_load(stream)
            print(CONFIG)
        except yaml.YAMLError as exc:
            print("Failed to read config.yml")
            print(exc)
            exit(1)


def gen_digest():
    load_config()
    return "\n\n\n".join(
        [gen_source_digest(source) for source in CONFIG['sources']])


def mail_digest(digest):
    load_config()

    ssl_context = ssl.create_default_context()
    service = smtplib.SMTP_SSL(CONFIG['mail']['smtp']['address'], int(CONFIG['mail']['smtp']['port']), context=ssl_context)
    service.login(CONFIG['mail']['smtp']['user'], CONFIG['mail']['smtp']['password'])
    body = f"Subject: News Digest\n{digest}"
    service.sendmail(CONFIG['mail']['from'], CONFIG['mail']['to'], body.encode('utf-8'))
