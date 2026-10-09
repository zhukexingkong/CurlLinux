#!/usr/bin/env python3
"""
UFS (Universal Flash Storage) 测试脚本
提供磁盘占比、磁盘读取速率等测试功能
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


# 全局变量，用于跟踪正在运行的压力测试进程
_stress_process: Optional[subprocess.Popen] = None
_stress_lock = threading.Lock()


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


def _parse_size_to_bytes(size_str: str) -> int:
    """解析容量字符串(如 '1G', '512M')为字节数"""
    units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$', size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    value = float(match.group(1))
    suffix = match.group(2).upper()
    return int(value * units.get(suffix, 1))


def ufs_info() -> Dict[str, Any]:
    """获取 UFS 磁盘基本信息（分区、总容量等）"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": "UFS info retrieved successfully"
    }

    try:
        # 使用 df 获取磁盘使用情况
        df_result = _run_command(["df", "-h"])
        if df_result["returncode"] == 0:
            lines = df_result["stdout"].splitlines()
            filesystems = []
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    filesystems.append({
                        "filesystem": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_percent": parts[4],
                        "mounted_on": parts[5]
                    })
            result["details"]["filesystems"] = filesystems

        # 使用 lsblk 获取块设备信息
        lsblk_result = _run_command(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT", "-J"])
        if lsblk_result["returncode"] == 0:
            try:
                result["details"]["block_devices"] = json.loads(lsblk_result["stdout"])
            except json.JSONDecodeError:
                result["details"]["block_devices_raw"] = lsblk_result["stdout"]

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error getting UFS info: {str(e)}"

    return result


def ufs_usage(path: str = "/") -> Dict[str, Any]:
    """获取指定路径的磁盘占比"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": "Disk usage retrieved successfully"
    }

    try:
        usage = shutil.disk_usage(path)
        result["details"] = {
            "path": path,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_GB": round(usage.total / (1024**3), 2),
            "used_GB": round(usage.used / (1024**3), 2),
            "free_GB": round(usage.free / (1024**3), 2),
            "usage_percent": round(usage.used / usage.total * 100, 2)
        }
    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error getting disk usage: {str(e)}"

    return result


def ufs_occupy(path: str = "/", percent: int = 75, duration: int = 60,
               block_size: str = "1M") -> Dict[str, Any]:
    """
    磁盘占比压力测试：创建临时文件占满磁盘到指定百分比

    参数:
        path: 目标路径（默认 "/"）
        percent: 目标磁盘占比百分比（默认 75%）
        duration: 保持时间（秒），0 表示一直持续到手动停止
        block_size: 写入块大小（默认 1M）
    """
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        usage = shutil.disk_usage(path)
        target_bytes = int(usage.total * percent / 100)
        already_used = usage.used
        to_allocate = target_bytes - already_used

        if to_allocate <= 0:
            result["message"] = (
                f"Disk already at {round(already_used / usage.total * 100, 2)}%, "
                f"target is {percent}%. No additional space needed."
            )
            result["details"] = {
                "current_usage_percent": round(already_used / usage.total * 100, 2),
                "target_percent": percent,
                "allocated_bytes": 0
            }
            return result

        # 计算需要写入的块数
        bs_bytes = _parse_size_to_bytes(block_size)
        num_blocks = max(1, to_allocate // bs_bytes)

        # 创建临时文件
        temp_file = os.path.join(path, f".tp_ufs_stress_{int(time.time())}")

        # 使用 dd 命令写入数据
        dd_cmd = [
            "dd", "if=/dev/urandom", f"of={temp_file}",
            f"bs={block_size}", f"count={num_blocks}",
            "status=progress"
        ]

        ps = subprocess.Popen(
            dd_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        with _stress_lock:
            global _stress_process
            _stress_process = ps

        _, stderr = ps.communicate()

        with _stress_lock:
            _stress_process = None

        allocated_bytes = num_blocks * bs_bytes

        if ps.returncode == 0:
            result["details"] = {
                "path": path,
                "target_percent": percent,
                "allocated_bytes": allocated_bytes,
                "allocated_MB": round(allocated_bytes / (1024**2), 2),
                "temp_file": temp_file,
                "duration_seconds": duration
            }
            result["message"] = (
                f"Allocated {round(allocated_bytes / (1024**2), 2)}MB "
                f"to reach {percent}% disk usage"
            )

            # 保持占用指定时间
            if duration > 0:
                time.sleep(duration)

            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
                result["details"]["cleaned"] = True
                result["message"] += " (cleaned up after hold time)"
        else:
            result["status"] = "error"
            result["exit_code"] = ps.returncode
            result["message"] = f"dd command failed: {stderr}"
            # 尝试清理
            if os.path.exists(temp_file):
                os.remove(temp_file)

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error during disk occupy: {str(e)}"

    return result


def ufs_read_speed(device: str = "/dev/sda", block_size: str = "1M",
                   count: int = 100) -> Dict[str, Any]:
    """
    磁盘读取速率测试：使用 dd 从设备读取数据测试速率

    参数:
        device: 块设备路径（默认 /dev/sda）
        block_size: 块大小（默认 1M）
        count: 读取块数（默认 100）
    """
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        # 方法1: 使用 dd 测试读取速度
        dd_cmd = [
            "dd", f"if={device}", "of=/dev/null",
            f"bs={block_size}", f"count={count}",
            "iflag=direct"
        ]

        ps = subprocess.run(
            dd_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120
        )

        # dd 的输出在 stderr
        output = ps.stderr
        # 解析速度信息，格式如: "104857600 bytes (105 MB, 100 MiB) copied, 0.523 s, 200 MB/s"
        speed_match = re.search(
            r'(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+\s*\S+/s)',
            output
        )

        if speed_match:
            result["details"] = {
                "device": device,
                "bytes_transferred": int(speed_match.group(1)),
                "duration_seconds": float(speed_match.group(2)),
                "speed": speed_match.group(3),
                "block_size": block_size,
                "count": count
            }
            result["message"] = f"Read speed: {speed_match.group(3)}"
        else:
            # 如果无法解析标准格式，尝试另一种方式
            result["details"] = {
                "device": device,
                "raw_output": output,
                "returncode": ps.returncode
            }
            result["message"] = "Read test completed but could not parse speed"

        # 方法2: 如果有 hdparm，也尝试获取缓存读取速度
        hdparm_result = _run_command(["hdparm", "-Tt", device], timeout=30)
        if hdparm_result["returncode"] == 0:
            result["details"]["hdparm_output"] = hdparm_result["stdout"]

    except FileNotFoundError:
        # dd 命令不可用，回退到简单的文件读写测试
        result = _fallback_read_speed_test(block_size, count)
    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error during read speed test: {str(e)}"

    return result


def _fallback_read_speed_test(block_size: str = "1M", count: int = 100) -> Dict[str, Any]:
    """回退方案：通过读取 /dev/urandom 来测试 I/O 性能"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    try:
        dd_cmd = [
            "dd", "if=/dev/urandom", "of=/dev/null",
            f"bs={block_size}", f"count={count}",
            "status=progress"
        ]

        ps = subprocess.run(
            dd_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120
        )

        output = ps.stderr
        speed_match = re.search(
            r'(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+\s*\S+/s)',
            output
        )

        if speed_match:
            result["details"] = {
                "method": "fallback_urandom",
                "bytes_transferred": int(speed_match.group(1)),
                "duration_seconds": float(speed_match.group(2)),
                "speed": speed_match.group(3),
                "block_size": block_size,
                "count": count
            }
            result["message"] = f"I/O speed (fallback): {speed_match.group(3)}"
        else:
            result["details"] = {"raw_output": output}
            result["message"] = "Fallback test completed but could not parse speed"

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Fallback read test error: {str(e)}"

    return result


def ufs_write_speed(path: str = "/", block_size: str = "1M",
                    count: int = 100) -> Dict[str, Any]:
    """
    磁盘写入速率测试：使用 dd 写入临时文件测试速率

    参数:
        path: 目标路径（默认 /）
        block_size: 块大小（默认 1M）
        count: 写入块数（默认 100）
    """
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": ""
    }

    temp_file = os.path.join(path, f".tp_write_test_{int(time.time())}")

    try:
        dd_cmd = [
            "dd", "if=/dev/urandom", f"of={temp_file}",
            f"bs={block_size}", f"count={count}",
            "oflag=direct", "status=progress"
        ]

        ps = subprocess.run(
            dd_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120
        )

        output = ps.stderr
        speed_match = re.search(
            r'(\d+)\s+bytes.*copied,\s*([\d.]+)\s*s,\s*([\d.]+\s*\S+/s)',
            output
        )

        if speed_match:
            result["details"] = {
                "path": path,
                "bytes_transferred": int(speed_match.group(1)),
                "duration_seconds": float(speed_match.group(2)),
                "speed": speed_match.group(3),
                "block_size": block_size,
                "count": count
            }
            result["message"] = f"Write speed: {speed_match.group(3)}"
        else:
            result["details"] = {"raw_output": output}
            result["message"] = "Write test completed but could not parse speed"

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error during write speed test: {str(e)}"
    finally:
        # 清理临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return result


def ufs_partitions() -> Dict[str, Any]:
    """获取 UFS 分区信息"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "details": {},
        "message": "Partition info retrieved successfully"
    }

    try:
        # 使用 lsblk 获取分区信息
        lsblk_result = _run_command(
            ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,PARTLABEL", "-J"]
        )
        if lsblk_result["returncode"] == 0:
            try:
                result["details"]["partitions"] = json.loads(lsblk_result["stdout"])
            except json.JSONDecodeError:
                result["details"]["partitions_raw"] = lsblk_result["stdout"]

        # 使用 df 获取文件系统使用情况
        df_result = _run_command(["df", "-hT"])
        if df_result["returncode"] == 0:
            lines = df_result["stdout"].splitlines()
            filesystems = []
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 7:
                    filesystems.append({
                        "filesystem": parts[0],
                        "type": parts[1],
                        "size": parts[2],
                        "used": parts[3],
                        "available": parts[4],
                        "use_percent": parts[5],
                        "mounted_on": parts[6]
                    })
            result["details"]["filesystems"] = filesystems

    except Exception as e:
        result["status"] = "error"
        result["exit_code"] = -1
        result["message"] = f"Error getting partitions: {str(e)}"

    return result


def ufs_stop_stress() -> Dict[str, Any]:
    """停止正在运行的 UFS 压力测试"""
    result = {
        "status": "ok",
        "exit_code": 0,
        "message": "No stress test running"
    }

    with _stress_lock:
        global _stress_process
        if _stress_process is not None:
            try:
                _stress_process.terminate()
                _stress_process.wait(timeout=10)
                result["message"] = "Stress test stopped successfully"
            except Exception as e:
                try:
                    _stress_process.kill()
                    result["message"] = "Stress test killed"
                except Exception:
                    result["status"] = "error"
                    result["message"] = f"Error stopping stress test: {str(e)}"
            finally:
                _stress_process = None

    # 清理可能残留的临时文件
    for f in os.listdir("/"):
        if f.startswith(".tp_ufs_stress_"):
            try:
                os.remove(os.path.join("/", f))
            except Exception:
                pass

    return result
