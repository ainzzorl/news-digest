import yaml
import feedparser
from datetime import datetime
from time import mktime
import html2text
import re
import smtplib
import ssl
import praw
import json
import urllib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CONFIG = None
ITEM_SEPARATOR = "" + "*" * 80 + "\n<br>\n<br>"


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
    digest = f"{submission.title} (score: {submission.score})\n<br>"
    if subreddit.display_name in config['showself'] and submission.is_self:
        digest += submission.selftext + "\n<br>"
    digest += f"<a href='{submission.url}'>{submission.url}</a>\n<br>"
    digest += f"<a href='https://old.reddit.com{submission.permalink}'>https://old.reddit.com{submission.permalink}</a>\n<br>"
    if submission.url.endswith(('jpg', 'jpeg', 'png', 'gif')):
        digest += f"<img src='{submission.url}'/>\n<br>"
    # if submission.url.startswith('https://v.redd.it/'):
    #     video_url, height, width = get_vreddit(f'https://www.reddit.com{submission.permalink}')
    #     if video_url is not None:
    #         digest += f"""<video style='height: 100vh; width: 100%; object-fit: fill position: absolute;' controls>
    #         <source src='{video_url}'/>
    #         </video>"""
    return digest

def get_vreddit(submission_url):
    try:
        with urllib.request.urlopen(submission_url + '.json') as url:
            data = json.loads(url.read().decode())
            # print("###")
            # print(data)
            v = data[0]['data']['children'][0]['data']['secure_media']['reddit_video']
            return (v['fallback_url'], v['height'], v['width'])
    except Exception as e:
        print(f"Failed to fetch video vreddit url for {submission_url}")
        print(e)
        return (None, None, None)

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
        #print(f"Unknown frequency: {frequency}")
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
    digest = f"<h4>/r/{subreddit.display_name} ({frequency_readable})</h4>"

    digest += "\n<br>".join(
        [gen_submission_digest(config, subreddit, s) for s in submissions])

    return digest


def gen_reddit_digest(config):
    session = praw.Reddit(user_agent='USERAGENT',
                          client_id=config['client_id'],
                          client_secret=config['secret'],
                          username=config['user'],
                          password=config['password'])

    subreddits = get_subreddits(session, config)

    digest = f"<h2>Reddit ({len(subreddits)} subreddits)</h2>\n<br>"

    subreddit_digests = [
        gen_subreddit_digest(session, config, s) for s in subreddits
    ]
    subreddit_digests = [d for d in subreddit_digests if d is not None]

    digest += "\n<br>".join(subreddit_digests)

    return digest


def gen_rss_digest(config):
    feed = feedparser.parse(config['url'])
    #print(feed.feed)
    items = feed.entries
    # if items:
    #     print(items[0])
    items = [
        item for item in items
        if ('published_parsed' in item and
            (datetime.now() -
             datetime.fromtimestamp(mktime(item.published_parsed))
             ).total_seconds() <= CONFIG['max_time_diff_seconds'])
    ]

    digest = f"<h2>{feed.feed.title} ({len(items)} item(s))</h2>\n\n"

    # h = html2text.HTML2Text()
    # h.ignore_links = True

    stories = [rss_story_to_html(item) for item in items]
    stories = [
        re.sub(
            '!\[\]\(http://feeds\.feedburner.com\/~[\s\S]*\/rss\/cnn_topstories.*\)',
            '', story).strip() + "\n" for story in stories
    ]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest

def rss_story_to_html(item):
    result = f"{item.title}\n<br>" + f"<a href='{item.link}'>{item.link}</a>\n<br>" + f"{item.published}\n<br>" + f"{process_rss_description(item.description)}"
    for link in item.links:
        if link.type.startswith('image/'):
            image_url = link.href
            result += f"<img src='{image_url}'/>\n<br>"
    return result

def process_rss_description(description):
    result = description
    #result = h.handle(result)
    result = re.sub(r'ДАННОЕ\s*СООБЩЕНИЕ\s*\(МАТЕРИАЛ\)\s*СОЗДАНО\s*И\s*\(ИЛИ\)\s*РАСПРОСТРАНЕНО\s*ИНОСТРАННЫМ\s*СРЕДСТВОМ\s*МАССОВОЙ\s*ИНФОРМАЦИИ,\s*ВЫПОЛНЯЮЩИМ\s*ФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА, И\s\(ИЛИ\)\sРОССИЙСКИМ\sЮРИДИЧЕСКИМ ЛИЦОМ,\sВЫПОЛНЯЮЩИМ\sФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА.', '', result)
    result = re.sub(r'Спасите «Медузу»!.*https:\/\/support\.meduza\.io', '', result)
    result = result.strip()
    return result

def gen_source_digest(config):
    #print(f"Generating source digest, config: {config}")
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
            #print("Read config.yml")
            CONFIG = yaml.safe_load(stream)
            #print(CONFIG)
        except yaml.YAMLError as exc:
            print("Failed to read config.yml")
            print(exc)
            exit(1)


def gen_digest():
    load_config()
    return '<html><body>' + "\n<br>".join(
        [gen_source_digest(source) for source in CONFIG['sources']]) + '</body></html>'


def mail_digest(digest):
    load_config()

    ssl_context = ssl.create_default_context()
    service = smtplib.SMTP_SSL(CONFIG['mail']['smtp']['address'], int(CONFIG['mail']['smtp']['port']), context=ssl_context)
    service.login(CONFIG['mail']['smtp']['user'], CONFIG['mail']['smtp']['password'])

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "News Digest"
    msg['From'] = CONFIG['mail']['from']
    msg['To'] = CONFIG['mail']['to']
    part1 = MIMEText(digest, 'html')
    msg.attach(part1)

    service.sendmail(CONFIG['mail']['from'], CONFIG['mail']['to'], msg.as_string().encode('utf-8'))
