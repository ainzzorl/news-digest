from handler import gen_digest
from handler import mail_digest

import sys


def lambda_handler(event, context):
    digest = gen_digest()
    mail_digest(digest)


if __name__ == "__main__":
    if 'gen' in sys.argv:
        print('Generating digest')
        digest = gen_digest()
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

    print(digest)

    if 'mail' in sys.argv:
        print('Mailing digest')
        mail_digest(digest)
    else:
        print('Skipping mailing')
