import pathlib
import psutil
import time

from typing import Dict, List, Tuple


class BAT:
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
        self.disk_count: int = 0
        self.disk_names: List[str] = []
        self.disk_temps: List[List[Tuple[str, float]]] = []
        self.cpu_count: int = 0
        self.cpu_names: List[str] = []
        self.cpu_temps: List[Tuple[str, float]] = []
        self.misc_count: int = 0
        self.misc_names: List[str] = []
        self.misc_temps: List[Tuple[str, float]] = []

        self.update()

    def update(self) -> None:

        temp_count: int = 0
        dev_names: List[str] = []
        temp_list: List[List[Tuple[str, float]]] = []

        # disk temperature sensors
        sys_base = pathlib.Path("/sys/block")
        if not sys_base.exists():
            return
        for d in sys_base.iterdir():
            for s in d.glob("device/hwmon*"):
                temps: List[Tuple[str, float]] = []
                for t in s.glob("temp*_label"):
                    if not t.is_file():
                        continue
                    sn = t.read_bytes().decode(encoding="ascii").strip()
                    fi = t.parent.absolute() / ( t.name[:-5] + "input" )
                    if not fi.is_file():
                        continue
                    si = float(fi.read_bytes().decode(encoding="ascii")) / 1000.0

                    temps.append( (sn, si) )

                if len(temps) > 0:
                    temp_count += 1
                    dev_names.append(d.name)
                    temp_list.append(temps)

        self.disk_count = temp_count
        self.disk_names = dev_names
        self.disk_temps = temp_list

        # hardware temperature sensors
        temp_count = 0
        dev_names = []
        temp_list = []
        cpu_count: int = 0
        cpu_names: List[str] = []
        cpu_list: List[List[Tuple[str, float]]] = []
        sys_base = pathlib.Path("/sys/class/hwmon")
        if not sys_base.exists():
            return
        for h in sys_base.glob("hwmon*/name"):
            hn = h.read_bytes().decode(encoding="ascii").strip()
            temps: List[Tuple[str, float]] = []
            for t in h.parent.glob("temp*_label"):
                tl = t.read_bytes().decode(encoding="ascii").strip()
                tf = t.parent.absolute() / ( t.name[:-5] + "input" )
                if not tf.is_file():
                    continue
                tt = float(tf.read_bytes().decode(encoding="ascii").strip()) / 1000.0
                temps.append( (tl, tt) )
            if len(temps) > 0:
                if hn in ["k10temp", "coretemp"]:
                    # there could be multiple cpu
                    cpu_count += 1
                    cpu_names.append(hn)
                    cpu_list.append(temps)
                elif hn in ["nvme"]:
                    pass
                else:
                    temp_count += 1
                    dev_names.append(hn)
                    temp_list.append(temps)

        self.cpu_count = cpu_count
        self.cpu_names = cpu_names
        self.cpu_temps = cpu_list
        self.misc_count = temp_count
        self.misc_names = dev_names
        self.misc_temps = temp_list

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
