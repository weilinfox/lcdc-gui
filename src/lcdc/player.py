
import av
import io
import logging
import pathlib
import pyaudio
import queue
import signal
import threading
import time

from typing import List, Union


logger = logging.getLogger(__name__)


def init_chizhu():
    import usb

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

    return ep_out


def test_chizhu(ep_out, width: int, height: int, data: bytes) -> None:


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
    width.to_bytes(4, byteorder="little") + height.to_bytes(4, byteorder="little") +
    bytes.fromhex("""00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    00 00 00 00 00 00 00 00 02 00 00 00""")
            + len(data).to_bytes(4, byteorder="little") + data )

    ep_out.write(data)


class Clock:
    def now(self) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


class AudioClock(Clock):
    def __init__(self, sample_rate: int):
        self._sr = sample_rate
        self._played_samples = 0
        self._latency_samples = 0
        self._lock = threading.Lock()

    def advance(self, n_samples: int):
        with self._lock:
            # stereo
            self._played_samples += n_samples // 2

    def set_latency(self, latency_sec: float):
        with self._lock:
            self._latency_samples = int(latency_sec * self._sr)

    def now(self) -> float:
        with self._lock:
            played = self._played_samples
            lat = self._latency_samples
        return max(0.0, (played - lat) / self._sr)

    def reset(self):
        pass



class WallClock(Clock):
    def __init__(self):
        self._t0 = time.monotonic()

    def reset(self):
        self._t0 = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self._t0


def play(path: pathlib.Path) -> int:

    player_clock = Clock()
    container_format = ""
    audio_flag = False
    audio_format = ""
    audio_layout = ""
    audio_sample_rate = 0
    audio_bit_rate = 0
    audio_channel = 0
    video_format = ""
    video_framerate = 0
    video_height = 0
    video_width = 0

    try:
        container_t = av.open(path)
    except Exception as e:
        logger.error(e)
        return 1
    else:
        container_format = container_t.format.name
        astream = next((s for s in container_t.streams if s.type == "audio"), None)
        vstream = next((s for s in container_t.streams if s.type == "video"), None)
        container_t.close()

        logger.warning(f"Container {container_format}")

        if vstream:
            logger.warning("Found video stream")
            video_format = vstream.format.name
            video_height = vstream.height
            video_width = vstream.width
            video_framerate = vstream.average_rate
            logger.warning(f"Video stream {video_format}, {video_width} x {video_height} {video_framerate} fps")
        else:
            logger.error("No video stream found")
            return 1

        if astream:
            logger.warning("Found audio stream")
            audio_flag = True
            audio_format = astream.format.name
            audio_layout = astream.layout.name
            audio_sample_rate = astream.rate
            audio_bit_rate = astream.bit_rate
            audio_channel = astream.channels
            player_clock = AudioClock(audio_sample_rate)
            logger.warning(f"Audio stream {audio_format}, {audio_sample_rate} Hz, {audio_channel} CH, {audio_bit_rate} bps")
        else:
            player_clock = WallClock()


    stop_evt = threading.Event()
    audio_q: queue.Queue[Union[av.AudioFrame, None]] = queue.Queue(maxsize=512)
    video_q: queue.Queue[Union[av.VideoFrame, None]] = queue.Queue(maxsize=512)

    ep_out = None

    def signal_handler(signal, frame):
        logger.warning(f"Signal {signal} detected")
        stop_evt.set()
        #audio_q.shutdown()
        #video_q.shutdown()


    def demux_thread():
        buf_audio: List[av.AudioFrame] = []
        buf_video: List[av.VideoFrame] = []
        buf_audio_index = 0
        buf_video_index = 0
        buf_use = True
        buf_ready = False

        logger.warning("Demux started")

        while not stop_evt.is_set():

            if not buf_ready:
                try:
                    container = av.open(path)
                except Exception as e:
                    logger.error(e)
                    stop_evt.set()
                    audio_q.put(None)
                    video_q.put(None)
                    break

                # only audio and video track
                a = next((s for s in container.streams if s.type == "audio"), None)
                v = next((s for s in container.streams if s.type == "video"), None)

                streams = []
                if a is not None:
                    streams.append(a)
                if v is not None:
                    streams.append(v)

                for packet in container.demux(streams):
                    if stop_evt.is_set():
                        break

                    if a is not None and packet.stream.index == a.index:
                        # first audio track
                        for af in packet.decode():
                            if stop_evt.is_set():
                                break
                            audio_q.put(af)
                            if buf_use:
                                buf_audio.append(af)

                    elif v is not None and packet.stream.index == v.index:
                        # first video track
                        for vf in packet.decode():
                            if stop_evt.is_set():
                                break

                            video_q.put(vf)
                            if buf_use:
                                buf_video.append(vf)

                    # too many frames
                    if buf_use and len(buf_video) > 1024:
                        buf_use = False
                        buf_video.clear()
                        buf_audio.clear()

                if buf_use:
                    logger.warning(f"buf_audio length {len(buf_audio)}, buf_video length {len(buf_video)}")
                    buf_ready = True

            else:
                # use buffer
                if audio_flag and not audio_q.full():
                    cap = audio_q.maxsize - audio_q.qsize()
                    for i in range(buf_audio_index, min(len(buf_audio), buf_audio_index + cap)):
                        audio_q.put(buf_audio[i])
                    buf_audio_index = 0 if buf_audio_index + cap >= len(buf_audio) else buf_audio_index + cap
                if not video_q.full():
                    cap = video_q.maxsize - video_q.qsize()
                    for i in range(buf_video_index, min(len(buf_video), buf_video_index + cap)):
                        video_q.put(buf_video[i])
                    buf_video_index = 0 if buf_video_index + cap >= len(buf_video) else buf_video_index + cap

        logger.warning("Demux stopped")

    def audio_thread():
        if not audio_flag:
            logger.warning("No audio output")
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=audio_sample_rate,
            output=True,
           # frames_per_buffer=1024,
           # stream_callback=None,
        )
        # convert to int16 interleaved(packed) stereo
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=audio_sample_rate)
        logger.warning("Audio output started")

        try:
            try:
                latency_sec = stream.get_output_latency()
                logger.warning(f"Audio output latency {latency_sec:.3f} ms")
            except Exception:
                latency_sec = 0.0

            player_clock.set_latency(latency_sec)

            while not stop_evt.is_set():
                try:
                    frame = audio_q.get(timeout=0.1)
                except queue.Empty:
                    logger.warning("Audio queue is empty")
                else:
                    if frame is None:
                        break

                    # to int16 packed
                    for f in resampler.resample(frame):
                        if stop_evt.is_set():
                            break

                        arr = f.to_ndarray()

                        stream.write(arr.tobytes())
                        player_clock.advance(arr.shape[1])
        finally:
            stream.close()
            pa.terminate()
            audio_q.shutdown()
            logger.warning("Audio output stopped")

    def video_thread():
        timestamp_loop = -1
        timestamp_old = 19260817.0
        timestamp_max = 0.0
        timestamp_base = 0
        frames_accept = 0
        frames_dropped = 0

        sleep_quantum = 0.002
        drop_threshold = - 0.8 / video_framerate

        logger.warning("Video output started")

        player_clock.reset()

        while not stop_evt.is_set():
            try:
                frame = video_q.get(timeout=0.1)
            except queue.Empty:
                logger.warning("Video queue is empty")
            else:
                if frame is None:
                    break

                if frame.time < timestamp_old:
                    timestamp_loop += 1
                    timestamp_old = frame.time
                    if timestamp_loop > 0:
                        timestamp_base = timestamp_max * timestamp_loop + timestamp_loop / video_framerate
                timestamp_max = max(timestamp_max, frame.time)
                timestamp_old = frame.time

                frame_time = frame.time
                if timestamp_loop > 0:
                    frame_time += timestamp_base
                # wrong frame time
                if frame_time == 0.0 and frames_accept + frames_dropped > 0:
                    frame_time = (frames_accept + frames_dropped) / video_framerate

                while not stop_evt.is_set():
                    delta = frame_time - player_clock.now()

                    if delta > sleep_quantum:
                        time.sleep(sleep_quantum)
                        continue
                    elif delta < drop_threshold:
                        frames_dropped += 1
                        logger.warning(f"Frame dropped {delta} "
                                       f"timestamp_base={timestamp_base} timestamp_max={timestamp_max} "
                                       f"timestamp_old={timestamp_old} timestamp_loop={timestamp_loop}"
                                       )
                    else:
                        # accept this frame
                        frames_accept += 1

                        if ep_out is not None:
                            jpeg_buf = io.BytesIO()
                            frame.to_image().save(jpeg_buf, format="JPEG", progressive=False,optimize=False,)
                            test_chizhu(ep_out, frame.width, frame.height, jpeg_buf.getvalue())
                        logger.warning(
                            f"[VIDEO] t={frame_time:7.3f}s  "
                            f"size={frame.width}x{frame.height}  "
                            f"frames={frames_accept + frames_dropped}  "
                            f"frames_dropped={frames_dropped}  "
                            f"frames_accept={frames_accept}  "
                            f"rate={(frames_accept + frames_dropped) / max(frame_time, 0.1)}  "
                            f"timestamp_base={timestamp_base} timestamp_max={timestamp_max} "
                            f"timestamp_old={timestamp_old} timestamp_loop={timestamp_loop}"
                        )
                    break

        video_q.shutdown()
        logger.warning("Video output stopped")

    signal.signal(signal.SIGINT, signal_handler)

    ep_out = init_chizhu()

    t_demux = threading.Thread(target=demux_thread, daemon=True)
    t_audio = threading.Thread(target=audio_thread, daemon=True)
    t_video = threading.Thread(target=video_thread, daemon=True)

    t_demux.start()
    t_audio.start()
    t_video.start()

    t_demux.join()
    t_audio.join()
    t_video.join()

    return 0


if __name__ == "__main__":
    play(pathlib.Path("/home/hachi/Videos/This is what happens when you reply to spam email-James Veitch.mp4"))
    #play(pathlib.Path("/home/hachi/Pictures/450x450.png"))
    #play(pathlib.Path("/home/hachi/Downloads/Cache_-7dbcd720aefeb687..jpg"))
    #play(pathlib.Path("/home/hachi/Pictures/0.gif"))
    #play(pathlib.Path("/home/hachi/Videos/a016.mp4"))
