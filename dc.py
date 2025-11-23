import logging
import struct
import sys

from typing import List, Tuple


logger = logging.getLogger(__name__)


class DC:
    def __init__(self, w_type: int, w_mode: int, x_offset: int, y_offset: int, w_device: int, w_param: int) -> None:
        self.w_type = w_type
        self.w_mode = w_mode
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.w_device = w_device
        self.w_param = w_param
        self.f_name = ""
        self.f_size = 0.0
        self.f_bold = False
        self.c_alpha = 0
        self.c_color = (0, 0, 0)
        self.w_text = ""
        self.magic = b''

    def __str__(self) -> str:

        type_desc = {
            0: {
                "name": "sensor",
                "w_mode": {
                    0: "without unit",
                    1: "with unit",
                },
                "w_device": {
                    0: {
                        "name": "CPU",
                        "w_param": {
                            1: "temperature",
                            2: "usage",
                            3: "frequency",
                        },
                    },
                    1: {
                        "name": "GPU",
                        "w_param": {
                            1: "temperature",
                            2: "usage",
                            3: "frequency",
                        },
                    },
                    10000: {
                        "name": "FAN",
                        "w_param": {
                            1: "RPMs",
                        },
                    },
                },
            },
            1: {
                "name": "time",
                "w_mode": {
                    2: "hh:mm",
                },
                "w_device": {
                    0: {
                        "name": "no device",
                        "w_param": {
                            0: "0 IDK",
                            1: "1 IDK",
                        },
                     },
                },
            },
            2: {
                "name": "weekday",
                "w_mode": {
                    0: "0 星期六",
                    1: "1 星期六",
                },
                "w_device": {
                    0: {
                        "name": "no device",
                        "w_param": {
                            0: "0 IDK",
                            1: "1 IDK",
                        },
                    },
                },
            },
            3: {
                "name": "date",
                "w_mode": {
                    1: "yyyy/mm/dd",
                    3: "mm/dd",
                },
                "w_device": {
                    0: {
                        "name": "no device",
                        "w_param": {
                            0: "0 IDK",
                            1: "1 IDK",
                        },
                    },
                },
            },
            4: {
                "name": "text",
                # we found these possible values
                # just ignore them
                "w_mode": {
                    0: "0 IDK",
                    1: "1 IDK",
                },
                "w_device": {
                    0: {
                        "name": "no device",
                        "w_param": {
                            0: "0 IDK",
                            1: "1 IDK",
                        },
                    },
                },
            },
        }

        return (f"Type: {type_desc[self.w_type]["name"]} mode {type_desc[self.w_type]["w_mode"][self.w_mode]}\n"
                f"Device: {type_desc[self.w_type]["w_device"][self.w_device]["name"]}\n"
                f"Device param: {type_desc[self.w_type]["w_device"][self.w_device]["w_param"][self.w_param]}\n"
                f"Text: {self.w_text}\n"
                f"Font: {self.f_name} size {self.f_size} bold {self.f_bold}\n"
                f"Color: {self.c_color} with alpha {self.c_alpha}\n"
                f"Offset: ({self.x_offset}, {self.y_offset})\n")


def dc_load_dd01(dc) -> int:
    # widgets count
    b = dc.read(4)
    wc = int.from_bytes(b, 'little')
    logger.info(f"will load {wc} widgets")

    # widgets read
    for i in range(wc):
        b = dc.read(24)
        w_type, w_mode, x_offset, y_offset, w_device, w_param = struct.unpack("<IIIIII", b)
        rdc = DC(w_type, w_mode, x_offset, y_offset, w_device, w_param)

        b = dc.read(1)
        if b[0] > 0:
            b = dc.read(b[0])
            rdc.f_name = b.decode("utf-8", errors="ignore")

        b = dc.read(5)
        f_size, f_bold = struct.unpack("<fB", b)
        rdc.f_size = f_size
        rdc.f_bold = f_bold > 0

        b = dc.read(2)
        if b != b"\x03\x86":
            logger.warning(f"magic number {b} not 0386")
        rdc.magic = b

        b = dc.read(4)
        c_alpha, c_r, c_g, c_b = struct.unpack("<BBBB", b)
        rdc.c_alpha = c_alpha
        rdc.c_color = (c_r, c_g, c_b)

        b = dc.read(1)
        if b[0] > 0:
            b = dc.read(b[0])
            rdc.w_text = b.decode("utf-8", errors="ignore")

        print(rdc)

    return 0


def main(dc_file) -> int:
    logger.info(f"reading {dc_file}")

    with open(dc_file, "rb") as dc:
        buffer = dc.read(2)
        if buffer == b'\xdd\x01':
            return dc_load_dd01(dc)
        else:
            logger.fatal(f"Unsupported file format: {buffer}")
            return 1


if __name__ == "__main__":
    exit(main(sys.argv[1]))
