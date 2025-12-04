#!/usr/bin/env python3

import argparse
import fcntl
import logging
import os
import pathlib
import random
import re
import string


def main(_listen_addr: str, _config_dir: str, _data_dir: str, _debug: bool) -> int:
    if _debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger(__name__)

    # socket or net
    listen_addr = "unix:///tmp/lcdc-" + "".join(random.choice(string.ascii_letters) for _ in range(16)) + ".sock"
    listen_port = 0
    if _listen_addr is not None:
        if not re.match(r"[\d]+.[\d]+.[\d]+.[\d]+:[\d]+", _listen_addr):
            logger.error(f"Invalid address format: {_listen_addr}")
            return -1
        listen_addr, str_port = re.match(r"([\d]+.[\d]+.[\d]+.[\d]+):([\d]+)", _listen_addr).groups()
        listen_port = int(str_port)
    logger.info(f"Server listen at {listen_addr}:{listen_port}")

    # config dir
    config_dir = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser().absolute() / "lcdc"
    if _config_dir is not None:
        config_dir = pathlib.Path(_config_dir).expanduser().absolute()
    if not config_dir.exists():
        config_dir.mkdir(parents=True)
    if not config_dir.is_dir():
        logger.error("Config directory path is not a directory")
        return -1
    if not os.access(config_dir, os.W_OK):
        logger.error("Config directory not writeable")
        return -1
    logger.debug(f"Config directory: {config_dir}")

    # data dir
    data_dir = pathlib.Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser().absolute() / "lcdc"
    if _data_dir is not None:
        data_dir = pathlib.Path(_data_dir).expanduser().absolute()
    if not data_dir.exists():
        data_dir.mkdir(parents=True)
    if not data_dir.is_dir():
        logger.error("Data directory path is not a directory")
        return -1
    if not os.access(data_dir, os.W_OK):
        logger.error("Data directory not writeable")
        return -1
    logger.debug(f"Data directory: {data_dir}")

    # lock file
    lock_file = "/tmp/lcdc@kosaka.lock"
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.debug(f"Lock file acquired: {lock_file}")
    except BlockingIOError:
        os.close(fd)
        logger.fatal(f"Lock file already held by another process: {lock_file}")
        return -1

    # main process
    logger.info("Starting LCDC")
    try:
        from lcdc.server.server import run
        ret = run(listen_addr, listen_port, _debug, config_dir, data_dir)
    except Exception as e:
        logger.exception(f"Exception in LCDC server: {e}")
        ret = -1
    finally:
        logger.info("Quitting LCDC")

        # release lock
        fcntl.flock(fd, fcntl.LOCK_UN)
        logger.debug(f"Lock file released: {lock_file}")
        os.close(fd)
        os.remove(lock_file)

    return ret

if __name__ == '__main__':

    parser = argparse.ArgumentParser(prog="lcdc", description="lcdc: the USB LCD Control Util")
    parser.add_argument("-l", "--listen", type=str, help="address listen for GUI")
    parser.add_argument("-c", "--config", type=str, help="configuration directory")
    parser.add_argument("-s", "--data", type=str, help="data storage directory")
    parser.add_argument("-d", "--debug", action="store_true", help="set debug log level mode")
    parser.set_defaults(func=lambda args: main(args.listen, args.config, args.data, args.debug))

    myfunc = parser.parse_args()
    exit(myfunc.func(myfunc))
