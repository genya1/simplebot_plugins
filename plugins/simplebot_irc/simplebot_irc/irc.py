# -*- coding: utf-8 -*-
from threading import Thread

import irc.bot
import irc.client

from .database import DBManager
from deltabot import DeltaBot

from deltachat import Message
from deltachat.capi import lib
from deltachat.cutil import as_dc_charpointer



class PuppetReactor(irc.client.SimpleIRCClient):
    def __init__(self, server, port, db: DBManager,
                 dbot: DeltaBot) -> None:
        super().__init__()
        self.server = server
        self.port = port
        self.dbot = dbot
        self.db = db
        self.puppets = dict()
        for chan, gid in db.get_channels():
            for c in dbot.get_chat(gid).get_contacts():
                if dbot.self_contact == c:
                    continue
                self._get_puppet(c.addr).channels.add(chan)

    def _get_puppet(self, addr: str) -> irc.client.ServerConnection:
        cnn = self.puppets.get(addr)
        if not cnn:
            cnn = self.reactor.server()
            cnn.channels = set()
            cnn.addr = addr
            nick = self.db.get_nick(addr) + '[dc]'
            cnn.connect(self.server, self.port, nick, ircname=nick)
            self.puppets[addr] = cnn
        return cnn

    def join_channel(self, addr: str, channel: str) -> None:
        cnn = self._get_puppet(addr)
        cnn.channels.add(channel)
        cnn.join(channel)

    def leave_channel(self, addr: str, channel: str) -> None:
        cnn = self.puppets[addr]
        if channel in cnn.channels:
            cnn.channels.discard(channel)
            cnn.part(channel)
            if not cnn.channels:
                del self.puppets[addr]
                cnn.close()

    def send_message(self, addr: str, target: str, text: str) -> None:
        self.puppets[addr].privmsg(target, text)

    def send_action(self, addr: str, target: str, text: str) -> None:
        self.puppets[addr].action(target, text)

    # EVENTS:

    def on_nicknameinuse(self, c, e) -> None:
        nick = self.db.get_nick(c.addr) + '_'
        self.db.set_nick(c.addr, nick)
        c.nick(nick + '[dc]')

    def on_welcome(self, c, e) -> None:
        for channel in c.channels:
            c.join(channel)


class IRCBot(irc.bot.SingleServerIRCBot):
    def __init__(self, server: str, port: int, nick: str, db: DBManager,
                 dbot: DeltaBot) -> None:
        super().__init__([(server, port)], nick, nick)
        self.dbot = dbot
        self.db = db
        self.preactor = PuppetReactor(server, port, db, dbot)

    def on_nicknameinuse(self, c, e) -> None:
        c.nick(c.get_nickname() + '_')

    def on_welcome(self, c, e) -> None:
        for chan, _ in self.db.get_channels():
            c.join(chan)
        Thread(target=self.preactor.start, daemon=True).start()

    def on_action(self, c, e) -> None:
        e.arguments.insert(0, '/me')
        self._irc2dc(e)

    def on_pubmsg(self, c, e) -> None:
        self._irc2dc(e)

    def _irc2dc(self, e) -> None:
        nick = e.source.split('!')[0]
        for cnn in self.preactor.puppets.values():
            if cnn.get_nickname() == nick:
                return
        sender = '{}[irc]'.format(nick)
        gid = self.db.get_chat(e.target)
        if not gid:
            self.dbot.logger.warning('Chat not found for room: %s', e.target)
            return
        msg = Message.new_empty(self.dbot.account, "text")
        lib.dc_msg_set_override_sender_name(
            msg._dc_msg, as_dc_charpointer(sender))
        msg.set_text(' '.join(e.arguments))
        self.dbot.get_chat(gid).send_msg(msg)

    def on_notopic(self, c, e) -> None:
        chan = self.channels[e.arguments[0]]
        chan.topic = '-'

    def on_currenttopic(self, c, e) -> None:
        chan = self.channels[e.arguments[0]]
        chan.topic = e.arguments[1]

    def join_channel(self, name: str, addr: str = None) -> None:
        self.connection.join(name)

    def leave_channel(self, channel: str) -> None:
        for addr in list(self.preactor.puppets.keys()):
            self.preactor.leave_channel(addr, channel)
        self.connection.part(channel)

    def get_topic(self, channel: str) -> str:
        self.connection.topic(channel)
        chan = self.channels[channel]
        if not hasattr(chan, 'topic'):
            chan.topic = '-'
        return chan.topic

    def get_members(self, channel: str) -> list:
        return list(self.channels[channel].users())

    def send_message(self, target: str, text: str) -> None:
        self.connection.privmsg(target, text)
