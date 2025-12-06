
import flask
import logging
import os
import pathlib
import signal
import sys
import werkzeug


from .sensors import Sensors
from ..display.usb_display import usb_detect


logger = logging.getLogger(__name__)


def run(__listen_addr: str, __listen_port: int, __debug: bool, __config_dir: pathlib.Path, __data_dir: pathlib.Path) -> int:

    logger.info(f"Detecting displays")
    lcdc_displays = usb_detect()
    if len(lcdc_displays) == 0:
        logger.fatal("No USB displays detected")
        return 1

    logger.info("Starting server")
    lcdc_app = flask.Flask(__name__)
    lcdc_server = werkzeug.serving.make_server(host=__listen_addr, port=__listen_port, app=lcdc_app, passthrough_errors=not __debug)
    lcdc_sensors = Sensors()

    @lcdc_app.route("/lcdc/lcdc", methods=["GET"])
    def route_lcdc_lcdc():
        return flask.jsonify({
            "name": "LCDC",
            "version": "0.0.0",
        })

    @lcdc_app.route("/lcdc/sensors", methods=["GET"])
    def route_lcdc_sensors():
        sensors = lcdc_sensors.format(True, True)
        return flask.jsonify({
            k: {
                "format_str": v,
                "desc": sensors[1][k],
            } for k, v in sensors[0].items()
        })

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
