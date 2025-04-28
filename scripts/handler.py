import yaml
import feedparser
from datetime import datetime, date
from time import mktime
import re
import smtplib
import ssl
import praw
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.users import GetFullUserRequest
import telethon
import shutil
import urllib.request
import json
from calendar import monthrange
import base64
import hashlib
import boto3

CONFIG = None
ITEM_SEPARATOR = "" + "*" * 80 + "\n<br>\n<br>"


def get_subreddits(session, config):
    day_of_week = datetime.now().weekday() + 1 # 1-7
    day_of_month = datetime.now().day - 1 # 0-30
    _, days_in_month = monthrange(datetime.now().year, datetime.now().month)

    print(f'Day of week: {day_of_week}')
    print(f'Day of month: {day_of_month}')
    print(f'Days in this month: {days_in_month}')

    # Given days of week, e.g. [1, 3, 5], select days of month,
    # e.g. all mondays, wednesdays and fridays of this month
    days_for_monthly = []
    # Take only the first 4 weeks of the month,
    # so assignment is consistent across months.
    max_days_for_monthly = len(config['days_for_monthly']) * 4
    for day in range(days_in_month):
        d = date(datetime.now().year, datetime.now().month, day + 1)
        if d.weekday() + 1 in config['days_for_monthly']:
            days_for_monthly.append(day + 1)
            if len(days_for_monthly) >= max_days_for_monthly:
                break
    print(f'Days for monthly: {days_for_monthly}')


    sub_candidates = []
    for subreddit in list(session.user.subreddits(limit=None)):
        if subreddit.display_name in config['exclude']:
            continue
        frequency = get_frequency(config,
                                  subreddit.display_name)
        day = get_day(config,
                      subreddit.display_name)
        sub_candidates.append((subreddit.display_name, frequency, day))

    if 'extra' in config:
        for subreddit_name, c in config['extra'].items():
            day = get_day(config,
                          subreddit_name)
            sub_candidates.append((subreddit_name, c['frequency'], day))

    print('Sub candidates:')
    duration_priorities = {
        'day': 1,
        'week': 2,
        'month': 3
    }
    sub_candidates = sorted(
        sub_candidates, key=lambda s: duration_priorities[s[1]])
    print(sub_candidates)

    subs = []
    for subreddit_name, frequency, day in sub_candidates:
        take = False

        if frequency == 'day':
            take = True

        if frequency == 'week':
            if day == day_of_week:
                print(f'Taking weekly subreddit {subreddit_name}. Day of week: {day_of_week}, day: {day}')
                take = True

        if frequency == 'month':
            subreddit_hash = string_to_int_hash(subreddit_name)
            day_for_subreddit = days_for_monthly[subreddit_hash % len(days_for_monthly)]
            print(f'Day for subreddit {subreddit_name}: {day_for_subreddit}. Today: {day_of_month + 1}')
            if day_for_subreddit == day_of_month + 1:
                print(f'Taking monthly subreddit {subreddit_name}')
                take = True

        if take:
            subs.append(subreddit_name)
            # print(f'Taking subreddit {subreddit_name}, frequency: {frequency}')

    print(f'Selected subreddits: {subs}')
    return subs

def string_to_int_hash(s):
    # Use hashlib to create a hash of the string (MD5 is chosen here)
    return int(hashlib.md5(s.encode()).hexdigest(), 16)

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
    if 'extra' in config and subreddit_name in config['extra'] and 'frequency' in config[
            'extra'][subreddit_name]:
        return config['extra'][subreddit_name]['frequency']
    return config['frequency']

def get_day(config, subreddit_name):
    if subreddit_name in config['overrides'] and 'day' in config[
            'overrides'][subreddit_name]:
        return config['overrides'][subreddit_name]['day']
    if 'extra' in config and subreddit_name in config['extra'] and 'day' in config[
            'extra'][subreddit_name]:
        return config['extra'][subreddit_name]['day']
    return 1

def gen_subreddit_digest(session, config, subreddit_name):
    frequency = get_frequency(config, subreddit_name)
    day = get_day(config, subreddit_name)
    submissions = session.subreddit(subreddit_name).top(frequency)

    spoiler = False
    if subreddit_name in config['overrides'] and 'spoiler' in config['overrides'][subreddit_name]:
        spoiler = config['overrides'][subreddit_name]['spoiler']

    if frequency == 'day':
        max_time_diff = 86400 * 2
    elif frequency == 'week':
        max_time_diff = 86400 * 7 * 2
    elif frequency == 'month':
        max_time_diff = 86400 * 31 * 2
    else:
        # print(f"Unknown frequency: {frequency}")
        exit(1)

    if frequency == 'day':
        frequency_readable = 'daily'
    else:
        frequency_readable = f'{frequency}ly'

    try:
        submissions = [
            s for s in submissions
            if (datetime.now() - datetime.utcfromtimestamp(s.created_utc)
                ).total_seconds() <= max_time_diff
        ]
    except Exception as e:
        print(f'Unable to list submissions for {subreddit_name}: {e}')
        digest = f"<h4>/r/{subreddit_name} ({frequency_readable})</h4>"
        digest += f'<p>Unable to list submissions: {e}</p>'
        return digest

    submissions = submissions[:config['submissions_per_subreddit']]

    if not submissions:
        return None

    print(f"Generating subreddit digest for {subreddit_name}")
    digest = f"<h4>/r/{subreddit_name} ({frequency_readable})</h4>"

    body = "\n<br>".join(
        [gen_submission_digest(config, subreddit_name, s) for s in submissions])

    if spoiler:
        div_id = f'subreddit-{subreddit_name}'
        digest += f'''
<button onclick="toggleElement('{div_id}')">Possible spoilers! Toggle</button><br><br>
<div id="{div_id}" style="display: none">
{body}
</div>
'''
    else:
        digest += body

    return digest


def gen_reddit_digest(config):
    session = praw.Reddit(user_agent='USERAGENT',
                          client_id=config['client_id'],
                          client_secret=config['secret'],
                          username=config['user'],
                          password=config['password'])

    subreddits = get_subreddits(session, config)

    digest = f"<h2>Reddit ({len(subreddits)} subreddits)</h2>"

    subreddit_digests = [
        gen_subreddit_digest(session, config, s) for s in subreddits
    ]
    subreddit_digests = [d for d in subreddit_digests if d is not None]

    digest += "\n<br>".join(subreddit_digests)

    return digest


def gen_rss_digest(config):
    current_day = datetime.now().weekday() + 1
    if current_day not in config['days']:
        print(f'Skipping {config["name"]}, not in days {config["days"]}. Current day: {current_day}')
        return ''

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


def gen_hn_digest(config):
    feed = feedparser.parse(config['url'])
    print(feed.feed)

    current_day = datetime.now().weekday() + 1
    if current_day not in config['days']:
        print(f'Skipping {config["name"]}, not in days {config["days"]}. Current day: {current_day}')
        return ''

    days_to_take = 1
    if config['include_days_since_last'] == 'yes':
        days_to_take = days_since_last_included_day(current_day, config['days'])
    seconds_to_take = days_to_take * 86400
    print(f'Days to take for HN: {days_to_take}')


    items = feed.entries
    items = [
        item for item in items
        if ('published_parsed' in item and
            (datetime.now() -
             datetime.fromtimestamp(mktime(item.published_parsed))
             ).total_seconds() <= seconds_to_take)
    ]

    digest = f"<h2>{config['name']} ({len(items)} item(s))</h2>\n\n"

    stories = [hn_item_to_html(config, item) for item in items]
    stories = [
        re.sub(
            '!\[\]\(http://feeds\.feedburner.com\/~[\s\S]*\/rss\/cnn_topstories.*\)',
            '', story).strip() + "\n<br>" for story in stories
    ]
    digest += "\n" + ITEM_SEPARATOR.join(stories)

    return digest


def hn_item_to_html(config, item):
    result = f"{item.title}\n<br>" + f"<a href='{item.link}'>{item.link}</a>\n<br>" + \
        f"{item.published}\n<br>" + \
        f"{process_rss_description(item.description)}"
    image_urls = '\n<br>'.join(
        [f"<img src='{link.href}'/>" for link in item.links if link.type.startswith('image/')])
    comments_url = item.comments
    story_id = comments_url.replace(
        'https://news.ycombinator.com/item?id=', '')

    comments_html = 'Top comments:<br><br>\n'
    try:
        story_content = urllib.request.urlopen(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json").read()
        story_json = json.loads(story_content)
        per_comment_htmls = []
        for comment_id in story_json['kids'][:config['top_comments']]:
            comment_content = urllib.request.urlopen(
                f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json").read()
            comment_json = json.loads(comment_content)
            per_comment_htmls.append(comment_json['text'])
        comments_html += '<br><br>~~~~~~~~~~<br><br>\n'.join(per_comment_htmls)
        comments_html += '<br>\n'

    except Exception as e:
        print(f'Error processing story {story_id}: {e}')
    return result + image_urls + comments_html


def rss_story_to_html(item):
    result = f"{item.title}\n<br>" + f"<a href='{item.link}'>{item.link}</a>\n<br>" + \
        f"{item.published}\n<br>" + \
        f"{process_rss_description(item.description if hasattr(item, 'description') else 'N/A')}"
    # image_urls = '\n<br>'.join(
    #     [f"<img src='{link.href}'/>" for link in item.links if link.type.startswith('image/')])
    # return result + image_urls
    return result


def process_rss_description(description):
    result = description
    # result = h.handle(result)
    result = re.sub(r'ДАННОЕ\s*СООБЩЕНИЕ\s*\(МАТЕРИАЛ\)\s*СОЗДАНО\s*И\s*\(ИЛИ\)\s*РАСПРОСТРАНЕНО\s*ИНОСТРАННЫМ\s*СРЕДСТВОМ\s*МАССОВОЙ\s*ИНФОРМАЦИИ,\s*ВЫПОЛНЯЮЩИМ\s*ФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА, И\s\(ИЛИ\)\sРОССИЙСКИМ\sЮРИДИЧЕСКИМ ЛИЦОМ,\sВЫПОЛНЯЮЩИМ\sФУНКЦИИ\sИНОСТРАННОГО\sАГЕНТА.', '', result)
    result = re.sub(
        r'Спасите «Медузу»!.*https:\/\/support\.meduza\.io', '', result)
    result = result.strip()
    return result


async def gen_telegram_digest(config):
    res = ''
    res += '<h2>Telegram</h2>'

    shutil.copyfile('session_name.session', '/tmp/session_name.session')

    async with TelegramClient('/tmp/session_name.session', config['api_id'], config['api_hash']) as client:
        # For testing one channel
        # return await gen_telegram_channel_digest(config, client, <id>)

        channel_id_to_text = {}

        async for dialog in client.iter_dialogs():
            if (datetime.now().astimezone() - dialog.date).days >= 3:
                print(f'Date too far: {dialog.date}, stopping')
                break

            channel_entity = await client.get_entity(dialog.id)
            if not isinstance(channel_entity, telethon.tl.types.Chat) and not isinstance(channel_entity, telethon.tl.types.Channel):
                print(f'Skipping {dialog.id}, wrong type')
                continue

            channel_id_to_text[channel_entity.id] = await gen_telegram_channel_digest(config, client, channel_entity)

        # First add channels that are in config['channels']
        for channel in config['channels']:
            if channel['id'] in channel_id_to_text:
                res += channel_id_to_text[channel['id']]

        # Then add channels that are not in config['channels']
        for channel_id, text in channel_id_to_text.items():
            if channel_id not in [c['id'] for c in config['channels']]:
                res += text

    return res

async def gen_telegram_channel_digest(config, client, channel_entity):
    res = ''
    print(f"Processing chat: {channel_entity.title}, channel id: {channel_entity.id}")
    if channel_entity.id in config['except_chat_ids']:
        print(f'Excluding {channel_entity.id} ({channel_entity.title})')
        return ''

    # Get config for this channel
    channel_config = next((c for c in config['channels'] if c['id'] == channel_entity.id), None)

    current_day = datetime.now().weekday() + 1

    if channel_config is not None and 'days' in channel_config:
        if current_day not in channel_config['days']:
            print(f'Skipping {channel_entity.id} ({channel_entity.title}), not in days {channel_config["days"]}. Current day: {current_day}')
            return ''

    filters = channel_config['filters'] if channel_config is not None and 'filters' in channel_config else {}
    include_filters = filters['include'] if 'include' in filters else []

    posts = await client(GetHistoryRequest(
        peer=channel_entity,
        limit=100,
        offset_date=None,
        offset_id=0,
        max_id=0,
        min_id=0,
        add_offset=0,
        hash=0))
    posts_str = ''
    total_posts = 0

    selected_posts = []
    for post in posts.messages:
        ago = datetime.now().astimezone() - post.date
        days = channel_config['days'] if channel_config is not None and 'days' in channel_config else default_days()
        days_to_take = 1
        if channel_config is not None and 'include_days_since_last' in channel_config and channel_config['include_days_since_last'] == 'yes':
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
            #print("Ignoring MessageActionChatAddUser")
            continue

        if hasattr(post, 'from_id') and hasattr(post.from_id, 'user_id'):
            user_id = post.from_id.user_id
            full_user = await get_telegram_user(client, user_id)
        else:
            user_id = 'undefined'
            full_user = None
        if user_id in config['silenced_user_ids']:
            posts_str += f"<span><i>Silenced user: {user_id}</i></span>"
            posts_str += "<br>\n"
            continue

        user_info_suffix = ''
        if full_user is not None:
            user_info_suffix += f" - {full_user.username}"
            if full_user.first_name is not None:
                user_info_suffix += f" ({full_user.first_name}"
                if full_user.last_name is not None:
                    user_info_suffix += f" {full_user.last_name}"
                user_info_suffix += f")"

        posts_str += f"<b>{str(post.date)}{user_info_suffix}</b>" + "<br>\n"
        if hasattr(channel_entity, 'username') and channel_entity.username is not None:
            usr = channel_entity.username
            url = "https://t.me/" + str(usr) + "/" + str(post.id)
            posts_str += f'<a href="{url}">{url}</a><br>\n'

        post_message = str(post.message).replace('\n', '<br>\n')
        posts_str += post_message
        posts_str += "<br>\n"

        media_tag = await get_post_media_tag(client, post, no_media = channel_entity.id in config['no_media'])
        posts_str += media_tag

        if len(str(post.message)) == 0 and len(media_tag) == 0:
            posts_str += str(post)

        posts_str += "<br>\n"

    if total_posts == 0:
        print(
            f'Chat with no messages: {channel_entity.title}, id={channel_entity.id}.')
        return ''
    else:
        res += f'<h4>{channel_entity.title} ({total_posts} item(s), id={channel_entity.id})</h4>'
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
        return '<span><i>Unsupported message type: audio</i></span>'
    if post.gif is not None:
        return '<span><i>Unsupported message type: gif</i></span>'
    if post.sticker is not None:
        return '<span><i>Unsupported message type: sticker</i></span>'
    if post.video is not None:
        return '<span><i>Unsupported message type: video</i></span>'
    if post.video_note is not None:
        return '<span><i>Unsupported message type: video note</i></span>'
    if post.voice is not None:
        return '<span><i>Unsupported message type: voice</i></span>'
    if post.poll is not None:
        return '<span><i>Unsupported message type: poll</i></span>'

    if post.photo is None:
        return ''
    if no_media:
        return '<span><i>Not including media for this channel</i></span>'

    ext_to_mime = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    if post.file.ext not in ext_to_mime:
        return f'<span><i>Unsupported image extension: {post.file.ext}</i></span>'
    mime = ext_to_mime[post.file.ext]

    thumb = None
    for (i, size) in enumerate(post.photo.sizes):
        if hasattr(size, 'w') and size.w <= 800:
            thumb = i

    blob = await client.download_media(post, bytes, thumb=thumb)
    encoded = base64.b64encode(blob).decode('utf-8')

    return f"<img src=\"data:{mime};base64, {encoded}\" alt=\"Image\"/>"


async def gen_source_digest(config):
    print(f"Generating source digest, config: {config}")
    if config['type'] == 'rss':
        return gen_rss_digest(config)
    elif config['type'] == 'reddit':
        return gen_reddit_digest(config)
    elif config['type'] == 'telegram':
        return await gen_telegram_digest(config)
    elif config['type'] == 'hn':
        return gen_hn_digest(config)
    else:
        raise f"Unknown type: {config['type']}"


def load_config():
    global CONFIG
    with open("config.yml", 'r') as stream:
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
    source_results = [await gen_source_digest(source) for source in CONFIG['sources']]
    source_results = [r for r in source_results if r is not None and len(r) > 0]
    result = '''<html>
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
    <body>'''
    if upload_path:
        upload_url = f"https://{CONFIG['s3']['bucket']}.s3.{CONFIG['s3']['region']}.amazonaws.com/{upload_path}"
    result += f'<p><a href="{upload_url}">View on web.</a></p>'
    result += "\n<br>".join(source_results)
    result += '</body></html>'
    return result

def mail_digest(digest):
    load_config()

    ssl_context = ssl.create_default_context()
    service = smtplib.SMTP_SSL(CONFIG['mail']['smtp']['address'], int(
        CONFIG['mail']['smtp']['port']), context=ssl_context)
    service.login(CONFIG['mail']['smtp']['user'],
                  CONFIG['mail']['smtp']['password'])

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "News Digest"
    msg['From'] = CONFIG['mail']['from']
    msg['To'] = CONFIG['mail']['to']
    part1 = MIMEText(digest, 'html')
    msg.attach(part1)

    service.sendmail(CONFIG['mail']['from'], CONFIG['mail']
                     ['to'], msg.as_string().encode('utf-8'))

def upload_digest(digest, path):
    load_config()

    if not CONFIG['s3']:
        print('No S3 config, skipping S3 upload')
        return

    s3 = boto3.client('s3')

    # Upload the text
    s3.put_object(Bucket=CONFIG['s3']['bucket'], Key=path, Body=digest, ContentType='text/html; charset=utf-8')

    print(f"Uploaded digest to s3://{CONFIG['s3']['bucket']}/{path}")
