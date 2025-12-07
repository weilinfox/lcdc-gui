import atexit
import importlib
import logging
import pathlib
import psutil
import time

from typing import Callable, Dict, List, Tuple


logger = logging.getLogger(__name__)


class _BAT:
    def __init__(self):
        # percent, secs_left, power_plugged
        self.precent = False
        self.bat: Tuple[float, int, bool] = (100.0, 0, True)

        self.update()

    def update(self) -> None:
        b = psutil.sensors_battery()
        if b is not None:
            self.precent = True
            self.bat = (b.percent, b.secsleft, b.power_plugged)

    def __str__(self) -> str:
        return (f"BAT Precent: {self.precent}\n"
                f"BAT Data: {self.bat}\n")


class _CPU:
    def __init__(self):
        self.cpu_count = psutil.cpu_count(logical=True)

        self.cpu_usage = 0.0
        self.cpu_usage_core: List[float] = [0.0 for _ in range(self.cpu_count)]
        self.cpu_freq = 0.0
        self.cpu_freq_core: List[float] = [0.0 for _ in range(self.cpu_count)]

        self.update()

    def update(self) -> None:
        self.cpu_usage = psutil.cpu_percent(percpu=False)
        self.cpu_usage_core = psutil.cpu_percent(percpu=True)
        self.cpu_freq = psutil.cpu_freq(percpu=False).current
        self.cpu_freq_core = [ i.current for i in psutil.cpu_freq(percpu=True) ]

    def __str__(self) -> str:
        return (f'CPU Cores: {self.cpu_count}\n'
                f'CPU Usage: {self.cpu_usage}\n'
                f'CPU Usage Core: {self.cpu_usage_core}\n'
                f'CPU Frequency: {self.cpu_freq}\n'
                f'CPU Frequency Core: {self.cpu_freq_core}\n')


def _c2f(_cels: float) -> float:
    return _cels * 1.8 + 57.6

class _GPU:
    def __init__(self):
        self.pynvml = None
        self.nvidia = False
        self.nvidia_dev_count: int = 0
        self.nvidia_dev_names: List[str] = []
        self.nvidia_dev_temps: List[float] = []
        self.nvidia_dev_usages: List[float] = []
        self.nvidia_dev_mem_total: List[int] = []
        self.nvidia_dev_mem_free: List[int] = []
        self.nvidia_dev_mem_used: List[int] = []
        self.amd = False

        try:
            self.pynvml = importlib.import_module("pynvml")

            self.pynvml.nvmlInit()
            if self.pynvml.nvmlDeviceGetCount() > 0:
                logger.info("Find Nvidia devices:")
                for i in range(self.pynvml.nvmlDeviceGetCount()):
                    logger.info(f"Card {i}: {self.pynvml.nvmlDeviceGetName(self.pynvml.nvmlDeviceGetHandleByIndex(i)).strip()}")
                self.nvidia = True
            else:
                logger.warning("No supported Nvidia devices found")
                self.pynvml.nvmlShutdown()
        except ImportError:
            logger.warning("Install pynvml for Nvidia GPU support")
            self.pynvml = None

        self.update()

    def update(self) -> None:
        if self.nvidia:
            temps: List[int] = []
            names: List[str] = []
            usages: List[int] = []
            mem_total: List[int] = []
            mem_free: List[int] = []
            mem_used: List[int] = []
            count = self.pynvml.nvmlDeviceGetCount()

            for d in range(count):
                h = self.pynvml.nvmlDeviceGetHandleByIndex(d)
                names.append(self.pynvml.nvmlDeviceGetName(h).strip())
                temps.append(self.pynvml.nvmlDeviceGetTemperature(h, self.pynvml.NVML_TEMPERATURE_GPU,))
                m = self.pynvml.nvmlDeviceGetMemoryInfo(h)
                usages.append(self.pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
                mem_total.append(m.total)
                mem_free.append(m.free)
                mem_used.append(m.used)

            self.nvidia_dev_count = count
            self.nvidia_dev_names = names
            self.nvidia_dev_temps = temps
            self.nvidia_dev_usages = usages
            self.nvidia_dev_mem_total = mem_total
            self.nvidia_dev_mem_free = mem_free
            self.nvidia_dev_mem_used = mem_used

    def clean(self) -> None:
        if self.nvidia:
            self.nvidia = False
            self.pynvml.nvmlShutdown()

    def __str__(self) -> str:
        return (f"Nvidia Count {self.nvidia_dev_count}\n"
                f"Nvidia Names: {self.nvidia_dev_names}\n"
                f"Nvidia Usages: {self.nvidia_dev_usages}\n"
                f"Nvidia Temperatures: {self.nvidia_dev_temps}\n"
                f"Nvidia Memory Total: {self.nvidia_dev_mem_total}\n"
                f"Nvidia Memory Free: {self.nvidia_dev_mem_free}\n"
                f"Nvidia Memory Used: {self.nvidia_dev_mem_used}\n")


class _FAN:
    def __init__(self):
        self.fans = {}
        self.update()

    def update(self) -> None:
        self.fans = psutil.sensors_fans()

    def __str__(self) -> str:
        return f"{self.fans}\n"


class _MEMORY:
    def __init__(self):
        self.free: int = 0
        self.usage: float = 0.0
        self.swap_free: int = 0
        self.swap_usage: float = 0.0

        self.update()

    def update(self) -> None:
        m = psutil.virtual_memory()
        self.free = m.free
        self.usage = m.percent

        m = psutil.swap_memory()
        self.swap_free = m.free
        self.swap_usage = m.percent

    def __str__(self) -> str:
        return (f"Memory Usage: {self.usage}\n"
                f"Memory Free: {self.free}\n"
                f"Memory Swap usage: {self.swap_usage}\n"
                f"Memory Swap free: {self.swap_free}\n")


class _DISK:
    def __init__(self):
        self.bytes_write: int = 0
        self.bytes_read: int = 0
        self.bytes_time = time.time()
        self.bytes_write_old = self.bytes_write
        self.bytes_read_old = self.bytes_read
        self.bytes_time_old = self.bytes_time

        self.rate_write = 0.0
        self.rate_read = 0.0

        self.update()

    def update(self) -> None:
        c = psutil.disk_io_counters()

        self.bytes_write_old = self.bytes_write
        self.bytes_read_old = self.bytes_read
        self.bytes_time_old = self.bytes_time

        self.bytes_write = c.write_bytes
        self.bytes_read = c.read_bytes
        self.bytes_time = time.time()

        self.rate_write = (self.bytes_write - self.bytes_write_old) / (self.bytes_time - self.bytes_time_old)
        self.rate_read = (self.bytes_read - self.bytes_read_old) / (self.bytes_time - self.bytes_time_old)

    def __str__(self) -> str:
        return (f'Disk Bytes Write: {self.bytes_write}\n'
                f'Disk Bytes Read: {self.bytes_read}\n'
                f'Disk Bytes Write Rate: {self.rate_write}\n'
                f'Disk Bytes Read Rate: {self.rate_read}\n')


class _NET:
    def __init__(self):
        self.bytes_sent: int = 0
        self.bytes_recv: int = 0
        self.bytes_time = time.time()
        self.bytes_sent_old = self.bytes_sent
        self.bytes_recv_old = self.bytes_recv
        self.bytes_time_old = self.bytes_time

        self.rate_sent = 0.0
        self.rate_recv = 0.0

        self.update()

    def update(self) -> None:
        c = psutil.net_io_counters()

        self.bytes_sent_old = self.bytes_sent
        self.bytes_recv_old = self.bytes_recv
        self.bytes_time_old = self.bytes_time

        self.bytes_sent = c.bytes_sent
        self.bytes_recv = c.bytes_recv
        self.bytes_time = time.time()

        self.rate_sent = (self.bytes_sent - self.bytes_sent_old) / (self.bytes_time - self.bytes_time_old)
        self.rate_recv = (self.bytes_recv - self.bytes_recv_old) / (self.bytes_time - self.bytes_time_old)

    def __str__(self) -> str:
        return (f'Network Bytes Sent: {self.bytes_sent}\n'
                f'Network Bytes Received: {self.bytes_recv}\n'
                f'Network Bytes Sent Rate: {self.rate_sent}\n'
                f'Network Bytes Received Rate: {self.rate_recv}\n')


class _TEMP:
    def __init__(self, fahrenheit: bool = False):
        # (name, label, current)
        self.disk_count: int = 0
        self.disk_names: List[str] = []
        self.disk_paths: List[List[pathlib.Path]] = []
        self.disk_temps: List[List[Tuple[str, float]]] = []
        self.cpu_count: int = 0
        self.cpu_names: List[str] = []
        self.cpu_paths: List[List[pathlib.Path]] = []
        self.cpu_temps: List[Tuple[str, float]] = []
        self.misc_count: int = 0
        self.misc_names: List[str] = []
        self.misc_paths: List[List[pathlib.Path]] = []
        self.misc_temps: List[Tuple[str, float]] = []

        self.detect()
        self.update()

    def update(self) -> None:
        """
        read from sensors
        :return:
        """

        temp_list: List[List[Tuple[str, float]]] = []
        detect_flag = False

        def _sensor_read(_p: pathlib.Path) -> Tuple[str, float]:
            si = float(p.read_bytes().decode(encoding="ascii").strip()) / 1000.0
            fi = p.parent.absolute() / (p.name[:-5] + "label")
            sn = ""
            if fi.is_file():
                sn = fi.read_bytes().decode(encoding="ascii").strip()

            return sn, si

        # disk temperature sensors
        for pl in self.disk_paths:
            temps: List[Tuple[str, float]] = []
            for p in pl:
                if not p.exists():
                    logger.debug(f"Disk temperature sensor {p} disappeared, set redetect flag")
                    detect_flag = True
                    continue
                temps.append(_sensor_read(p))

            if len(temps) > 0:
                temp_list.append(temps)

        self.disk_temps = temp_list

        # cpu temperature sensors
        temp_list = []
        for pl in self.cpu_paths:
            temps: List[Tuple[str, float]] = []
            for p in pl:
                if not p.exists():
                    logger.debug(f"CPU temperature sensor {p} disappeared, set redetect flag")
                    detect_flag = True
                    continue
                temps.append(_sensor_read(p))

            if len(temps) > 0:
                temp_list.append(temps)

        self.cpu_temps = temp_list

        # misc temperature sensors
        temp_list = []
        for pl in self.misc_paths:
            temps: List[Tuple[str, float]] = []
            for p in pl:
                if not p.exists():
                    logger.debug(f"Misc temperature sensor {p} disappeared, set redetect flag")
                    detect_flag = True
                    continue
                temps.append(_sensor_read(p))

            if len(temps) > 0:
                temp_list.append(temps)

        self.misc_temps = temp_list

        if detect_flag:
            logger.debug(f"Temperature sensor redetect")
            self.detect()

    def detect(self) -> None:
        """
        detect all sensor paths
        :return:
        """

        temp_count: int = 0
        dev_names: List[str] = []
        path_list: List[List[pathlib.Path]] = []

        # disk temperature sensors
        sys_base = pathlib.Path("/sys/block")
        if not sys_base.exists():
            return
        logger.debug(f"Entering /sys/block")
        for d in sys_base.iterdir():
            for s in d.glob("device/hwmon*"):
                paths: List[pathlib.Path] = []
                for t in s.glob("temp*_input"):
                    if not t.is_file():
                        continue
                    logger.debug(f"Find disk sensor {t}")
                    paths.append(t)

                if len(paths) > 0:
                    logger.debug(f"Record disk sensors above")
                    temp_count += 1
                    dev_names.append(d.name)
                    path_list.append(paths)

        self.disk_count = temp_count
        self.disk_names = dev_names
        self.disk_paths = path_list

        # hardware temperature sensors
        temp_count = 0
        dev_names = []
        path_list = []
        cpu_count: int = 0
        cpu_names: List[str] = []
        cpu_list: List[List[pathlib.Path]] = []
        sys_base = pathlib.Path("/sys/class/hwmon")
        logger.debug(f"Entering /sys/class/hwmon")
        if not sys_base.exists():
            return
        for h in sys_base.glob("hwmon*/name"):
            hn = h.read_bytes().decode(encoding="ascii").strip()
            paths: List[pathlib.Path] = []
            for t in h.parent.glob("temp*_input"):
                if not t.is_file():
                    continue
                logger.debug(f"Find sensor {t}")
                paths.append(t)
            if len(paths) > 0:
                if hn in ["k10temp", "coretemp"]:
                    # there could be multiple cpu
                    logger.debug(f"Record cpu sensors above")
                    cpu_count += 1
                    cpu_names.append(hn)
                    cpu_list.append(paths)
                elif hn in ["nvme"]:
                    # skip already detected disks
                    logger.debug(f"Skip disk sensors above")
                else:
                    logger.debug(f"Record misc sensors above")
                    temp_count += 1
                    dev_names.append(hn)
                    path_list.append(paths)

        self.cpu_count = cpu_count
        self.cpu_names = cpu_names
        self.cpu_paths = cpu_list
        self.misc_count = temp_count
        self.misc_names = dev_names
        self.misc_paths = path_list

    def __str__(self) -> str:
        return (f"CPU Count {self.cpu_count}\n"
                f"CPU Names: {self.cpu_names}\n"
                f"CPU Temp: {self.cpu_temps}\n"
                f"Disk Count: {self.disk_count}\n"
                f"Disk Names: {self.disk_names}\n"
                f"Disk Temp: {self.disk_temps}\n"
                f"Misc Count: {self.misc_count}\n"
                f"Misc Names: {self.misc_names}\n"
                f"Misc Temp: {self.misc_temps}\n")


class _SYSTEM:
    def __init__(self):
        self.boot_time = psutil.boot_time()
        self.cpu_count = psutil.cpu_count(logical=True)

        self.load_average: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.iowait_percent: float = 0.0

        self.update()

    def update(self) -> None:
        self.load_average = psutil.getloadavg()
        self.iowait_percent = psutil.cpu_times(percpu=False).iowait / self.cpu_count / 100.0

    def __str__(self) -> str:
        return (f"Boot Time: {self.boot_time}\n"
                f'Load Average: {self.load_average}\n'
                f'IOWAIT: {self.iowait_percent}\n')


class Sensors:
    def __init__(self):
        self._cpu = _CPU()
        self._gpu = _GPU()
        self._net = _NET()
        self._temp = _TEMP()
        self._disk = _DISK()
        self._mem = _MEMORY()
        self._system = _SYSTEM()

        self._data_dict = {}

        self._old_update = time.monotonic()
        self.format_value = {}
        self.format_def: Dict[str, Callable] = {}
        self.format_desc = {}

        # init format_desc and format_def
        # self._update()
        self.format("No such key", True, True)

    def _update(self):
        update = time.monotonic()
        if update - self._old_update > 0.25:
            self._old_update = update
            self._cpu.update()
            self._gpu.update()
            self._net.update()
            self._temp.update()
            self._disk.update()
            self._mem.update()
            self._system.update()

            self.format_value = {}

    def format(self, key: str, unit: bool, cels: bool) -> Tuple[str, str]:
        self._update()

        if key not in self.format_desc.keys():
            # CPUs
            def _cpu_format():
                if self._cpu.cpu_count == 0:
                    return

                _max_usage = 0.0
                _max_freq = 0.0
                for i, v in enumerate(self._cpu.cpu_freq_core):
                    _max_freq = max(_max_freq, v)
                for i, v in enumerate(self._cpu.cpu_usage_core):
                    _max_usage = max(_max_usage, v)

                self.format_value.update({
                    "CpuFreq": f"{self._cpu.cpu_freq / 1000:4.2f}" + "GHz" if unit else "",
                    "CpuUsage": f"{self._cpu.cpu_usage:4.1f}" + "%" if unit else "",
                    "CpuFreqMax": f"{_max_freq / 1000:4.2f}" + "GHz" if unit else "",
                    "CpuUsageMax": f"{_max_usage:4.1f}" + "%" if unit else "",
                })
                self.format_value.update(
                    {f"CpuFreq{i:03d}": f"{v:3.1f}" + "MHz" if unit else "" for i, v in enumerate(self._cpu.cpu_freq_core)})
                self.format_value.update(
                    {f"CpuUsage{i:03d}": f"{v:4.1f}" + "%" if unit else "" for i, v in enumerate(self._cpu.cpu_usage_core)})

            self.format_def.update({
                "CpuFreq": _cpu_format,
                "CpuUsage": _cpu_format,
                "CpuFreqMax": _cpu_format,
                "CpuUsageMax": _cpu_format,
            })
            self.format_def.update({f"CpuFreq{i:03d}": _cpu_format for i in range(self._cpu.cpu_count)})
            self.format_def.update({f"CpuUsage{i:03d}": _cpu_format for i in range(self._cpu.cpu_count)})

            self.format_desc = {
                "CpuFreq": "CPU Frequency in GHz",
                "CpuUsage": "CPU Usage",
                "CpuFreqMax": "CPU Core Frequency Max in GHz",
                "CpuUsageMax": "CPU Core Usage Max",
            }
            self.format_desc.update({f"CpuFreq{i:03d}": f"CPU Frequency of Core {i} in MHz" for i in range(self._cpu.cpu_count)})
            self.format_desc.update({f"CpuUsage{i:03d}": f"CPU Usage of Core {i}" for i in range(self._cpu.cpu_count)})

            # GPUs
            if self._gpu.nvidia:
                def _gpu_nv_format():
                    self.format_value.update({f"GpuUsage{i:03d}": f"{v:4.1f}" + "%" if unit else "" for i, v in enumerate(self._gpu.nvidia_dev_usages)})
                    self.format_value.update({f"GpuMemoryUsage{i:03d}": f"{v * 100.0 / self._gpu.nvidia_dev_mem_total[i]:4.1f}" + "%" if unit else "" for i, v in enumerate(self._gpu.nvidia_dev_mem_used)})
                    self.format_value.update({f"GpuMemoryFree{i:03d}": f"{v / 1073741824.0:5.2f}" + "GB" if unit else "" for i, v in enumerate(self._gpu.nvidia_dev_mem_free)})
                    if cels:
                        self.format_value.update({f"GpuTemp{i:03d}": f"{v:4.1f}" + "℃" if unit else "" for i, v in enumerate(self._gpu.nvidia_dev_temps)})
                    else:
                        self.format_value.update({f"GpuTemp{i:03d}": f"{_c2f(v):5.1f}" + "℉" if unit else "" for i, v in enumerate(self._gpu.nvidia_dev_temps)})

                self.format_def.update({f"GpuUsage{i:03d}": _gpu_nv_format for i in range(self._gpu.nvidia_dev_count)})
                self.format_def.update({f"GpuMemoryUsage{i:03d}": _gpu_nv_format for i in range(self._gpu.nvidia_dev_count)})
                self.format_def.update({f"GpuMemoryFree{i:03d}": _gpu_nv_format for i in range(self._gpu.nvidia_dev_count)})
                self.format_def.update({f"GpuTemp{i:03d}": _gpu_nv_format for i in range(self._gpu.nvidia_dev_count)})

                self.format_desc.update({f"GpuUsage{i:03d}": f"GPU Usage of Card ({i})" for i in range(self._gpu.nvidia_dev_count)})
                self.format_desc.update(
                    {f"GpuMemoryUsage{i:03d}": f"GPU Memory Usage of Card {self._gpu.nvidia_dev_names[i]} ({i})" for i in
                     range(self._gpu.nvidia_dev_count)})
                self.format_desc.update(
                    {f"GpuMemoryFree{i:03d}": f"GPU Memory Free of Card {self._gpu.nvidia_dev_names[i]} ({i}) in GB" for i in
                     range(self._gpu.nvidia_dev_count)})
                self.format_desc.update(
                    {f"GpuTemp{i:03d}": f"GPU Temperature of Card {self._gpu.nvidia_dev_names[i]} ({i})" for i in
                     range(self._gpu.nvidia_dev_count)})

            # Memory
            def _memory_format():
                self.format_value.update({"MemoryDdrUsage": f"{self._mem.usage:4.1f}" + "%" if unit else "",
                                          "MemoryDdrFree": f"{self._mem.free / 1073741824.0:5.2f}" + "GB" if unit else "",
                                          "MemorySwapUsage": f"{self._mem.swap_usage:4.1f}" + "%" if unit else "",
                                          "MemorySwapFree": f"{self._mem.swap_free / 1073741824.0:5.2f}" + "GB" if unit else "",
                                          })

            self.format_def.update({"MemoryDdrUsage": _memory_format,
                                    "MemoryDdrFree": _memory_format,
                                    "MemorySwapUsage": _memory_format,
                                    "MemorySwapFree": _memory_format,
                                    })

            self.format_desc.update({"MemoryDdrUsage": "Memory Usage",
                                     "MemoryDdrFree": "Memory Free in GB",
                                     "MemorySwapUsage": "Swap Usage",
                                     "MemorySwapFree": "Swap Free in GB",
                                     })

            # Disk
            def _disk_format():
                self.format_value.update({
                    "DiskWrite": f"{self._disk.bytes_write / 1073741824.0 if self._disk.bytes_write > 1048502599.68 else self._disk.bytes_write / 1048576.0:5.1f}" +
                                 ("GB" if self._disk.bytes_write > 1048502599.68 else "MB" if unit else ""),
                    "DiskRead": f"{self._disk.bytes_read / 1073741824.0 if self._disk.bytes_read > 1048502599.68 else self._disk.bytes_read / 1048576.0:5.1f}" +
                                ("GB" if self._disk.bytes_read > 1048502599.68 else "MB" if unit else ""),
                    "DiskWriteRate": f"{self._disk.rate_write / 1048576.0:5.1f}" + ("MB" if unit else ""),
                    "DiskReadRate": f"{self._disk.rate_read / 1048576.0:5.1f}" + ("MB" if unit else ""),
                    })

            self.format_def.update({"DiskWrite": _disk_format,
                                    "DiskRead": _disk_format,
                                    "DiskWriteRate": _disk_format,
                                    "DiskReadRate": _disk_format,
                                    })

            self.format_desc.update({"DiskWrite": "Disk Write Count in MB/GB",
                                     "DiskRead": "Disk Read Count in MB/GB",
                                     "DiskWriteRate": "Disk Write Rate in MB",
                                     "DiskReadRate": "Disk Read Rate in MB",
                                     })

            # Net
            def _net_format():
                self.format_value.update({
                    "NetworkSent": f"{self._net.bytes_sent / 1073741824.0 if self._net.bytes_sent > 1048502599.68 else self._net.bytes_sent / 1048576.0:5.1f}" +
                                   ("GB" if self._net.bytes_sent > 1048502599.68 else "MB" if unit else ""),
                    "NetworkRecv": f"{self._net.bytes_recv / 1073741824.0 if self._net.bytes_recv > 1048502599.68 else self._net.bytes_recv / 1048576.0:5.1f}" +
                                   ("GB" if self._net.bytes_recv > 1048502599.68 else "MB" if unit else ""),
                    "NetworkSentRate": f"{self._net.rate_sent / 1048576.0 if self._net.rate_sent > 1023928.32 else self._net.rate_sent / 1024.0:6.2f}" +
                                       ("MB" if self._net.rate_sent > 1023928.32 else "KB" if unit else ""),
                    "NetworkRecvRate": f"{self._net.rate_recv / 1048576.0 if self._net.rate_recv > 1023928.32 else self._net.rate_recv / 1024.0:6.2f}" +
                                       ("MB" if self._net.rate_recv > 1023928.32 else "KB" if unit else ""),
                    })

            self.format_def.update({"NetworkSent": _net_format,
                                    "NetworkRecv": _net_format,
                                    "NetworkSentRate": _net_format,
                                    "NetworkRecvRate": _net_format,
                                    })

            self.format_desc.update({"NetworkSent": "Network Sent Count in MB/GB",
                                     "NetworkRecv": "Network Received Count in MB/GB",
                                     "NetworkSentRate": "Network Sent Rate in KB/MB",
                                     "NetworkRecvRate": "Network Received Rate in KB/MB",
                                     })
            # temperature
            def _temp_format():
                if cels:
                    for _c in range(self._temp.cpu_count):
                        self.format_desc.update({f"CpuTemp{i:03d}": f"{v[1]:4.1f}" + "℃" if unit else "" for i, v in
                                                 enumerate(self._temp.cpu_temps[_c])})
                    for _c in range(self._temp.disk_count):
                        self.format_desc.update({f"DiskTemp{i:03d}": f"{v[1]:4.1f}" + "℃" if unit else "" for i, v in
                                                 enumerate(self._temp.disk_temps[_c])})
                    for _c in range(self._temp.misc_count):
                        self.format_desc.update({f"MiscTemp{i:03d}": f"{v[1]:4.1f}" + "℃" if unit else "" for i, v in
                                                 enumerate(self._temp.misc_temps[_c])})
                else:
                    for _c in range(self._temp.cpu_count):
                        self.format_desc.update({f"CpuTemp{i:03d}": f"{_c2f(v[1]):5.1f}" + "℉" if unit else "" for i, v in
                                                 enumerate(self._temp.cpu_temps[_c])})
                    for _c in range(self._temp.disk_count):
                        self.format_desc.update({f"DiskTemp{i:03d}": f"{_c2f(v[1]):5.1f}" + "℉" if unit else "" for i, v in
                                                 enumerate(self._temp.disk_temps[_c])})
                    for _c in range(self._temp.misc_count):
                        self.format_desc.update({f"MiscTemp{i:03d}": f"{_c2f(v[1]):5.1f}" + "℉" if unit else "" for i, v in
                                                 enumerate(self._temp.misc_temps[_c])})

            for c in range(self._temp.cpu_count):
                self.format_def.update({f"CpuTemp{i:03d}": _temp_format for i in range(len(self._temp.cpu_temps[c]))})
            for c in range(self._temp.disk_count):
                self.format_def.update({f"DiskTemp{i:03d}": _temp_format for i in range(len(self._temp.disk_temps[c]))})
            for c in range(self._temp.misc_count):
                self.format_def.update({f"MiscTemp{i:03d}": _temp_format for i in range(len(self._temp.misc_temps[c]))})

            for c in range(self._temp.cpu_count):
                self.format_desc.update(
                    {f"CpuTemp{i:03d}": f"CPU Temperature of {self._temp.cpu_names[c]} {v[0]}({i})" for i, v in
                     enumerate(self._temp.cpu_temps[c])})
            for c in range(self._temp.disk_count):
                self.format_desc.update(
                    {f"DiskTemp{i:03d}": f"Disk Temperature of {self._temp.disk_names[c]} {v[0]}({i})" for i, v in
                     enumerate(self._temp.disk_temps[c])})
            for c in range(self._temp.misc_count):
                self.format_desc.update(
                    {f"MiscTemp{i:03d}": f"Misc Temperature of {self._temp.misc_names[c]} {v[0]}({i})" for i, v in
                     enumerate(self._temp.misc_temps[c])})

            # system
            def _system_format():
                self.format_value.update({
                    "SystemLoad": f"{self._system.load_average[0]:5.2f}, {self._system.load_average[1]:5.2f}, {self._system.load_average[2]:5.2f}",
                    "SystemIoWait": f"{self._system.iowait_percent:5.2f}" + "%" if unit else ""
                    })
                _uptime = self._system.boot_time - time.time()
                if _uptime < 86400.0:
                    self.format_value.update({"SystemUptime": time.strftime("%_H:%M:%S", time.gmtime(_uptime)), })
                else:
                    self.format_value.update({"SystemUptime": f"{_uptime // 86400.0:.0f} days, " +
                                                              time.strftime("%_H:%M:%S", time.gmtime(_uptime)), })

            self.format_def.update({"SystemLoad": _system_format,
                                    "SystemUptime": _system_format,
                                    "SystemIoWait": _system_format,
                                    })

            self.format_desc.update({"SystemLoad": "System Average Load",
                                     "SystemUptime": "Uptime",
                                     "SystemIoWait": "CPU Time IO Wait Percentage",
                                     })

        if key not in self.format_value.keys():
            self.format_def.get(key, lambda: None)()

        return self.format_value.get(key, "None"), self.format_desc.get(key, "None")

    def clean(self):
        """
        clean on exit
        :return:
        """
        self._gpu.clean()


if __name__ == "__main__":
    cpu = _CPU()
    gpu = _GPU()
    atexit.register(gpu.clean)
    net = _NET()
    temp = _TEMP()
    fan = _FAN()
    bat = _BAT()
    disk = _DISK()
    mem = _MEMORY()
    system = _SYSTEM()
    time.sleep(1)
    net.update()
    disk.update()

    print(cpu)
    print(gpu)
    print(net)
    print(mem)
    print(disk)
    print(temp)
    print(system)
    print(bat)
    print(fan)
