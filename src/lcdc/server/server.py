import time

import flask
import logging
import os
import pathlib
import signal
import sys
import threading
import werkzeug

from .config import Config
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

    # main process
    lcdc_configs = Config(__config_dir, __data_dir)
    lcdc_canvas = lcdc_configs.setup_canvas(lcdc_displays, lcdc_sensors)

    lcdc_canvas_paints = []
    for c in lcdc_canvas:
        lcdc_canvas_paints.append(threading.Thread(target=lambda: c.paint(), daemon=True))

    # flask routes
    @lcdc_app.route("/lcdc/lcdc", methods=["GET"])
    def route_lcdc_lcdc():
        return flask.jsonify({
            "name": "LCDC",
            "version": "0.0.0",
        })

    @lcdc_app.route("/lcdc/displays", methods=["GET"])
    def route_lcdc_displays():
        ret = []
        for d in lcdc_displays:
            ret.append({"id_vendor": d.device()[0], "id_product": d.device()[1]})
        return flask.jsonify({"displays": ret})

    @lcdc_app.route("/lcdc/sensors", methods=["GET"])
    def route_lcdc_sensors():
        # {key: description}
        return flask.jsonify({"sensors": lcdc_sensors.format_desc})

    @lcdc_app.route("/lcdc/sensors/format_key", methods=["GET"])
    def route_lcdc_sensor_format_key():
        key = flask.request.args.get("key", "")
        unit = flask.request.args.get("unit", "1")
        cels = flask.request.args.get("cels", "1")
        # without unit: unit=0
        #   fahrenheit: cels=0
        ret = lcdc_sensors.format(key, unit != "0", cels != "0")
        return flask.jsonify({
            "request_key": key,
            "format_str": ret[0],
            "description": ret[1],
        })

    # SIGINT handler
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} detected")
        lcdc_server.server_close()
        for _c in lcdc_canvas:
            _c.stop()
        lcdc_sensors.clean()
        if __listen_port == 0:
            os.remove(__listen_addr[7:])
        logger.info("Stop server")

        # core dump without this delay
        time.sleep(0.1)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    logger.warning("Ctrl+C to stop server")
    for _t in lcdc_canvas_paints:
        _t.start()

    lcdc_server.serve_forever()

    # code will never reach here
    for _t in lcdc_canvas_paints:
        _t.join()

    return 0
