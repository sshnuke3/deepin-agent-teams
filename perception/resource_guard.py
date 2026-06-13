"""
资源占用控制器
监控系统资源使用，在资源紧张时暂停感知模块
"""
import logging
import os
import time
import threading
from typing import Dict, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ResourceThresholds:
    """资源阈值配置"""
    cpu_max_percent: float = 70.0      # CPU 使用率上限
    memory_max_percent: float = 80.0   # 内存使用率上限
    screenshot_min_interval: float = 5.0  # 截图最小间隔（秒）
    clipboard_poll_interval: float = 2.0  # 剪贴板轮询间隔（秒）
    ocr_cache_ttl: float = 10.0        # OCR 缓存有效期（秒）
    disk_io_max_kbps: float = 50000.0  # 磁盘IO上限（KB/s）


class ResourceGuard:
    """
    资源占用控制器

    功能：
    1. 实时监控 CPU/内存/磁盘IO
    2. 资源紧张时自动暂停感知模块
    3. 截图频率限制
    4. OCR 结果缓存（相同截图不重复识别）
    """

    def __init__(self, thresholds: ResourceThresholds = None):
        self.thresholds = thresholds or ResourceThresholds()
        self._paused = False
        self._pause_callbacks: list = []
        self._resume_callbacks: list = []

        # 截图频率控制
        self._last_screenshot_time: float = 0
        self._last_screenshot_hash: str = ""

        # OCR 缓存
        self._ocr_cache: Dict = {}  # {hash: (result, timestamp)}
        self._ocr_cache_lock = threading.Lock()

        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

    def start_monitoring(self, interval: float = 5.0):
        """启动资源监控"""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True,
        )
        self._monitor_thread.start()

    def stop_monitoring(self):
        """停止资源监控"""
        self._running = False

    def _monitor_loop(self, interval: float):
        """监控循环"""
        while self._running:
            stats = self.get_system_stats()

            cpu = stats.get("cpu_percent", 0)
            mem = stats.get("memory_percent", 0)

            if not self._paused and (cpu > self.thresholds.cpu_max_percent or
                                     mem > self.thresholds.memory_max_percent):
                self._pause()

            elif self._paused and (cpu < self.thresholds.cpu_max_percent * 0.8 and
                                   mem < self.thresholds.memory_max_percent * 0.8):
                self._resume()

            time.sleep(interval)

    def _pause(self):
        """暂停感知模块"""
        self._paused = True
        for cb in self._pause_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Resource guard pause callback failed: %s", e)

    def _resume(self):
        """恢复感知模块"""
        self._paused = False
        for cb in self._resume_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Resource guard resume callback failed: %s", e)

    def on_pause(self, callback: Callable):
        """注册暂停回调"""
        self._pause_callbacks.append(callback)

    def on_resume(self, callback: Callable):
        """注册恢复回调"""
        self._resume_callbacks.append(callback)

    @property
    def is_paused(self) -> bool:
        return self._paused

    # === 截图频率控制 ===

    def can_screenshot(self) -> bool:
        """检查是否可以截图（频率限制）"""
        now = time.time()
        if now - self._last_screenshot_time < self.thresholds.screenshot_min_interval:
            return False
        return True

    def record_screenshot(self, content_hash: str = ""):
        """记录一次截图"""
        self._last_screenshot_time = time.time()
        self._last_screenshot_hash = content_hash

    def is_screenshot_duplicate(self, content_hash: str) -> bool:
        """检查截图是否与上次相同（避免重复OCR）"""
        return content_hash == self._last_screenshot_hash and self._last_screenshot_hash != ""

    # === OCR 缓存 ===

    def get_cached_ocr(self, screenshot_hash: str) -> Optional[Dict]:
        """获取缓存的 OCR 结果"""
        with self._ocr_cache_lock:
            cached = self._ocr_cache.get(screenshot_hash)
            if cached:
                result, timestamp = cached
                if time.time() - timestamp < self.thresholds.ocr_cache_ttl:
                    return result
                else:
                    del self._ocr_cache[screenshot_hash]
        return None

    def cache_ocr_result(self, screenshot_hash: str, result: Dict):
        """缓存 OCR 结果"""
        with self._ocr_cache_lock:
            # 限制缓存大小
            if len(self._ocr_cache) > 20:
                # 删除最旧的
                oldest_key = min(self._ocr_cache,
                                 key=lambda k: self._ocr_cache[k][1])
                del self._ocr_cache[oldest_key]
            self._ocr_cache[screenshot_hash] = (result, time.time())

    # === 系统资源查询 ===

    def get_system_stats(self) -> Dict:
        """获取当前系统资源使用情况"""
        stats = {}

        try:
            # CPU
            with open("/proc/stat") as f:
                line = f.readline()
                parts = line.split()[1:]
                values = [int(x) for x in parts]
                idle = values[3]
                total = sum(values)
                # 简化：返回瞬时值
                stats["cpu_idle"] = idle
                stats["cpu_total"] = total

            # 内存
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = int(parts[1].strip().split()[0])
                        meminfo[key] = val

                total = meminfo.get("MemTotal", 1)
                available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
                stats["memory_total_mb"] = total // 1024
                stats["memory_available_mb"] = available // 1024
                stats["memory_percent"] = round((1 - available / total) * 100, 1)

            # CPU 百分比（简化计算）
            stats["cpu_percent"] = self._calc_cpu_percent()

        except Exception as e:
            logger.warning("get_system_stats failed: %s", e)
            stats["cpu_percent"] = 0
            stats["memory_percent"] = 0

        return stats

    def _calc_cpu_percent(self) -> float:
        """计算 CPU 使用率（两次采样差值）"""
        try:
            with open("/proc/stat") as f:
                line1 = f.readline()
            parts1 = [int(x) for x in line1.split()[1:]]
            time.sleep(0.1)
            with open("/proc/stat") as f:
                line2 = f.readline()
            parts2 = [int(x) for x in line2.split()[1:]]

            idle1, total1 = parts1[3], sum(parts1)
            idle2, total2 = parts2[3], sum(parts2)

            idle_delta = idle2 - idle1
            total_delta = total2 - total1

            if total_delta == 0:
                return 0.0
            return round((1 - idle_delta / total_delta) * 100, 1)
        except Exception as e:
            logger.warning("_calc_cpu_percent failed: %s", e)
            return 0.0

    def get_report(self) -> Dict:
        """获取资源使用报告"""
        stats = self.get_system_stats()
        return {
            **stats,
            "paused": self._paused,
            "screenshot_interval": self.thresholds.screenshot_min_interval,
            "clipboard_interval": self.thresholds.clipboard_poll_interval,
            "ocr_cache_size": len(self._ocr_cache),
        }


# 全局单例
_guard: Optional[ResourceGuard] = None


def get_guard(thresholds: ResourceThresholds = None) -> ResourceGuard:
    global _guard
    if _guard is None:
        _guard = ResourceGuard(thresholds)
    return _guard
