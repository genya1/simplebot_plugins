
import io
import mimetypes
import re

import bs4
import requests
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

version = '1.0.0'
ua = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101'
ua += ' Firefox/60.0'
HEADERS = {
    'user-agent': ua
}
dbot: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot
    dbot = bot
    getdefault('max_meme_size', 1024*200)

    bot.commands.register(name='/cuantarazon', func=cmd_cuantarazon)
    bot.commands.register(name='/cuantocabron', func=cmd_cuantocabron)


# ======== Commands ===============


def cmd_cuantarazon(command: IncomingCommand, replies: Replies) -> None:
    """Devuelve un meme al azar de https://m.cuantarazon.com
    """
    replies.add(**get_meme('https://m.cuantarazon.com/aleatorio/'))


def cmd_cuantocabron(command: IncomingCommand, replies: Replies) -> None:
    """Devuelve un meme al azar de https://m.cuantocabron.com
    """
    replies.add(**get_meme('https://m.cuantocabron.com/aleatorio'))


# ======== Utilities ===============

def get_meme(url: str) -> dict:
    def get_image(url: str) -> tuple:
        with requests.get(url, headers=HEADERS) as r:
            r.raise_for_status()
            soup = bs4.BeautifulSoup(r.text, 'html.parser')
        img = soup('div', class_='storyContent')[-1].img
        return (img['title'], img['src'])

    img = b''
    max_meme_size = int(getdefault('max_meme_size'))
    for i in range(10):
        img_desc, img_url = get_image(url)
        with requests.get(img_url, headers=HEADERS) as r:
            r.raise_for_status()
            if len(r.content) <= max_meme_size:
                img = r.content
                ext = get_ext(r) or '.jpg'
                break
            if not img or len(img) > len(r.content):
                img = r.content
                ext = get_ext(r) or '.jpg'

    text = '{}\n\n{}'.format(img_desc, img_url)
    return dict(text=text, filename='meme'+ext, bytefile=io.BytesIO(img))


def get_ext(r) -> str:
    d = r.headers.get('content-disposition')
    if d is not None and re.findall("filename=(.+)", d):
        fname = re.findall(
            "filename=(.+)", d)[0].strip('"')
    else:
        fname = r.url.split('/')[-1].split('?')[0].split('#')[0]
    if '.' in fname:
        ext = '.' + fname.rsplit('.', maxsplit=1)[-1]
    else:
        ctype = r.headers.get(
            'content-type', '').split(';')[0].strip().lower()
        if 'text/plain' == ctype:
            ext = '.txt'
        elif 'image/jpeg' == ctype:
            ext = '.jpg'
        else:
            ext = mimetypes.guess_extension(ctype)
    return ext


def getdefault(key: str, value=None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val
