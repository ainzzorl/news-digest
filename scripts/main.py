from handler import gen_digest
from handler import mail_digest
from handler import upload_digest
from pathlib import Path
from datetime import datetime

import sys
import asyncio

def lambda_handler(event, context):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(inner_lambda_handler(event, context))

async def inner_lambda_handler(event, context):
    s3_path = 'news-digests/' + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + '.html'
    digest = await gen_digest(s3_path)
    mail_digest(digest)
    upload_digest(digest, s3_path)

async def main():
    s3_path = 'news-digests/' + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + '.html'

    if 'gen' in sys.argv:
        print('Generating digest')
        digest = await gen_digest(s3_path)
        #print(digest)
    else:
        print('Using dummy digest')
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

    with open(f"{Path.home()}/tmp/res.html", "w") as text_file:
        text_file.write(digest)

    if 'mail' in sys.argv:
        print('Mailing digest')
        mail_digest(digest)
    else:
        print('Skipping mailing')

    if 'upload' in sys.argv:
        print('Uploading digest')
        upload_digest(digest, s3_path)
    else:
        print('Skipping uploading')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
