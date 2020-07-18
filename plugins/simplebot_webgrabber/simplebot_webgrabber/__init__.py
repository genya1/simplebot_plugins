# -*- coding: utf-8 -*-
from urllib.parse import quote_plus, unquote_plus, quote
import tempfile
import re
import mimetypes
import zipfile
import zlib

from deltachat import Message
from deltabot.hookspec import deltabot_hookimpl
from readability import Document
from html2text import html2text
import bs4
import requests
# typing
from deltabot import DeltaBot
from deltabot.commands import IncomingCommand
# ======


version = '1.0.0'
zlib.Z_DEFAULT_COMPRESSION = 9
ua = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101'
ua += ' Firefox/60.0'
HEADERS = {'user-agent': ua}
dbot: DeltaBot


# ======== Hooks ===============

@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global dbot
    dbot = bot

    getdefault('max_size', 1024*1024*5)

    dbot.commands.register('/ddg', cmd_ddg)
    dbot.commands.register('/wt', cmd_wt)
    dbot.commands.register('/w', cmd_w)
    dbot.commands.register('/wttr', cmd_wttr)
    dbot.commands.register('/web', cmd_web)
    dbot.commands.register('/read', cmd_read)
    dbot.commands.register('/img', cmd_img)
    dbot.commands.register('/img1', cmd_img1)
    dbot.commands.register('/img5', cmd_img5)


# ======== Commands ===============

def cmd_ddg(cmd: IncomingCommand) -> tuple:
    """Search in DuckDuckGo.
    """
    mode = get_mode(cmd.message.get_sender_contact().addr)
    page = 'lite' if mode == 'htmlzip' else 'html'
    url = "https://duckduckgo.com/{}?q={}".format(
        page, quote_plus(cmd.payload))
    return download_file(url, mode)


def cmd_wt(cmd: IncomingCommand) -> tuple:
    """Search in Wiktionary.
    """
    sender = cmd.message.get_sender_contact().addr
    lang = get_locale(sender)
    url = "https://{}.m.wiktionary.org/wiki/?search={}".format(
        lang, quote_plus(cmd.payload))
    return download_file(url, get_mode(sender))


def cmd_w(cmd: IncomingCommand) -> tuple:
    """Search in Wikipedia.
    """
    sender = cmd.message.get_sender_contact().addr
    lang = get_locale(sender)
    url = "https://{}.m.wikipedia.org/wiki/?search={}".format(
        lang, quote_plus(cmd.payload))
    return download_file(url, get_mode(sender))


def cmd_wttr(cmd: IncomingCommand) -> tuple:
    """Search weather info from wttr.in
    """
    lang = get_locale(cmd.message.get_sender_contact().addr)
    url = 'https://wttr.in/{}_Fnp_lang={}.png'.format(
        quote(cmd.payload), lang)
    return (None, download_file(url)[-1])


def cmd_web(cmd: IncomingCommand) -> tuple:
    """Download a webpage or file.
    """
    mode = get_mode(cmd.message.get_sender_contact().addr)
    return download_file(cmd.payload, mode)


def cmd_read(cmd: IncomingCommand) -> tuple:
    """Download a webpage and try to improve its readability.
    """
    mode = get_mode(cmd.message.get_sender_contact().addr)
    return download_file(cmd.payload, mode, True)


def cmd_img(cmd: IncomingCommand) -> str:
    """Search for images, returns image links.
    """
    text = '\n\n'.join(get_images(cmd.payload))
    if text:
        return '{}:\n\n{}'.format(cmd.payload, text)
    return 'No results for: {}'.format(cmd.payload)


def cmd_img1(cmd: IncomingCommand) -> None:
    """Get an image based on the given text.
    """
    _cmd_img(cmd, 1)


def cmd_img5(cmd: IncomingCommand) -> None:
    """Search for images, returns 5 results.
    """
    _cmd_img(cmd, 5)


def _cmd_img(cmd: IncomingCommand, img_count: int = None) -> None:
    chat = cmd.message.chat
    imgs = get_images(cmd.payload)
    if not imgs:
        chat.send_text('No results for: {}'.format(cmd.payload))
        return
    for img_url in imgs[:img_count]:
        with requests.get(img_url, headers=HEADERS) as r:
            r.raise_for_status()
            msg = Message.new_empty(cmd.bot.account, 'file')
            msg.set_file(save_file(r.content, get_ext(r) or '.jpg'))
            chat.send_msg(msg)


# ======== Utilities ===============

def getdefault(key: str, value=None) -> str:
    val = dbot.get(key, scope=__name__)
    if val is None and value is not None:
        dbot.set(key, value, scope=__name__)
        val = value
    return val


def get_locale(addr: str) -> str:
    return dbot.get('locale', scope=addr) or dbot.get('locale') or 'en'


def get_mode(addr: str) -> str:
    return dbot.get('mode', scope=addr) or dbot.get('mode') or 'htmlzip'


def html2read(html) -> str:
    return Document(html).summary()


def get_images(query: str) -> list:
    url = 'https://www.dogpile.com/search/images?q={}'.format(
        quote_plus(query))
    with requests.get(url, headers=HEADERS) as r:
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, 'html.parser')
    soup = soup.find('div', class_='mainline-results')
    if not soup:
        return []
    return [img['src'] for img in soup('img')]


def process_html(r) -> str:
    html, url = r.text, r.url
    soup = bs4.BeautifulSoup(html, 'html5lib')
    [t.extract() for t in soup(
        ['script', 'iframe', 'noscript', 'link', 'meta'])]
    soup.head.append(soup.new_tag('meta', charset='utf-8'))
    [comment.extract() for comment in soup.find_all(
        text=lambda text: isinstance(text, bs4.Comment))]
    for b in soup(['button', 'input']):
        if b.has_attr('type') and b['type'] == 'hidden':
            b.extract()
        b.attrs['disabled'] = None
    for i in soup(['i', 'em', 'strong']):
        if not i.get_text().strip():
            i.extract()
    for f in soup('form'):
        del f['action'], f['method']
    for t in soup(['img']):
        src = t.get('src')
        if not src:
            t.extract()
        elif not src.startswith('data:'):
            t.name = 'a'
            t['href'] = src
            alt = t.get('alt')
            if not alt:
                alt = 'IMAGE'
            t.string = '[{}]'.format(alt)
            del t['src'], t['alt']

            parent = t.find_parent('a')
            if parent:
                t.extract()
                parent.insert_before(t)
                contents = [e for e in parent.contents if not isinstance(
                    e, str) or e.strip()]
                if not contents:
                    parent.string = '(LINK)'
    styles = [str(s) for s in soup.find_all('style')]
    for t in soup(lambda t: t.has_attr('class') or t.has_attr('id')):
        classes = []
        for c in t.get('class', []):
            for s in styles:
                if '.'+c in s:
                    classes.append(c)
                    break
        del t['class']
        if classes:
            t['class'] = ' '.join(classes)
        if t.get('id') is not None:
            for s in styles:
                if '#'+t['id'] in s:
                    break
            else:
                del t['id']
    if url.startswith('https://www.startpage.com'):
        for a in soup('a', href=True):
            u = a['href'].split(
                'startpage.com/cgi-bin/serveimage?url=')
            if len(u) == 2:
                a['href'] = unquote_plus(u[1])

    index = url.find('/', 8)
    if index == -1:
        root = url
    else:
        root = url[:index]
        url = url.rsplit('/', 1)[0]
    for a in soup('a', href=True):
        if not a['href'].startswith('mailto:'):
            a['href'] = re.sub(
                r'^(//.*)', r'{}:\1'.format(root.split(':', 1)[0]), a['href'])
            a['href'] = re.sub(
                r'^(/.*)', r'{}\1'.format(root), a['href'])
            if not re.match(r'^https?://', a['href']):
                a['href'] = '{}/{}'.format(url, a['href'])
            a['href'] = 'mailto:{}?body=/web%20{}'.format(
                dbot.self_contact.addr, quote_plus(a['href']))
    return str(soup)


def process_file(r) -> tuple:
    max_size = int(getdefault('max_size'))
    data = b''
    size = 0
    for chunk in r.iter_content(chunk_size=10240):
        data += chunk
        size += len(chunk)
        if size > max_size:
            msg = 'Only files smaller than {} Bytes are allowed'
            raise ValueError(msg.format(max_size))

    return (data, get_ext(r))


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


def save_file(data, ext: str) -> str:
    fd, path = tempfile.mkstemp(prefix='web-', suffix=ext)
    if isinstance(data, str):
        mode = 'w'
    else:
        mode = 'wb'
    with open(fd, mode) as f:
        f.write(data)
    return path


def save_htmlzip(html) -> str:
    fd, path = tempfile.mkstemp(prefix='web-', suffix='.html.zip')
    with open(fd, 'wb') as f:
        with zipfile.ZipFile(f, 'w', compression=zipfile.ZIP_DEFLATED) as fzip:
            fzip.writestr('index.html', html)
    return path


def download_file(url: str, mode: str = 'htmlzip',
                  readability: bool = False) -> tuple:
    if '://' not in url:
        url = 'http://'+url
    with requests.get(url, headers=HEADERS, stream=True) as r:
        r.raise_for_status()
        r.encoding = 'utf-8'
        dbot.logger.debug(
            'Content type: {}'.format(r.headers['content-type']))
        if 'text/html' in r.headers['content-type']:
            if mode == 'text':
                html = html2read(r.text) if readability else r.text
                return (html2text(html), None)
            html = process_html(r)
            if readability:
                html = html2read(html)
            if mode == 'md':
                return (r.url, save_file(html2text(html), '.md'))
            return (r.url, save_htmlzip(html))
        return (r.url, save_file(*process_file(r)))