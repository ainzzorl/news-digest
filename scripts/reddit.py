from datetime import datetime, date
import praw
from calendar import monthrange
import hashlib

from util import *


def get_subreddits(session: praw.Reddit, config, source_options=None):
    # If specific subreddits are requested, use only those
    if source_options and "subreddits" in source_options:
        return source_options["subreddits"]

    day_of_week = datetime.now().weekday() + 1  # 1-7
    day_of_month = datetime.now().day - 1  # 0-30
    _, days_in_month = monthrange(datetime.now().year, datetime.now().month)

    print(f"Day of week: {day_of_week}")
    print(f"Day of month: {day_of_month}")
    print(f"Days in this month: {days_in_month}")

    # Given days of week, e.g. [1, 3, 5], select days of month,
    # e.g. all mondays, wednesdays and fridays of this month
    days_for_monthly = []
    # Take only the first 4 weeks of the month,
    # so assignment is consistent across months.
    max_days_for_monthly = len(config["days_for_monthly"]) * 4
    for day in range(days_in_month):
        d = date(datetime.now().year, datetime.now().month, day + 1)
        if d.weekday() + 1 in config["days_for_monthly"]:
            days_for_monthly.append(day + 1)
            if len(days_for_monthly) >= max_days_for_monthly:
                break
    print(f"Days for monthly: {days_for_monthly}")

    sub_candidates = []
    for subreddit in list(session.user.subreddits(limit=None)):  # type: ignore
        if subreddit.display_name in config["exclude"]:
            continue
        frequency = get_frequency(config, subreddit.display_name)
        day = get_day(config, subreddit.display_name)
        sub_candidates.append((subreddit.display_name, frequency, day))

    print("Sub candidates:")
    duration_priorities = {"day": 1, "week": 2, "month": 3}
    sub_candidates = sorted(sub_candidates, key=lambda s: duration_priorities[s[1]])
    print(sub_candidates)

    subs = []
    for subreddit_name, frequency, day in sub_candidates:
        take = False

        if frequency == "day":
            take = True

        if frequency == "week":
            if day == day_of_week:
                print(
                    f"Taking weekly subreddit {subreddit_name}. Day of week: {day_of_week}, day: {day}"
                )
                take = True

        if frequency == "month":
            subreddit_hash = string_to_int_hash(subreddit_name)
            day_for_subreddit = days_for_monthly[subreddit_hash % len(days_for_monthly)]
            print(
                f"Day for subreddit {subreddit_name}: {day_for_subreddit}. Today: {day_of_month + 1}"
            )
            if day_for_subreddit == day_of_month + 1:
                print(f"Taking monthly subreddit {subreddit_name}")
                take = True

        if take:
            subs.append(subreddit_name)
            # print(f'Taking subreddit {subreddit_name}, frequency: {frequency}')

    print(f"Selected subreddits: {subs}")
    return subs


def string_to_int_hash(s: str):
    # Use hashlib to create a hash of the string (MD5 is chosen here)
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def gen_submission_digest(config, subreddit_name, submission):
    digest = f"{submission.title} (score: {submission.score})\n<br>"
    if subreddit_name in config["showself"] and submission.is_self:
        digest += submission.selftext + "\n<br>"
    digest += (
        gen_href(
            f"https://old.reddit.com{submission.permalink}",
            f"https://old.reddit.com{submission.permalink}",
        )
        + "\n<br>"
    )

    if submission.is_self:
        return digest

    if submission.url.startswith("https://www.reddit.com/gallery/"):
        images = get_reddit_gallery_urls(submission)
        if images is not None:
            as_images = 5
            for image in images[:as_images]:
                digest += f"<img src='{image}' style='max-width: {PREFERRED_MAX_IMAGE_WITH}px;'/>\n<br>"
            if len(images) > as_images:
                for image in images[as_images:]:
                    digest += gen_href(image, image) + "\n<br>"
            return digest

    if submission.url.endswith(("jpg", "jpeg", "png", "gif")):
        digest += f"<img src='{submission.url}' style='max-width: {PREFERRED_MAX_IMAGE_WITH}px;'/>\n<br>"
        return digest

    url = submission.url
    if submission.url.startswith("https://v.redd.it/"):
        video_url = get_vreddit(submission)
        if video_url is not None:
            url = video_url
    digest += gen_href(url, url) + "\n<br>"
    return digest


def get_vreddit(submission):
    try:
        if hasattr(submission, "crosspost_parent"):
            secure_media = submission.crosspost_parent_list[0]["secure_media"]
        else:
            secure_media = submission.secure_media
        return secure_media["reddit_video"]["fallback_url"]
    except Exception as e:
        print(f"Failed to fetch video vreddit url for {submission}")
        print(e)
        return None


def get_reddit_gallery_urls(submission):
    try:
        if hasattr(submission, "crosspost_parent"):
            media_metadata = submission.crosspost_parent_list[0]["media_metadata"]
        else:
            media_metadata = submission.media_metadata
        media_metadata = submission.media_metadata
        result = []
        for _k, media in media_metadata.items():
            selected_img = media["p"][0]["u"]
            selected_width = media["p"][0]["x"] if media["p"][0]["x"] else 0
            for m in media["p"]:
                mx = m["x"] if "x" in m else 0
                if mx <= PREFERRED_MAX_IMAGE_WITH and mx >= selected_width:
                    selected_img = m["u"]
                    selected_width = mx
            result.append(selected_img.replace("&amp;", "&"))
        return result
    except Exception as e:
        print(f"Failed to fetch gallery images for {submission}")
        print(e)
        return None


def get_frequency(config, subreddit_name):
    if (
        subreddit_name in config["overrides"]
        and "frequency" in config["overrides"][subreddit_name]
    ):
        return config["overrides"][subreddit_name]["frequency"]
    return config["frequency"]


def get_day(config, subreddit_name):
    if (
        subreddit_name in config["overrides"]
        and "day" in config["overrides"][subreddit_name]
    ):
        return config["overrides"][subreddit_name]["day"]
    return 1


def get_submissions_per_subreddit(config, subreddit_name):
    if (
        subreddit_name in config["overrides"]
        and "submissions_per_subreddit" in config["overrides"][subreddit_name]
    ):
        return config["overrides"][subreddit_name]["submissions_per_subreddit"]
    return config["submissions_per_subreddit"]


def gen_subreddit_digest(session, config, subreddit_name):
    frequency = get_frequency(config, subreddit_name)
    day = get_day(config, subreddit_name)
    submissions = session.subreddit(subreddit_name).top(frequency)

    spoiler = False
    if (
        subreddit_name in config["overrides"]
        and "spoiler" in config["overrides"][subreddit_name]
    ):
        spoiler = config["overrides"][subreddit_name]["spoiler"]

    if frequency == "day":
        max_time_diff = 86400 * 2
    elif frequency == "week":
        max_time_diff = 86400 * 7 * 2
    elif frequency == "month":
        max_time_diff = 86400 * 31 * 2
    else:
        # print(f"Unknown frequency: {frequency}")
        exit(1)

    if frequency == "day":
        frequency_readable = "daily"
    else:
        frequency_readable = f"{frequency}ly"

    try:
        submissions = [
            s
            for s in submissions
            if (
                datetime.now() - datetime.utcfromtimestamp(s.created_utc)
            ).total_seconds()
            <= max_time_diff
        ]
    except Exception as e:
        print(f"Unable to list submissions for {subreddit_name}: {e}")
        digest = f"<h4>/r/{subreddit_name} ({frequency_readable})</h4>"
        digest += f"<p>Unable to list submissions: {e}</p>"
        return digest

    submissions = submissions[: get_submissions_per_subreddit(config, subreddit_name)]

    if not submissions:
        return None

    print(f"Generating subreddit digest for {subreddit_name}")
    digest = f"<h4>/r/{subreddit_name} ({frequency_readable})</h4>"

    body = "\n<br>".join(
        [gen_submission_digest(config, subreddit_name, s) for s in submissions]
    )

    if spoiler:
        div_id = f"subreddit-{subreddit_name}"
        digest += f"""
<button onclick="toggleElement('{div_id}')">Possible spoilers! Toggle</button><br><br>
<div id="{div_id}" style="display: none">
{body}
</div>
"""
    else:
        digest += body

    return digest


def gen_reddit_digest(config, source_options=None):
    session = praw.Reddit(
        user_agent="USERAGENT",
        client_id=config["client_id"],
        client_secret=config["secret"],
        username=config["user"],
        password=config["password"],
    )

    subreddits = get_subreddits(session, config, source_options)

    digest = f"<h2>Reddit ({len(subreddits)} subreddits)</h2>"

    subreddit_digests = [gen_subreddit_digest(session, config, s) for s in subreddits]
    subreddit_digests = [d for d in subreddit_digests if d is not None]

    digest += "\n<br>".join(subreddit_digests)

    return digest
