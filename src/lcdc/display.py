
import hid
import logging
import time
import usb.core


logger = logging.getLogger(__name__)

def test_chizhu():
    dev = usb.core.find(idVendor=0x87ad, idProduct=0x70db)
    if dev is None:
        return
    if dev.bNumConfigurations == 0:
        logger.fatal("No configuration?")
        return
    elif dev.bNumConfigurations > 1:
        logger.warning("Multiple configurations?")

    logger.warning(str(dev))

    dev.set_configuration()
    cfg = dev.get_active_configuration()[(0, 0)]
    logger.warning("==========")

    ep_out = None  # write(host -> device)
    ep_in = None  # read(device -> host)

    for ep in cfg:
        if usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK:
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT:
                ep_out = ep
            elif usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                ep_in = ep

    logger.warning("OUT =" + hex(ep_out.bEndpointAddress) + " IN =" + hex(ep_in.bEndpointAddress))
    if ep_out is None or ep_in is None:
        return

    # URB_BULK out
    # 12 34 56 78 00 00 00 00 00 00 00 00 00 00 00 00
    # 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    # 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    # 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00
    ep_out.write(bytes.fromhex("""
    12 34 56 78 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00"""))

    # URB_BULK in
    # 12 34 56 78 53 53 43 52 4d 2d 56 31 00 00 00 00
    # 00 00 00 00 4c 1f aa 8f 04 00 00 00 2e 00 00 00
    # 01 00 00 00 01 00 00 00 00 00 00 00 01 00 00 00
    # 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00
    #                         little int32 type 0x01
    resp = bytes(ep_in.read(128, 100))
    logger.warning("==========")
    logger.warning("Command response:")
    logger.warning(resp.hex(" "))
    #
    # URB_BUIK out
    # 12 34 56 78 02 00 00 00 e0 01 00 00 e0 01 00 00
    # 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    # 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    # 00 00 00 00 00 00 00 00 02 00 00 00 1a ad 01 00
    #                         type 0x02   little int32 length
    # ff d8 ff e0 00 10 4a 46 49 46 00 01 01 01 00 60
    # JPEG
    # 00 60 00 00 ff db 00 43 00 02 01 01 01 01 01 02

    fb = None
    #with open("/home/hachi/Documents/Untitled.jpg", "rb") as f:
    with open("/home/hachi/Documents/Untitled2.jpg", "rb") as f:
    #with open("/home/hachi/Desktop/test.jpg", "rb") as f:
        fb = f.read()

    if fb is None:
        return

    logger.warning(str(len(fb)))
    logger.warning(str(len(fb).to_bytes(4, byteorder="little")))
    logger.warning(str(fb[:64]))

    # baseline DCT only
    # no optimized Huffman
    #data = (bytes.fromhex("""
    #12 34 56 78 02 00 00 00 e0 01 00 00 e0 01 00 00
    #00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    #00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    #00 00 00 00 00 00 00 00 02 00 00 00""")
    #        + len(fb).to_bytes(4, byteorder="little") + fb
    #        )
    data = (bytes.fromhex("12 34 56 78 02 00 00 00") +
    int(1920).to_bytes(4, byteorder="little") + int(480).to_bytes(4, byteorder="little") +
    bytes.fromhex("""00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 02 00 00 00""")
            + len(fb).to_bytes(4, byteorder="little") + fb )
    logger.warning(str(data[:64].hex(" ")))
    logger.warning(str(data[64:128].hex(" ")))

    for i in range(5000):
        time.sleep(0.01)
        ep_out.write(data)


def test_winbond():

    dev = usb.core.find(idVendor=0x0416, idProduct=0x5302)
    if dev is None:
        return
    if dev.bNumConfigurations == 0:
        logger.fatal("No configuration?")
        return
    elif dev.bNumConfigurations > 1:
        logger.warning("Multiple configurations?")

    logger.warning(str(dev))

    #dev.set_configuration()


    dev = hid.device()
    try:
        dev.open(0x0416, 0x5302)
    except OSError:
        return

    dev.set_nonblocking(False)


    logger.warning("==========")

    def reports_write(__i, __d: bytes) -> int:
        __t = 0
        for __c in range(len(__d) // 512 + 1):
            td = __d[512 * __c: 512 * __c + 512]
            td = td.ljust(512, b'\x00')
            #logger.warning(str(td))
            __tt = __i.write(b'\x00' + td)
            if __tt == -1:
                break
            __t += __tt

        return __t

    def reports_read(__i, __t: int) -> bytes:
        __r = []
        while True:
            __tt = __i.read(512, __t)
            if __tt is None or len(__tt) == 0:
                break
            __r.extend(__tt)
        return bytes(__r)

    # URB_INTERRUPT out
    # da db dc dd 00 00 00 00 00 00 00 00 01 00 00 00
    #             ↑ little int32 type 0x00
    reports_write(dev, bytes.fromhex("da db dc dd 00 00 00 00 00 00 00 00 01 00 00 00"))

    # URB_INTERRUPT in
    # da db dc dd 01 80 00 00 00 00 00 00 01 00 00 00
    #             ↑ little int32 type 0x01
    # 10 00 00 00 42 50 32 31 39 34 30 0d 01 6f 57 42
    # 47 02 20 78
    k = reports_read(dev, 100)
    logger.warning("==========")
    logger.warning("Command response:")
    logger.warning(str(k.hex(" ")))
    logger.warning("==========")

    #
    # URB_BUIK out
    # da db dc dd 02 00 00 00 00 05 e0 01 02 00 00 00
    #             ↑ type 0x02    ↑ magic
    # 10 b7 02 00 ff d8 ff e0 00 10 4a 46 49 46 00 01
    # uint32 size JPEG

    fb = None
    with open("/home/hachi/Documents/Untitled2.jpg", "rb") as f:
    #with open("/home/hachi/Documents/Untitled.jpg", "rb") as f: # it will auto resize image
        fb = f.read()

    if fb is None:
        exit(1)

    logger.warning(str(len(fb)))
    logger.warning(str(len(fb).to_bytes(4, byteorder="little")))

    # baseline DCT only
    # no optimized Huffman
    #data = (bytes.fromhex("da db dc dd 02 00 00 00 00 05 e0 01 02 00 00 00")
    data = (bytes.fromhex("da db dc dd 02 00 00 00 00 00 00 00 02 00 00 00")
            + len(fb).to_bytes(4, byteorder="little") + fb
            )
    logger.warning(str(data[:32].hex(" ")))

    for i in range(5000):
        time.sleep(0.01)
        reports_write(dev, data)

    dev.close()


if __name__ == "__main__":
    test_winbond()
