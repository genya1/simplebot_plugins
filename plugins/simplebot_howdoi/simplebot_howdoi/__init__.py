import json

import simplebot
from howdoi.howdoi import howdoi
from simplebot.bot import Replies

__version__ = '1.0.0'


@simplebot.command(name='/howdoi')
def cmd_howdoi(payload: str, replies: Replies) -> None:
    """Instant coding answers. Example: /howdoi format date bash"""
    try:
        res = json.loads(howdoi('{} -j'.format(payload)))[0]
        replies.add(text='{}\n\n↗️ {}'.format(res['answer'], res['link']))
    except (Exception, SystemExit):
        replies.add(text='Something went wrong.')
