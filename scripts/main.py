from news_digest.core.handler import gen_digest
from news_digest.core.handler import mail_digest
from news_digest.core.handler import upload_digest
from pathlib import Path
from datetime import datetime

import sys
import asyncio
import argparse
import requests


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
        "--source",
        "-s",
        type=str,
        help="Generate digest for specific source type (e.g. reddit, rss)",
    )
    parser.add_argument(
        "--subreddits",
        type=str,
        help="Comma-separated list of subreddits to include (only works with reddit source)",
    )
    parser.add_argument("--output", "-o", type=str, help="Output file path")
    parser.add_argument(
        "--skip-lms",
        action="store_true",
        help="Skip loading/unloading LMS model",
    )
    args = parser.parse_args()

    try:
        s3_path = (
            "news-digests/" + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + ".html"
        )

        if args.gen:
            # Start LMS server
            if not args.skip_lms:
                try:
                    print("Starting LMS server...")
                    requests.post(
                        "http://framework-desktop.local:9247/lms/server/start"
                    )
                    print("LMS server started")
                except Exception as e:
                    print(f"Failed to start LMS server (continuing anyway): {e}")

                # Load LMS model
                try:
                    print("Loading LMS model...")
                    requests.post(
                        "http://framework-desktop.local:9247/lms/load",
                        headers={"Content-Type": "application/json"},
                        json={"model": "openai/gpt-oss-120b"},
                    )
                    print("LMS model loaded")
                except Exception as e:
                    print(f"Failed to load LMS model (continuing anyway): {e}")
            else:
                print("Skipping LMS server start/load (--skip-lms flag set)")

            print("Generating digest")
            source_options = {}
            if args.subreddits:
                source_options["subreddits"] = args.subreddits.split(",")
            digest = await gen_digest(
                s3_path, source_name=args.source, source_options=source_options
            )
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
    finally:
        # Unload LMS model only if it was loaded (i.e., in --gen mode and not skipped)
        if args.gen and not args.skip_lms:
            try:
                print("Unloading LMS model...")
                requests.post("http://framework-desktop.local:9247/lms/unload")
                print("LMS model unloaded")
            except Exception as e:
                print(f"Failed to unload LMS model (continuing anyway): {e}")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
