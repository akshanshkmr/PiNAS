"""Background system-metrics sampler shared by all dashboard clients."""

import datetime
import socket
import threading
import time
from collections import deque

import humanize
import psutil

SAMPLE_INTERVAL = 1
HISTORY_LEN = 300  # 5 minutes at 1s per sample


class TempSensors:
    CPU = "cpu_thermal"
    ADC = "rp1_adc"


def _get_temp(name: str) -> float:
    try:
        readings = psutil.sensors_temperatures().get(name, [])
        if readings and hasattr(readings[0], "current"):
            return round(readings[0].current, 1)
    except Exception:
        pass
    return 0.0


def _get_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "N/A"
    finally:
        s.close()


class Monitor:
    """Samples CPU/RAM/temp on a fixed cadence so history and per-process CPU
    deltas are meaningful regardless of how often clients poll."""

    def __init__(self):
        self._lock = threading.Lock()
        self.cpu_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        self.ram_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        self.temp_hist: deque[float] = deque(maxlen=HISTORY_LEN)
        self.processes: list[dict] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        if self._thread:
            return
        psutil.cpu_percent(interval=None)  # prime the counter
        self._thread = threading.Thread(target=self._loop, daemon=True, name="stats-sampler")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(SAMPLE_INTERVAL):
            self._sample()

    def _sample(self):
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        temp = _get_temp(TempSensors.CPU)
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            info = p.info
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu": round(info["cpu_percent"] or 0.0, 1),
                    "ram": round(info["memory_percent"] or 0.0, 1),
                }
            )
        procs.sort(key=lambda x: x["cpu"], reverse=True)
        with self._lock:
            self.cpu_hist.append(cpu)
            self.ram_hist.append(ram)
            self.temp_hist.append(temp)
            self.processes = procs[:10]

    def snapshot(self) -> dict:
        if not self.cpu_hist:
            self._sample()
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        uptime_seconds = time.time() - psutil.boot_time()
        with self._lock:
            cpu_hist = list(self.cpu_hist)
            ram_hist = list(self.ram_hist)
            temp_hist = list(self.temp_hist)
            processes = list(self.processes)
        return {
            "cpu": cpu_hist[-1] if cpu_hist else 0.0,
            "ram": ram_hist[-1] if ram_hist else vm.percent,
            "cpu_temp": temp_hist[-1] if temp_hist else 0.0,
            "adc_temp": _get_temp(TempSensors.ADC),
            "history": {"cpu": cpu_hist, "ram": ram_hist, "temp": temp_hist, "interval": SAMPLE_INTERVAL},
            "memory": {"total": vm.total, "used": vm.used, "percent": vm.percent},
            "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
            "net": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv,
            },
            "uptime": humanize.naturaldelta(datetime.timedelta(seconds=uptime_seconds)),
            "hostname": socket.gethostname(),
            "ip": _get_ip(),
            "processes": processes,
        }


monitor = Monitor()
