import yaml
import feedparser
from datetime import datetime
from time import mktime
import re
import smtplib
import ssl
import praw
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest, GetAllChatsRequest
import shutil

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
        subs.append(subreddit.display_name)

    if 'extra' in config:
        print(config['extra'])
        for subreddit_name, c in config['extra'].items():
            if c['frequency'] == 'day' or isweek:
                subs.append(subreddit_name)

    return subs

def gen_submission_digest(config, subreddit_name, submission):
    digest = f"{submission.title} (score: {submission.score})\n<br>"
    if subreddit_name in config['showself'] and submission.is_self:
        digest += submission.selftext + "\n<br>"
    digest += f"<a href='https://old.reddit.com{submission.permalink}'>https://old.reddit.com{submission.permalink}</a>\n<br>"

    if submission.is_self:
        return digest

    if submission.url.startswith('https://www.reddit.com/gallery/'):
        images = get_reddit_gallery_urls(submission)
        if images is not None:
            as_images = 5
            for image in images[:as_images]:
                digest += f"<img src='{image}'/>\n<br>"
            if len(images) > as_images:
                for image in images[as_images:]:
                    digest += f"<a href='{image}'>{image}</a>\n<br>"
            return digest

    if submission.url.endswith(('jpg', 'jpeg', 'png', 'gif')):
        digest += f"<img src='{submission.url}'/>\n<br>"
        return digest

    url = submission.url
    if submission.url.startswith('https://v.redd.it/'):
        video_url = get_vreddit(submission)
        if video_url is not None:
            url = video_url
    digest += f"<a href='{url}'>{url}</a>\n<br>"
    return digest

def get_vreddit(submission):
    try:
        if hasattr(submission, "crosspost_parent"):
            secure_media = submission.crosspost_parent_list[0]['secure_media']
        else:
            secure_media = submission.secure_media
        return secure_media['reddit_video']['fallback_url']
    except Exception as e:
        print(f"Failed to fetch video vreddit url for {submission}")
        print(e)
        return None

def get_reddit_gallery_urls(submission):
    try:
        if hasattr(submission, "crosspost_parent"):
            media_metadata = submission.crosspost_parent_list[0]['media_metadata']
        else:
            media_metadata = submission.media_metadata
        media_metadata = submission.media_metadata
        result = []
        for _k, media in media_metadata.items():
            img = media['p'][-1]
            result.append(img['u'].replace('&amp;', '&'))
        return result
    except Exception as e:
        print(f"Failed to fetch gallery images for {submission}")
        print(e)
        return None

def get_frequency(config, subreddit_name):
    if subreddit_name in config['overrides'] and 'frequency' in config[
            'overrides'][subreddit_name]:
        return config['overrides'][subreddit_name]['frequency']
    return config['frequency']


def gen_subreddit_digest(session, config, subreddit_name):
    frequency = get_frequency(config, subreddit_name)
    submissions = session.subreddit(subreddit_name).top(frequency)

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
    print(f"Generating subreddit digest for {subreddit_name}")
    digest = f"<h4>/r/{subreddit_name} ({frequency_readable})</h4>"

    digest += "\n<br>".join(
        [gen_submission_digest(config, subreddit_name, s) for s in submissions])

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
    print(feed.feed)
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

    digest = f"<h2>{config['name']} ({len(items)} item(s))</h2>\n\n"

    # h = html2text.HTML2Text()
    # h.ignore_links = True

    stories = [rss_story_to_html(item) for item in items]
    stories = [
        re.sub(
            '!\[\]\(http://feeds\.feedburner.com\/~[\s\S]*\/rss\/cnn_topstories.*\)',
            '', story).strip() + "\n<br>" for story in stories
    ]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest

def rss_story_to_html(item):
    result = f"{item.title}\n<br>" + f"<a href='{item.link}'>{item.link}</a>\n<br>" + f"{item.published}\n<br>" + f"{process_rss_description(item.description)}"
    image_urls = '\n<br>'.join([f"<img src='{link.href}'/>" for link in item.links if link.type.startswith('image/')])
    return result + image_urls

def process_rss_description(description):
    result = description
    #result = h.handle(result)
    result = re.sub(r'ДАННОЕ\s*СООБЩЕНИЕ\s*\(МАТЕРИАЛ\)\s*СОЗДАНО\s*И\s*\(ИЛИ\)\s*РАСПРОСТРАНЕНО\s*ИНОСТРАННЫМ\s*СРЕДСТВОМ\s*МАССОВОЙ\s*ИНФОРМАЦИИ,\s*ВЫПОЛНЯЮЩИМ\s*ФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА, И\s\(ИЛИ\)\sРОССИЙСКИМ\sЮРИДИЧЕСКИМ ЛИЦОМ,\sВЫПОЛНЯЮЩИМ\sФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА.', '', result)
    result = re.sub(r'Спасите «Медузу»!.*https:\/\/support\.meduza\.io', '', result)
    result = result.strip()
    return result

def gen_telegram_digest(config):
    # TODO: pull from S3 or somewhere
    res = ''
    res += '<h2>Telegram</h2><br>'

    shutil.copyfile('session_name.session', '/tmp/session_name.session')

    with TelegramClient('/tmp/session_name.session', config['api_id'], config['api_hash']) as client:
        my_chats = client(GetAllChatsRequest(except_ids=config['except_chat_ids'])).chats
        for chat in my_chats:
            channel_entity=client.get_entity(chat.id)
            print(f"Processing chat: {channel_entity.title}")
            # print(channel_entity)
            posts = client(GetHistoryRequest(
                peer=channel_entity,
                limit=50,
                offset_date=None,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0))
            posts_str = ''
            total_posts = 0
            for post in posts.messages:
                # if post.message is None:
                #     print("### None")
                #     print(post)
                ago = datetime.now().astimezone() - post.date
                if ago.days >= 1:
                    break
                total_posts += 1
                posts_str += f"<b>{str(post.date)}</b>" + "<br>\n"
                if hasattr(channel_entity, 'username'):
                    usr = channel_entity.username
                    url = "https://t.me/" + str(usr) + "/" + str(post.id)
                    posts_str += f'<a href="{url}">{url}</a><br>\n'
                posts_str += str(post.message) + "<br>\n"
                posts_str += "<br>\n"
            if total_posts == 0:
                print(f'Chat with no messages: {channel_entity.title}, id={channel_entity.id}.')
            else:
                res += f'<h4>{channel_entity.title} ({total_posts} item(s), id={channel_entity.id})</h4>'
                res += posts_str

    return res

def gen_source_digest(config):
    print(f"Generating source digest, config: {config}")
    if config['type'] == 'rss':
        return gen_rss_digest(config)
    elif config['type'] == 'reddit':
        return gen_reddit_digest(config)
    elif config['type'] == 'telegram':
        return gen_telegram_digest(config)
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
