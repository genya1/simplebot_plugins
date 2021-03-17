#!/usr/bin/env python3
import os


if __name__ == '__main__':
    pdir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'plugins')
    plugins = sorted(os.listdir(pdir))
    pcount = len(plugins)

    for i, p in enumerate(plugins):
        print('{}. {}'.format(i+1, p))
    print('{}. INSTALL ALL'.format(pcount+1))
    to_install = [int(p) - 1 for p in input('* Select plugins: ').split()]

    if to_install[0] != pcount:
        plugins = [plugins[i] for i in to_install]

    cmd = 'pip install -U "{}"'
    for p in plugins:
        os.system(cmd.format(os.path.join(pdir, p)))
