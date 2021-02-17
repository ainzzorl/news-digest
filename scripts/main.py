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
        digest = 'Dummy digest'

    print(digest)

    if 'mail' in sys.argv:
        print('Mailing digest')
        mail_digest(digest)
    else:
        print('Skipping mailing')
