import os


PREFERRED_MAX_IMAGE_WITH = 800
ITEM_SEPARATOR = "" + "*" * 80 + "\n<br>\n<br>"


def gen_href(title, href):
    return f'<a target="_blank" href="{href}">{title}</a>'


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


def is_running_in_lambda() -> bool:
    return os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
