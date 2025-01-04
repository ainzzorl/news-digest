from handler import gen_digest
from handler import mail_digest

import sys
import asyncio

def lambda_handler(event, context):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(inner_lambda_handler(event, context))

async def inner_lambda_handler(event, context):
    digest = await gen_digest()
    mail_digest(digest)

async def main():
    if 'gen' in sys.argv:
        print('Generating digest')
        digest = await gen_digest()
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

    # with open("~/tmp/res.html", "w") as text_file:
    #     text_file.write(digest)

    if 'mail' in sys.argv:
        print('Mailing digest')
        mail_digest(digest)
    else:
        print('Skipping mailing')


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
