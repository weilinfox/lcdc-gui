
import av
import logging
import pyaudio
import queue
import time
import threading

from typing import List, Union

from ..display.usb_display import Display
from ..theme.theme import Theme


logger = logging.getLogger(__name__)


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


class Canvas:
    def __init__(self, _display: Display, _theme: Theme):
        self._display = _display
        self._theme = _theme

        self.stop_env = threading.Event()

    def set_theme(self, _theme: Theme):
        self._theme = _theme

    def paint(self):
        """
        run in a new thread
        :return:
        """

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
            container_t = av.open(self._theme.background)
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
                logger.warning(
                    f"Audio stream {audio_format}, {audio_sample_rate} Hz, {audio_channel} CH, {audio_bit_rate} bps")
            else:
                player_clock = WallClock()

        audio_q: queue.Queue[Union[av.AudioFrame, None]] = queue.Queue(maxsize=512)
        video_q: queue.Queue[Union[av.VideoFrame, None]] = queue.Queue(maxsize=512)


        def demux_thread():
            buf_audio: List[av.AudioFrame] = []
            buf_video: List[av.VideoFrame] = []
            buf_audio_index = 0
            buf_video_index = 0
            buf_use = True
            buf_ready = False

            logger.warning("Demux started")

            while not self.stop_env.is_set():

                if not buf_ready:
                    try:
                        container = av.open(self._theme.background)
                    except Exception as e:
                        logger.error(e)
                        self.stop_env.set()
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
                        if self.stop_env.is_set():
                            break

                        if a is not None and packet.stream.index == a.index:
                            # first audio track
                            for af in packet.decode():
                                if self.stop_env.is_set():
                                    break
                                audio_q.put(af)
                                if buf_use:
                                    buf_audio.append(af)

                        elif v is not None and packet.stream.index == v.index:
                            # first video track
                            for vf in packet.decode():
                                if self.stop_env.is_set():
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

                while not self.stop_env.is_set():
                    try:
                        frame = audio_q.get(timeout=0.1)
                    except queue.Empty:
                        logger.warning("Audio queue is empty")
                    else:
                        if frame is None:
                            break

                        # to int16 packed
                        for f in resampler.resample(frame):
                            if self.stop_env.is_set():
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

            while not self.stop_env.is_set():
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

                    while not self.stop_env.is_set():
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

                            self._display.print(frame)

                            logger.warning(
                                f"[VIDEO] t={frame_time:7.3f}s  "
                                f"size={frame.width}x{frame.height}  "
                                f"frames={frames_accept + frames_dropped}  "
                                f"frames_dropped={frames_dropped}  "
                                f"frames_accept={frames_accept}  "
                                f"rate={(frames_accept + frames_dropped - 1) / max(frame_time, 0.1)}  "
                                f"timestamp_base={timestamp_base} timestamp_max={timestamp_max} "
                                f"timestamp_old={timestamp_old} timestamp_loop={timestamp_loop}"
                            )
                        break

            video_q.shutdown()
            logger.warning("Video output stopped")

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

    def stop(self):
        self.stop_env.set()
