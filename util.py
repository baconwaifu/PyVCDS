#!/usr/bin/python3

# PyVCDS Util script. used to load config files and do per-module logging,

import inspect
import json
import os
import threading


class Config:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.path = None
        if not path:
            self.backing = None
        else:
            if not os.path.exists(path):
                fd = open(path, "w")
                fd.write("{}")
                fd.close()
            self.open(path)

    def __getitem__(self, idx):
        if idx not in self.backing:
            self.backing[idx] = {}
        return self.backing[idx]

    def __setitem__(self, idx, item):
        with self.lock:  # ensures config writes are always consistent among threads
            self.backing[idx] = item
            self.flush()

    def open(self, fname):
        self.path = fname  # no need to flush, since we do that on every config update
        with self.lock:
            fd = open(fname, "r")
            self.backing = json.loads(fd.read())
            fd.close()

    def flush(self):  # NOTE: do *NOT* add a call to 'self.lock' due to deadlocking with `__setitem__`
        fd = open(self.path, "w")
        fd.write(json.dumps(self.backing, indent=4))
        fd.close()


home = os.environ["HOME"]
assert home, "No home directory? cannot run on windows."
cfgpath = home + "/.pyvcds/config.json"
if not os.path.exists(home + "/.pyvcds"):
    os.mkdir(home + "/.pyvcds")
config = Config(cfgpath)

levels = [
    "FATAL",  # 0
    "CRITICAL",  # 1
    "ERROR",  # 2
    "WARNING",  # 3
    "INFO",  # 4
    "DEBUG",  # 5
    "TRACE"  # 6
]


def log(level, *args):
    global config
    # get the calling stack frame, dereference it to the method, then get the module from it.
    modname = inspect.getmodule(inspect.stack()[1][0]).__name__
    if modname not in config["log"]:
        config["log"][modname] = 4  # initialize the module's log level config to "INFO"
        config.flush()  # need to manually flush here, since sub-module configs don't trigger our __setitem__ call.
    if level <= config["log"][modname]:
        if modname == "__main__":  # don't include __main__ for module tracing.
            print("[{}]".format(levels[level]), *args)
        else:
            print("[{}] [{}]".format(levels[level], modname), *args)
