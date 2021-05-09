import yaml
import feedparser
from datetime import datetime
from time import mktime
import html2text
import re
import smtplib
from email.message import EmailMessage
import ssl
import os
from googleapiclient.discovery import build
from googleapiclient import errors, discovery
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from oauth2client import client, tools, file
import base64
import httplib2
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
        f"{h.handle(item.description).strip()}" for item in items
    ]
    stories = [
        re.sub(
            '!\[\]\(http://feeds\.feedburner.com\/~[\s\S]*\/rss\/cnn_topstories.*\)',
            '', story).strip() + "\n" for story in stories
    ]
    digest += ITEM_SEPARATOR.join(stories)

    return digest


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

    client_id = CONFIG['mail']['gmail']['client_id']
    client_secret = CONFIG['mail']['gmail']['client_secret']
    refresh_token = CONFIG['mail']['gmail']['refresh_token']
    credentials = client.GoogleCredentials(
        None, client_id, client_secret, refresh_token, None,
        "https://accounts.google.com/o/oauth2/token", 'my-user-agent')

    http = credentials.authorize(httplib2.Http())
    service = discovery.build('gmail', 'v1', http=http, cache_discovery=False)
    msg = EmailMessage()
    msg['Subject'] = 'News Digest'
    msg['To'] = CONFIG['mail']['to']
    msg['From'] = CONFIG['mail']['from']
    msg.set_content(digest)

    msg_to_send = {
        'raw':
        base64.urlsafe_b64encode(
            msg.as_string().encode('UTF-8')).decode('ascii')
    }

    try:
        message = (service.users().messages().send(userId='me',
                                                   body=msg_to_send).execute())
        print('Message Id: %s' % message['id'])
    except errors.HttpError as error:
        print('An error occurred: %s' % error)
        exit(1)
