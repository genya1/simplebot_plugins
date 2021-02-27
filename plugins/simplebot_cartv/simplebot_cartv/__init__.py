# pylama:ignore=W0613

import requests
from simplebot import DeltaBot
from simplebot.bot import Replies
from simplebot.commands import IncomingCommand
from simplebot.hookspec import deltabot_hookimpl

__version__ = '1.0.0'
tv_emoji, cal_emoji, aster_emoji = '📺', '📆', '✳'
channels = {
    name: 'http://eprog2.tvcdigital.cu/programacion/' + code
    for name, code in zip(
            ('Cubavisión',
             'Tele Rebelde',
             'Educativo',
             'Educativo 2',
             'Multivisión',
             'Clave',
             'Caribe',
             'Habana',
             ),
            ('5c096ea5bad1b202541503cf',
             '596c6d34769cf31454a473aa',
             '596c6d4f769cf31454a473ab',
             '596c8107670d001588a8bfc1',
             '597eed8948124617b0d8b23a',
             '5a6a056c6c40dd21604965fd',
             '5c5357124929db17b7429949',
             '5c42407f4fa5d131ce00f864',
             ),
    )
}


@deltabot_hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    bot.commands.register(name="/cartv", func=cmd_cartv)
    bot.commands.register(name="/cartvcv", func=cmd_cv)
    bot.commands.register(name="/cartvtr", func=cmd_tr)
    bot.commands.register(name="/cartved", func=cmd_ed)
    bot.commands.register(name="/cartved2", func=cmd_ed2)
    bot.commands.register(name="/cartvmv", func=cmd_mv)
    bot.commands.register(name="/cartvcl", func=cmd_cl)
    bot.commands.register(name="/cartvca", func=cmd_ca)
    bot.commands.register(name="/cartvha", func=cmd_ha)


def cmd_cartv(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera de todos los canales de la TV cubana.
    """
    text = ''
    for chan in channels.keys():
        text += get_channel(chan) + '\n\n'
    replies.add(text=text)


def cmd_cv(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Cubavisión.
    """
    replies.add(text=get_channel('Cubavisión'))


def cmd_tr(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Tele Rebelde.
    """
    replies.add(text=get_channel('Tele Rebelde'))


def cmd_ed(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Educativo.
    """
    replies.add(text=get_channel('Educativo'))


def cmd_ed2(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Educativo 2.
    """
    replies.add(text=get_channel('Educativo 2'))


def cmd_mv(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Multivisión.
    """
    replies.add(text=get_channel('Multivisión'))


def cmd_cl(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Clave.
    """
    replies.add(text=get_channel('Clave'))


def cmd_ca(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Caribe.
    """
    replies.add(text=get_channel('Caribe'))


def cmd_ha(command: IncomingCommand, replies: Replies) -> None:
    """Muestra la cartelera del canal Habana.
    """
    replies.add(text=get_channel('Habana'))


# ======== Utilities ===============

def get_channel(chan) -> str:
    with requests.get(channels[chan]) as req:
        req.raise_for_status()
        programs = req.json()

    text = '{} {}\n'.format(tv_emoji, chan)
    date = None
    for prog in programs:
        if date != prog['fecha_inicial']:
            date = prog['fecha_inicial']
            text += '{} {}\n'.format(cal_emoji, date)
        time = prog['hora_inicio'][:-3]
        title = ' '.join(prog['titulo'].split())
        desc = ' '.join(prog['descripcion'].split())
        trans = prog['transmision'].strip()
        text += '{} {} {}\n'.format(
            aster_emoji, time, '/'.join(e for e in (title, desc, trans) if e))

    if not programs:
        text += 'Cartelera no disponible.'

    return text
