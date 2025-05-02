import yaml
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import boto3

from hn import *
from reddit import *
from rss import *
from telegram import *

CONFIG = None


async def gen_source_digest(config):
    print(f"Generating source digest, config: {config}")
    if config["type"] == "rss":
        return gen_rss_digest(config)
    elif config["type"] == "reddit":
        return gen_reddit_digest(config)
    elif config["type"] == "telegram":
        return await gen_telegram_digest(config)
    elif config["type"] == "hn":
        return gen_hn_digest(config)
    else:
        raise f"Unknown type: {config['type']}"


def load_config():
    global CONFIG
    with open("config.yml", "r") as stream:
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
    source_results = [await gen_source_digest(source) for source in CONFIG["sources"]]
    source_results = [r for r in source_results if r is not None and len(r) > 0]
    result = """<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        /* Default (light mode) styles */
        body {
        background-color: white;
        color: black;
        }

        /* Dark mode styles */
        @media (prefers-color-scheme: dark) {
        body {
            background-color: #121212;
            color: white;
        }
        }
    </style>
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
</head>
    <body>"""
    if upload_path:
        upload_url = f"https://{CONFIG['s3']['bucket']}.s3.{CONFIG['s3']['region']}.amazonaws.com/{upload_path}"
    result += f'<p><a href="{upload_url}">View on web.</a></p>'
    result += "\n<br>".join(source_results)
    result += "</body></html>"
    return result


def mail_digest(digest):
    load_config()

    ssl_context = ssl.create_default_context()
    service = smtplib.SMTP_SSL(
        CONFIG["mail"]["smtp"]["address"],
        int(CONFIG["mail"]["smtp"]["port"]),
        context=ssl_context,
    )
    service.login(CONFIG["mail"]["smtp"]["user"], CONFIG["mail"]["smtp"]["password"])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "News Digest"
    msg["From"] = CONFIG["mail"]["from"]
    msg["To"] = CONFIG["mail"]["to"]
    part1 = MIMEText(digest, "html")
    msg.attach(part1)

    service.sendmail(
        CONFIG["mail"]["from"], CONFIG["mail"]["to"], msg.as_string().encode("utf-8")
    )


def upload_digest(digest, path):
    load_config()

    if not CONFIG["s3"]:
        print("No S3 config, skipping S3 upload")
        return

    s3 = boto3.client("s3")

    # Upload the text
    s3.put_object(
        Bucket=CONFIG["s3"]["bucket"],
        Key=path,
        Body=digest,
        ContentType="text/html; charset=utf-8",
    )

    print(f"Uploaded digest to s3://{CONFIG['s3']['bucket']}/{path}")
