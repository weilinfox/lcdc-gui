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
        self.f_format = 0
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
                            4: "power",
                        },
                    },
                    1: {
                        "name": "GPU",
                        "w_param": {
                            1: "temperature",
                            2: "usage",
                            3: "frequency",
                            4: "power",
                        },
                    },
                    2: {
                        "name": "Memory",
                        "w_param": {
                            1: "temperature",
                            2: "usage",
                            3: "clock",
                            4: "free",
                        },
                    },
                    3: {
                        "name": "HDD",
                        "w_param": {
                            1: "temperature",
                            2: "activity",
                            3: "read",
                            4: "write",
                        },
                    },
                    4: {
                        "name": "Network",
                        "w_param": {
                            1: "up rate",
                            2: "down rate",
                            3: "total up",
                            4: "total down",
                        },
                    },
                    5: {
                        "name": "FAN",
                        "w_param": {
                            1: "pump",
                            2: "cpu fan",
                            3: "fan1",
                            4: "fan2",
                        },
                    },
                    10000: {
                        "name": "FAN",
                        "w_param": {
                            1: "FAN",
                        },
                    },
                },
            },
            1: {
                "name": "time",
                "w_mode": {
                    1: "hh:mm AM/PM",
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
                    0: "0 IDK", # 星期日
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
            3: {
                "name": "date",
                "w_mode": {
                    1: "yyyy/mm/dd",
                    2: "dd/mm/yyyy",
                    3: "mm/dd",
                    4: "dd/mm",
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
                f"Font: {self.f_name} size {self.f_size}\n"
                f"Format bold {self.f_format & 1}, italic {self.f_format & 2}, underline {self.f_format & 4}, strikeout {self.f_format & 8}\n"
                f"Color: {self.c_color} with alpha {self.c_alpha}\n"
                f"Offset: ({self.x_offset}, {self.y_offset})\n")


def dc_load_dd(dc) -> int:
    buffer = dc.read(1)
    if buffer == b'\x00':
        logger.info("theme without text/data widgets")
        return 0
    elif buffer == b'\x01':
        pass
    else:
        logger.info(f"unexpected data {buffer}\n")

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
        f_size, f_fmt = struct.unpack("<fB", b)
        rdc.f_size = f_size
        rdc.f_format = f_fmt

        b = dc.read(2)
        if b != b"\x03\x86":
            logger.warning(f"magic number {b} not 0386")
        rdc.magic = b

        b = dc.read(4)
        c_alpha, c_r, c_g, c_b = struct.unpack("<BBBB", b)
        rdc.c_alpha = c_alpha # unused in TRCC
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
        buffer = dc.read(1)
        if buffer == b'\xdd':
            return dc_load_dd(dc)
        else:
            logger.fatal(f"Unsupported file format: {buffer}")
            return 1


if __name__ == "__main__":
    exit(main(sys.argv[1]))
