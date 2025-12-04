
import flask
import logging
import os
import pathlib
import signal
import sys
import werkzeug


from .sensors import Sensors


lcdc_app = flask.Flask(__name__)
logger = logging.getLogger(__name__)

@lcdc_app.route("/")
def index():
    return 'hello lcdc'


def run(__listen_addr: str, __listen_port: int, __debug: bool, __config_dir: pathlib.Path, __data_dir: pathlib.Path) -> int:

    logger.info("Starting server")
    lcdc_server = werkzeug.serving.make_server(host=__listen_addr, port=__listen_port, app=lcdc_app, passthrough_errors=not __debug)
    lcdc_sensors = Sensors()

    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} detected")
        lcdc_server.server_close()
        lcdc_sensors.clean()
        if __listen_port == 0:
            os.remove(__listen_addr[7:])
        logger.info("Stop server")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    logger.warning("Ctrl+C to stop server")
    lcdc_server.serve_forever()

    return 0
