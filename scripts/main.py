from handler import gen_digest
from handler import mail_digest
from handler import upload_digest
from pathlib import Path
from datetime import datetime

import sys
import asyncio
import argparse


def lambda_handler(event, context):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(inner_lambda_handler(event, context))


async def inner_lambda_handler(event, context):
    s3_path = "news-digests/" + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".html"
    digest = await gen_digest(s3_path)
    mail_digest(digest)
    upload_digest(digest, s3_path)


async def main():
    parser = argparse.ArgumentParser(description="Generate news digest")
    parser.add_argument("--gen", action="store_true", help="Generate digest")
    parser.add_argument("--mail", action="store_true", help="Mail digest")
    parser.add_argument("--upload", action="store_true", help="Upload digest")
    parser.add_argument(
        "--source", "-s", type=str, help="Generate digest for specific source only"
    )
    parser.add_argument("--output", "-o", type=str, help="Output file path")
    args = parser.parse_args()

    s3_path = "news-digests/" + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".html"

    if args.gen:
        print("Generating digest")
        digest = await gen_digest(s3_path, source_name=args.source)
    else:
        print("Using dummy digest")
        digest = """\
    <html>
    <head></head>
    <body>
    <p>Hi!<br>
        How are <b>you</b>?<br>
        Here is the <a href="http://www.python.org">link</a> you wanted.
    </p>
    </body>
    </html>
    """

    if args.output:
        print(f"Writing digest to {args.output}")
        with open(args.output, "w") as text_file:
            text_file.write(digest)
    else:
        print("Skipping file output")

    if args.mail:
        print("Mailing digest")
        mail_digest(digest)
    else:
        print("Skipping mailing")

    if args.upload:
        print("Uploading digest")
        upload_digest(digest, s3_path)
    else:
        print("Skipping uploading")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
