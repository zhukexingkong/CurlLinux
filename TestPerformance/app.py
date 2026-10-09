#!/usr/bin/env python3
"""
TestPerformance - Linux 系统性能测试 HTTP 服务

通过 HTTP 接口（GET/POST/DELETE）远程控制 Linux 系统性能测试，
支持 UFS（磁盘）和 DRAM（内存）测试。

用法:
    从上位机（如 Windows）通过 curl 发送命令:
    curl http://<linux-ip>:5000/api/ufs/usage
    curl http://<linux-ip>:5000/api/dram/occupy?percent=75&duration=60
    curl -X DELETE http://<linux-ip>:5000/api/dram/stress/stop
"""

import json
import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from scripts.ufs_test import (
    ufs_info,
    ufs_usage,
    ufs_occupy,
    ufs_read_speed,
    ufs_write_speed,
    ufs_partitions,
    ufs_stop_stress,
)
from scripts.dram_test import (
    dram_info,
    dram_usage,
    dram_occupy,
    dram_release,
    dram_read_speed,
    dram_write_speed,
    dram_stop_stress,
)

app = Flask(__name__)

# ============================================================
# 通用接口
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    """服务状态检查"""
    return jsonify({
        "status": "ok",
        "service": "TestPerformance",
        "version": "1.0.0",
        "message": "Service is running"
    })


# ============================================================
# UFS（磁盘）测试接口
# ============================================================

@app.route("/api/ufs/info", methods=["GET"])
def api_ufs_info():
    """
    获取 UFS 磁盘基本信息

    GET /api/ufs/info
    """
    return jsonify(ufs_info())


@app.route("/api/ufs/usage", methods=["GET"])
def api_ufs_usage():
    """
    获取磁盘占比

    GET /api/ufs/usage?path=/
    参数:
        path: 目标路径（默认 /）
    """
    path = request.args.get("path", "/")
    return jsonify(ufs_usage(path))


@app.route("/api/ufs/occupy", methods=["POST", "GET"])
def api_ufs_occupy():
    """
    磁盘占比压力测试 - 将磁盘使用率提升到指定百分比

    POST/GET /api/ufs/occupy?path=/&percent=75&duration=60&block_size=1M
    参数:
        path: 目标路径（默认 /）
        percent: 目标磁盘占比百分比（默认 75）
        duration: 保持时间秒数（默认 60）
        block_size: 写入块大小（默认 1M）
    """
    path = request.args.get("path", "/")
    percent = int(request.args.get("percent", 75))
    duration = int(request.args.get("duration", 60))
    block_size = request.args.get("block_size", "1M")

    if not 0 < percent <= 100:
        return jsonify({
            "status": "error",
            "message": "percent must be between 1 and 100"
        }), 400

    return jsonify(ufs_occupy(path, percent, duration, block_size))


@app.route("/api/ufs/read-speed", methods=["GET"])
def api_ufs_read_speed():
    """
    磁盘读取速率测试

    GET /api/ufs/read-speed?device=/dev/sda&block_size=1M&count=100
    参数:
        device: 块设备路径（默认 /dev/sda）
        block_size: 块大小（默认 1M）
        count: 读取块数（默认 100）
    """
    device = request.args.get("device", "/dev/sda")
    block_size = request.args.get("block_size", "1M")
    count = int(request.args.get("count", 100))

    return jsonify(ufs_read_speed(device, block_size, count))


@app.route("/api/ufs/write-speed", methods=["GET"])
def api_ufs_write_speed():
    """
    磁盘写入速率测试

    GET /api/ufs/write-speed?path=/&block_size=1M&count=100
    参数:
        path: 目标路径（默认 /）
        block_size: 块大小（默认 1M）
        count: 写入块数（默认 100）
    """
    path = request.args.get("path", "/")
    block_size = request.args.get("block_size", "1M")
    count = int(request.args.get("count", 100))

    return jsonify(ufs_write_speed(path, block_size, count))


@app.route("/api/ufs/partitions", methods=["GET"])
def api_ufs_partitions():
    """
    获取 UFS 分区信息

    GET /api/ufs/partitions
    """
    return jsonify(ufs_partitions())


@app.route("/api/ufs/stress/stop", methods=["DELETE", "POST"])
def api_ufs_stop_stress():
    """
    停止正在运行的 UFS 压力测试

    DELETE/POST /api/ufs/stress/stop
    """
    return jsonify(ufs_stop_stress())


# ============================================================
# DRAM（内存）测试接口
# ============================================================

@app.route("/api/dram/info", methods=["GET"])
def api_dram_info():
    """
    获取 DRAM 内存基本信息

    GET /api/dram/info
    """
    return jsonify(dram_info())


@app.route("/api/dram/usage", methods=["GET"])
def api_dram_usage():
    """
    获取当前内存占比

    GET /api/dram/usage
    """
    return jsonify(dram_usage())


@app.route("/api/dram/occupy", methods=["POST", "GET"])
def api_dram_occupy():
    """
    内存占比压力测试 - 将内存使用率提升到指定百分比

    POST/GET /api/dram/occupy?percent=75&duration=60&block_size=1M
    参数:
        percent: 目标内存占比百分比（默认 75）
        duration: 保持时间秒数（默认 60，0=持续直到手动释放）
        block_size: 每次分配的块大小（默认 1M）
    """
    percent = int(request.args.get("percent", 75))
    duration = int(request.args.get("duration", 60))
    block_size = request.args.get("block_size", "1M")

    if not 0 < percent <= 100:
        return jsonify({
            "status": "error",
            "message": "percent must be between 1 and 100"
        }), 400

    return jsonify(dram_occupy(percent, duration, block_size))


@app.route("/api/dram/release", methods=["DELETE", "POST"])
def api_dram_release():
    """
    释放正在占用的内存

    DELETE/POST /api/dram/release
    """
    return jsonify(dram_release())


@app.route("/api/dram/read-speed", methods=["GET"])
def api_dram_read_speed():
    """
    内存读取速率测试

    GET /api/dram/read-speed?block_size=1M&total_size=1G&threads=1&max_time=10
    参数:
        block_size: 内存块大小（默认 1M）
        total_size: 总传输数据量（默认 1G）
        threads: 工作线程数（默认 1）
        max_time: 最大测试时间秒数（默认 10）
    """
    block_size = request.args.get("block_size", "1M")
    total_size = request.args.get("total_size", "1G")
    threads = int(request.args.get("threads", 1))
    max_time = int(request.args.get("max_time", 10))

    return jsonify(dram_read_speed(block_size, total_size, threads, max_time))


@app.route("/api/dram/write-speed", methods=["GET"])
def api_dram_write_speed():
    """
    内存写入速率测试

    GET /api/dram/write-speed?block_size=1M&total_size=1G&threads=1&max_time=10
    参数:
        block_size: 内存块大小（默认 1M）
        total_size: 总传输数据量（默认 1G）
        threads: 工作线程数（默认 1）
        max_time: 最大测试时间秒数（默认 10）
    """
    block_size = request.args.get("block_size", "1M")
    total_size = request.args.get("total_size", "1G")
    threads = int(request.args.get("threads", 1))
    max_time = int(request.args.get("max_time", 10))

    return jsonify(dram_write_speed(block_size, total_size, threads, max_time))


@app.route("/api/dram/stress/stop", methods=["DELETE", "POST"])
def api_dram_stop_stress():
    """
    停止所有正在运行的 DRAM 压力测试

    DELETE/POST /api/dram/stress/stop
    """
    return jsonify(dram_stop_stress())


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TestPerformance - Linux 系统性能测试 HTTP 服务"
    )
    parser.add_argument(
        "-H", "--host",
        default="0.0.0.0",
        help="监听地址（默认 0.0.0.0，接受所有连接）"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=5000,
        help="监听端口（默认 5000）"
    )
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        default=False,
        help="启用调试模式"
    )
    args = parser.parse_args()

    print(f"=" * 60)
    print(f"TestPerformance HTTP Server")
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print(f"  Debug: {args.debug}")
    print(f"=" * 60)
    print(f"")
    print(f"API Endpoints:")
    print(f"  GET  /api/status          - 服务状态检查")
    print(f"  GET  /api/ufs/info        - UFS 磁盘基本信息")
    print(f"  GET  /api/ufs/usage       - 磁盘占比查询")
    print(f"  POST /api/ufs/occupy      - 磁盘占比压力测试")
    print(f"  GET  /api/ufs/read-speed  - 磁盘读取速率测试")
    print(f"  GET  /api/ufs/write-speed - 磁盘写入速率测试")
    print(f"  GET  /api/ufs/partitions  - UFS 分区信息")
    print(f"  DEL  /api/ufs/stress/stop - 停止 UFS 压力测试")
    print(f"  GET  /api/dram/info       - DRAM 内存基本信息")
    print(f"  GET  /api/dram/usage      - 内存占比查询")
    print(f"  POST /api/dram/occupy     - 内存占比压力测试")
    print(f"  DEL  /api/dram/release    - 释放占用的内存")
    print(f"  GET  /api/dram/read-speed - 内存读取速率测试")
    print(f"  GET  /api/dram/write-speed- 内存写入速率测试")
    print(f"  DEL  /api/dram/stress/stop- 停止 DRAM 压力测试")
    print(f"")

    app.run(host=args.host, port=args.port, debug=args.debug)
