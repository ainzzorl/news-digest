from typing import Any
import yaml
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import boto3

from news_digest.core.hn import *
from news_digest.core.reddit import *
from news_digest.core.rss import *
from news_digest.core.telegram import *

CONFIG: dict[str, Any] = {}


async def gen_source_digest(config, source_options=None, global_config=None) -> str:
    print(f"Generating source digest, config: {config}, options: {source_options}")
    if config["type"] == "rss":
        return gen_rss_digest(config, source_options)
    elif config["type"] == "reddit":
        return await gen_reddit_digest(config, source_options)
    elif config["type"] == "telegram":
        return await gen_telegram_digest(config, source_options)
    elif config["type"] == "hn":
        return gen_hn_digest(config, source_options, global_config)
    else:
        raise Exception(f"Unknown type: {config['type']}")


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


async def gen_digest(upload_path, source_name=None, source_options=None):
    load_config()
    if source_name:
        # Find the specific source
        source = next((s for s in CONFIG["sources"] if s["name"] == source_name), None)
        if not source:
            raise ValueError(f"Source '{source_name}' not found in config")
        source_results = [await gen_source_digest(source, source_options, CONFIG)]
    else:
        source_results = [
            await gen_source_digest(source, source_options, CONFIG)
            for source in CONFIG["sources"]
        ]

    source_results = [r for r in source_results if r is not None and len(r) > 0]
    script_src = """
    <script>
    function toggleElement(id) {
        var content = document.getElementById(id);
        if (content.style.display === "none" || content.style.display === "") {
        content.style.display = "block";
        } else {
        content.style.display = "none";
        }
    }

    function updateGalleryCounter(galleryId, currentIndex, totalImages) {
        const counter = document.querySelector(`#${galleryId} .gallery-counter`);
        counter.textContent = `${currentIndex + 1} / ${totalImages}`;
    }

    function showImage(galleryId, index) {
        const gallery = document.getElementById(galleryId);
        const images = gallery.getElementsByClassName('gallery-image');
        for (let i = 0; i < images.length; i++) {
            images[i].style.display = i === index ? 'block' : 'none';
        }
        updateGalleryCounter(galleryId, index, images.length);
    }

    function nextImage(galleryId) {
        const gallery = document.getElementById(galleryId);
        const images = gallery.getElementsByClassName('gallery-image');
        let currentIndex = -1;
        for (let i = 0; i < images.length; i++) {
            if (images[i].style.display === 'block') {
                currentIndex = i;
                break;
            }
        }
        const nextIndex = (currentIndex + 1) % images.length;
        showImage(galleryId, nextIndex);
    }

    function prevImage(galleryId) {
        const gallery = document.getElementById(galleryId);
        const images = gallery.getElementsByClassName('gallery-image');
        let currentIndex = -1;
        for (let i = 0; i < images.length; i++) {
            if (images[i].style.display === 'block') {
                currentIndex = i;
                break;
            }
        }
        const prevIndex = (currentIndex - 1 + images.length) % images.length;
        showImage(galleryId, prevIndex);
    }
    </script>"""
    style_src = """
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

        /* Gallery styles */
        .gallery-container {
            margin: 10px 0;
            max-width: 800px;
            width: 100%;
        }
        .gallery-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            max-width: 800px;
            width: 100%;
        }
        .gallery-counter {
            font-weight: bold;
        }
        .gallery-images {
            position: relative;
        }
        .gallery-image {
            transition: opacity 0.3s ease-in-out;
        }
    </style>
    """
    result = f"""<html>
<head>
    <title>News Digest - {datetime.now().strftime('%Y-%m-%d')}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {style_src}
    {script_src}
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
    msg["Subject"] = f"News Digest - {datetime.now().strftime('%Y-%m-%d')}"
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
