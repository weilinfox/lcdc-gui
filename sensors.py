import pathlib
import psutil
import time

from typing import Dict, List, Tuple


class BAT:
    def __init__(self):
        # percent, secs_left, power_plugged
        self.bat: Tuple[float, int, bool] = (100.0, 0, True)

        self.update()

    def update(self) -> None:
        b = psutil.sensors_battery()
        if b is not None:
            self.bat = (b.percent, b.secsleft, b.power_plugged)

    def __str__(self) -> str:
        return f"{self.bat}\n"


class CPU:
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


class FAN:
    def __init__(self):
        self.fans = {}
        self.update()

    def update(self) -> None:
        self.fans = psutil.sensors_fans()

    def __str__(self) -> str:
        return f"{self.fans}\n"


class MEMORY:
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


class DISK:
    def __init__(self):
        self.bytes_write: int = 0
        self.bytes_read: int = 0
        self.bytes_time = time.time()
        self.bytes_write_old = self.bytes_write
        self.bytes_read_old = self.bytes_read
        self.bytes_time_old = self.bytes_time

        self.rate_write = 0.0
        self.rate_read = 0.0

        self.disk_count = 0
        self.disk_temp: List[List[Tuple[str, float]]] = []

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

        # disk temperature sensors
        disk_count = 0
        disk_temp = []
        sys_base = pathlib.Path("/sys/block")

        if not sys_base.exists():
            return
        for d in sys_base.iterdir():
            for s in d.glob("device/hwmon*"):
                sensors = []
                for t in s.glob("temp*_label"):
                    if not t.is_file():
                        continue
                    sn = t.read_bytes().decode(encoding="ascii").strip()
                    fi = t.parent.absolute() / ( t.name[:-5] + "input" )
                    if not fi.is_file():
                        continue
                    si = float(fi.read_bytes().decode(encoding="ascii")) / 1000.0

                    sensors.append( (sn, si) )

                if len(sensors) > 0:
                    disk_count += 1
                    disk_temp.append(sensors)

        self.disk_count = disk_count
        self.disk_temp = disk_temp

    def __str__(self) -> str:
        return (f'Disk Bytes Write: {self.bytes_write}\n'
                f'Disk Bytes Read: {self.bytes_read}\n'
                f'Disk Bytes Write Rate: {self.rate_write}\n'
                f'Disk Bytes Read Rate: {self.rate_read}\n'
                f'Disk Count: {self.disk_count}\n'
                f'Disk Temperatures: {self.disk_temp}\n')


class NET:
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


class TEMP:
    def __init__(self, fahrenheit: bool = False):
        # (name, label, current)
        self.psutil_temp: Dict[str, List[Tuple[str, float]]] = {}
        self.fahrenheit = fahrenheit

        self.update()

    def update(self) -> None:
        sensors = {}

        for t in psutil.sensors_temperatures(fahrenheit=self.fahrenheit).items():
            sensors[t[0]] = [ (f"id {k}" if t[1][k].label == "" else t[1][k].label, t[1][k].current) for k in range(len(t[1])) ]

        self.psutil_temp = sensors

    def __str__(self) -> str:
        return f"{self.psutil_temp}\n"


if __name__ == "__main__":
    cpu = CPU()
    net = NET()
    temp = TEMP()
    fan = FAN()
    bat = BAT()
    disk = DISK()
    mem = MEMORY()
    time.sleep(1)
    net.update()
    disk.update()

    print(cpu)
    print(net)
    print(mem)
    print(disk)
    print(temp)
    print(bat)
    print(fan)
