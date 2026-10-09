#!/usr/bin/env python3
"""
DRAM (Dynamic Random Access Memory) 测试脚本
提供内存占比、内存读取速率等测试功能
"""

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, Dict, Optional


PAGE_SIZE = 4096

# 全局变量，用于跟踪正在运行的压力测试
_occupy_blocks = []
_occupy_lock = threading.Lock()
_occupy_stop = False
_occupy_thread: Optional[threading.Thread] = None
_stress_process: Optional[subprocess.Popen] = None


def _run_command(cmd: list, timeout: int = 30) -> Dict[str, Any]:
    """执行 Linux 命令并返回结果"""
    try:
        ps = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return {
            "returncode": ps.returncode,
            "stdout": ps.stdout.strip(),
            "stderr": ps.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def _get_meminfo() -> Dict[str, int]:
    """读取 /proc/meminfo，返回值单位为 kB"""
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, value = line.split(":")
                info[key.strip()] = int(value.strip().split()[0])
    except Exception:
        pass
    return info


def _parse_size_to_bytes(size_str: str) -> int:
    """解析容量字符串(如 '1M', '50G')为字节数"""
    units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$', size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    value = float(match.group(1))
    suffix = match.group(2).upper()
    return int(value * units.get(suffix, 1))


def dram_info() -> Dict[str, Any]:
    """获取 DRAM 内存基本信息"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": "Memory info retrieved successfully"
    }

    try:
        meminfo = _get_meminfo()

        mem_total_kb = meminfo.get("MemTotal", 0)
        mem_free_kb = meminfo.get("MemFree", 0)
        mem_available_kb = meminfo.get("MemAvailable", mem_free_kb)
        mem_buffers_kb = meminfo.get("Buffers", 0)
        mem_cached_kb = meminfo.get("Cached", 0)
        mem_used_kb = mem_total_kb - mem_available_kb

        # Swap 信息
        swap_total_kb = meminfo.get("SwapTotal", 0)
        swap_free_kb = meminfo.get("SwapFree", 0)
        swap_used_kb = swap_total_kb - swap_free_kb

        result["details"] = {
            "total_MB": round(mem_total_kb / 1024, 2),
            "used_MB": round(mem_used_kb / 1024, 2),
            "free_MB": round(mem_free_kb / 1024, 2),
            "available_MB": round(mem_available_kb / 1024, 2),
            "buffers_MB": round(mem_buffers_kb / 1024, 2),
            "cached_MB": round(mem_cached_kb / 1024, 2),
            "usage_percent": round(mem_used_kb / mem_total_kb * 100, 2) if mem_total_kb > 0 else 0,
            "swap_total_MB": round(swap_total_kb / 1024, 2),
            "swap_used_MB": round(swap_used_kb / 1024, 2),
            "swap_free_MB": round(swap_free_kb / 1024, 2)
        }
        result["message"] = (
            f"Memory: {result['details']['total_MB']}MB total, "
            f"{result['details']['used_MB']}MB used, "
            f"{result['details']['usage_percent']}% usage"
        )

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error getting memory info: {str(e)}"

    return result


def dram_usage() -> Dict[str, Any]:
    """获取当前内存占比"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        meminfo = _get_meminfo()

        mem_total_kb = meminfo.get("MemTotal", 0)
        mem_available_kb = meminfo.get("MemAvailable",
                                       meminfo.get("MemFree", 0))
        mem_used_kb = mem_total_kb - mem_available_kb
        usage_percent = round(mem_used_kb / mem_total_kb * 100, 2) if mem_total_kb > 0 else 0

        result["details"] = {
            "total_MB": round(mem_total_kb / 1024, 2),
            "used_MB": round(mem_used_kb / 1024, 2),
            "available_MB": round(mem_available_kb / 1024, 2),
            "usage_percent": usage_percent
        }
        result["message"] = (
            f"Memory usage: {usage_percent}% "
            f"({round(mem_used_kb / 1024, 2)}MB / {round(mem_total_kb / 1024, 2)}MB)"
        )

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error getting memory usage: {str(e)}"

    return result


def _occupy_worker(target_bytes: int, block_size: int, duration: int):
    """内存占用工作线程"""
    global _occupy_blocks, _occupy_stop

    _occupy_stop = False
    num_blocks = max(1, target_bytes // block_size)
    block_mib = block_size // (1024 * 1024)

    blocks = []
    for i in range(num_blocks):
        if _occupy_stop:
            break
        try:
            buf = bytearray(block_size)
            # 触摸每个页面以强制物理内存分配
            for off in range(0, block_size, PAGE_SIZE):
                buf[off] = 0xFF
            blocks.append(buf)
        except MemoryError:
            break

    with _occupy_lock:
        _occupy_blocks = blocks

    occupied_mib = len(blocks) * block_size // (1024 * 1024)

    # 保持占用
    if duration > 0:
        end_time = time.time() + duration
        while time.time() < end_time and not _occupy_stop:
            time.sleep(1)
    else:
        while not _occupy_stop:
            time.sleep(1)

    # 释放内存
    with _occupy_lock:
        _occupy_blocks.clear()
        _occupy_blocks = []


def dram_occupy(percent: int = 75, duration: int = 60,
                block_size: str = "1M") -> Dict[str, Any]:
    """
    内存占比压力测试：分配内存使占比达到指定百分比

    参数:
        percent: 目标内存占比百分比（默认 75%）
        duration: 保持时间（秒），0 表示一直持续到手动停止
        block_size: 每次分配的块大小（默认 1M）
    """
    global _occupy_thread, _occupy_stop

    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        meminfo = _get_meminfo()
        mem_total_kb = meminfo.get("MemTotal", 0)
        mem_available_kb = meminfo.get("MemAvailable",
                                       meminfo.get("MemFree", 0))
        mem_total_bytes = mem_total_kb * 1024
        mem_available_bytes = mem_available_kb * 1024

        # 计算目标
        target_bytes = int(mem_total_bytes * percent / 100)
        already_used = mem_total_bytes - mem_available_bytes
        to_allocate = target_bytes - already_used

        block_size_bytes = _parse_size_to_bytes(block_size)

        total_mib = mem_total_kb // 1024
        avail_mib = mem_available_kb // 1024
        used_mib = (mem_total_kb - mem_available_kb) // 1024
        target_mib = target_bytes // (1024 * 1024)
        alloc_mib = to_allocate // (1024 * 1024)

        result["details"] = {
            "total_MB": total_mib,
            "currently_used_MB": used_mib,
            "available_MB": avail_mib,
            "target_percent": percent,
            "target_MB": target_mib,
            "to_allocate_MB": alloc_mib,
            "duration_seconds": duration
        }

        if to_allocate <= 0:
            current_pct = round(already_used / mem_total_bytes * 100, 2)
            result["message"] = (
                f"Memory already at {current_pct}%, "
                f"target is {percent}%. No additional allocation needed."
            )
            return result

        # 停止之前的占用测试
        dram_release()

        # 启动内存占用线程
        _occupy_stop = False
        _occupy_thread = threading.Thread(
            target=_occupy_worker,
            args=(to_allocate, block_size_bytes, duration),
            daemon=True
        )
        _occupy_thread.start()

        # 等待一小段时间确保内存分配开始
        time.sleep(2)

        # 获取分配后的内存状态
        meminfo_after = _get_meminfo()
        used_after = meminfo_after.get("MemTotal", 0) - meminfo_after.get(
            "MemAvailable", meminfo_after.get("MemFree", 0))
        pct_after = round(used_after / meminfo_after.get("MemTotal", 1) * 100, 2)

        result["details"]["current_usage_after_allocation"] = f"{pct_after}%"
        result["message"] = (
            f"Memory occupation started: target {percent}%, "
            f"allocate {alloc_mib}MB, hold for {duration}s"
        )

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error during memory occupy: {str(e)}"

    return result


def dram_release() -> Dict[str, Any]:
    """释放正在占用的内存"""
    global _occupy_stop, _occupy_thread, _occupy_blocks

    result = {
        "status": "ok",
        "exit_code": 0,
        "message": "No memory occupation running"
    }

    _occupy_stop = True

    with _occupy_lock:
        blocks_count = len(_occupy_blocks)
        _occupy_blocks.clear()
        _occupy_blocks = []

    if _occupy_thread and _occupy_thread.is_alive():
        _occupy_thread.join(timeout=10)
        _occupy_thread = None
        result["message"] = f"Memory released ({blocks_count} blocks freed)"

    return result


def dram_read_speed(block_size: str = "1M", total_size: str = "1G",
                    threads: int = 1, max_time: int = 10) -> Dict[str, Any]:
    """
    内存读取速率测试：使用 sysbench 测试内存读写速率

    参数:
        block_size: 内存块大小（默认 1M）
        total_size: 总传输数据量（默认 1G）
        threads: 工作线程数（默认 1）
        max_time: 最大测试时间（秒，默认 10）
    """
    global _stress_process

    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    # 先尝试使用 sysbench
    if shutil.which("sysbench"):
        result = _sysbench_memory_test("read", block_size, total_size, threads, max_time)
    else:
        # 回退到 dd 测试
        result = _dd_memory_read_test(block_size, total_size, max_time)

    return result


def _sysbench_memory_test(operation: str, block_size: str, total_size: str,
                          threads: int, max_time: int) -> Dict[str, Any]:
    """使用 sysbench 进行内存测试"""
    global _stress_process

    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        cmd = [
            "sysbench", "--test=memory",
            f"--memory-block-size={block_size}",
            f"--memory-total-size={total_size}",
            f"--memory-oper={operation}",
            f"--max-time={max_time}",
            f"--threads={threads}",
            "run"
        ]

        ps = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        with _stress_lock:
            _stress_process = ps

        stdout, stderr = ps.communicate()

        with _stress_lock:
            _stress_process = None

        output = stdout

        # 解析 sysbench 输出
        speed_match = re.search(r'([\d.]+)\s*MB\s*transferred\s*\(([\d.]+)\s*MB/sec\)', output)
        ops_match = re.search(r'([\d.]+)\s*ops/sec', output)
        latency_match = re.search(r'avg:\s*([\d.]+)ms', output)

        details = {
            "method": "sysbench",
            "operation": operation,
            "block_size": block_size,
            "total_size": total_size,
            "threads": threads,
            "max_time": max_time,
            "raw_output": output
        }

        if speed_match:
            details["transferred_MB"] = float(speed_match.group(1))
            details["speed_MB_per_sec"] = float(speed_match.group(2))

        if ops_match:
            details["ops_per_sec"] = float(ops_match.group(1))

        if latency_match:
            details["avg_latency_ms"] = float(latency_match.group(1))

        result["details"] = details
        result["message"] = (
            f"Memory {operation} speed: "
            f"{details.get('speed_MB_per_sec', 'N/A')} MB/s, "
            f"{details.get('ops_per_sec', 'N/A')} ops/s"
        )

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"sysbench test error: {str(e)}"

    return result


def _dd_memory_read_test(block_size: str = "1M", total_size: str = "1G",
                         max_time: int = 10) -> Dict[str, Any]:
    """回退方案：使用 dd 从 /dev/zero 读取来测试内存读取速度"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        # 计算 count
        bs_bytes = _parse_size_to_bytes(block_size)
        total_bytes = _parse_size_to_bytes(total_size)
        count = total_bytes // bs_bytes

        dd_cmd = [
            "dd", "if=/dev/zero", "of=/dev/null",
            f"bs={block_size}", f"count={count}"
        ]

        ps = subprocess.run(
            dd_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max_time + 30
        )

        output = ps.stderr
        speed_match = re.search(
            r'(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+\s*\S+/s)',
            output
        )

        if speed_match:
            result["details"] = {
                "method": "dd_fallback",
                "bytes_transferred": int(speed_match.group(1)),
                "duration_seconds": float(speed_match.group(2)),
                "speed": speed_match.group(3),
                "block_size": block_size,
                "count": count
            }
            result["message"] = f"Memory read speed (dd): {speed_match.group(3)}"
        else:
            result["details"] = {"raw_output": output, "method": "dd_fallback"}
            result["message"] = "dd test completed but could not parse speed"

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"dd memory test error: {str(e)}"

    return result


def dram_write_speed(block_size: str = "1M", total_size: str = "1G",
                     threads: int = 1, max_time: int = 10) -> Dict[str, Any]:
    """
    内存写入速率测试

    参数:
        block_size: 内存块大小（默认 1M）
        total_size: 总传输数据量（默认 1G）
        threads: 工作线程数（默认 1）
        max_time: 最大测试时间（秒，默认 10）
    """
    if shutil.which("sysbench"):
        return _sysbench_memory_test("write", block_size, total_size, threads, max_time)
    else:
        # 回退方案：使用 dd 写入 /dev/null
        result = {
            "status": "ok",
            "exit_code": 0,
            "details": {},
            "message": ""
        }
        try:
            bs_bytes = _parse_size_to_bytes(block_size)
            total_bytes = _parse_size_to_bytes(total_size)
            count = total_bytes // bs_bytes

            dd_cmd = [
                "dd", "if=/dev/urandom", "of=/dev/null",
                f"bs={block_size}", f"count={count}"
            ]
            ps = subprocess.run(
                dd_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max_time + 30
            )
            output = ps.stderr
            speed_match = re.search(
                r'(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+\s*\S+/s)',
                output
            )
            if speed_match:
                result["details"] = {
                    "method": "dd_fallback",
                    "bytes_transferred": int(speed_match.group(1)),
                    "duration_seconds": float(speed_match.group(2)),
                    "speed": speed_match.group(3),
                    "block_size": block_size,
                    "count": count
                }
                result["message"] = f"Memory write speed (dd): {speed_match.group(3)}"
            else:
                result["details"] = {"raw_output": output, "method": "dd_fallback"}
                result["message"] = "dd test completed but could not parse speed"
        except Exception as e:
            result["status"] = "error"
            result["exit_code"] = -1
            result["message"] = f"dd memory write test error: {str(e)}"
        return result


def dram_stop_stress() -> Dict[str, Any]:
    """停止所有正在运行的 DRAM 压力测试"""
    global _stress_process, _occupy_stop

    result = {
        "status": "ok",
        "exit_code": 0,
        "message": "No stress test running"
    }

    stopped_any = False

    # 停止内存占用
    _occupy_stop = True
    with _occupy_lock:
        if _occupy_blocks:
            _occupy_blocks.clear()
            stopped_any = True

    # 停止 sysbench/dd 进程
    with _stress_lock:
        if _stress_process is not None:
            try:
                _stress_process.terminate()
                _stress_process.wait(timeout=10)
                stopped_any = True
            except Exception:
                try:
                    _stress_process.kill()
                    stopped_any = True
                except Exception:
                    pass
            finally:
                _stress_process = None

    if stopped_any:
        result["message"] = "All DRAM stress tests stopped"

    return result
