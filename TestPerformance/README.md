# TestPerformance

Linux 系统性能测试 HTTP 服务应用，支持通过 HTTP 接口远程操控 Linux 系统的 UFS（磁盘）和 DRAM（内存）性能测试。

## 架构

```
上位机 (Windows/Linux)              Linux 目标机
┌─────────────────┐                 ┌─────────────────────────────┐
│  curl / 浏览器   │  HTTP Request   │  TestPerformance            │
│                 │ ──────────────> │  ┌─────────┐  ┌──────────┐ │
│  发送测试指令    │                 │  │ Flask   │─>│ Python   │ │
│                 │ <────────────── │  │ Server  │  │ Scripts  │ │
│  接收测试结果    │  JSON Response  │  └─────────┘  └──────────┘ │
└─────────────────┘                 │       │          │          │
                                    │       ▼          ▼          │
                                    │   HTTP接口   Linux命令      │
                                    └─────────────────────────────┘
```

## 项目结构

```
TestPerformance/
├── app.py                  # Flask HTTP 服务主程序
├── scripts/
│   ├── __init__.py         # Python 包
│   ├── ufs_test.py         # UFS（磁盘）测试脚本
│   └── dram_test.py        # DRAM（内存）测试脚本
├── requirements.txt        # Python 依赖
├── start.sh               # 启动/停止脚本
└── README.md              # 本文档
```

## 安装

```bash
# 进入项目目录
cd TestPerformance

# 安装依赖
pip3 install -r requirements.txt
```

## 启动

```bash
# 方法1: 使用启动脚本（推荐，后台运行）
chmod +x start.sh
./start.sh              # 默认端口 5000
./start.sh 8080         # 指定端口 8080
./start.sh 8080 -d      # 调试模式
./start.sh stop         # 停止服务

# 方法2: 直接运行（前台）
python3 app.py -p 5000

# 方法3: 调试模式
python3 app.py -p 5000 --debug
```

## Flask 框架说明

本项目使用 [Flask](https://flask.palletsprojects.com/) 作为 HTTP 服务框架。Flask 是一个轻量级的 Python Web 框架，适合构建小型 REST API 服务。

### 为什么选择 Flask

- **轻量级**：核心依赖少，安装包小，适合嵌入式 Linux 环境
- **简单易用**：路由注册、请求解析、JSON 响应均内置支持
- **灵活扩展**：通过装饰器 `@app.route()` 即可快速注册 HTTP 接口

### Flask 在本项目中的角色

```
curl 请求 --> Flask 路由分发 --> 调用 Python 脚本 --> 执行 Linux 命令
                                       |
                                  返回 JSON 响应
```

1. **HTTP 服务监听**：`app.py` 中通过 `Flask(__name__)` 创建应用实例，监听 `0.0.0.0:5000` 端口
2. **路由注册**：使用 `@app.route("/api/...", methods=["GET", "POST", "DELETE"])` 装饰器注册接口
3. **参数解析**：通过 `request.args.get("key", "default")` 从 URL 查询字符串中提取参数
4. **JSON 响应**：通过 `jsonify()` 将 Python 字典序列化为 JSON 返回给客户端

### 接口注册示例

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/api/ufs/usage", methods=["GET"])
def api_ufs_usage():
    path = request.args.get("path", "/")   # 从 URL 获取参数
    result = ufs_usage(path)                # 调用 Python 测试脚本
    return jsonify(result)                  # 返回 JSON 响应
```

### 配置选项

启动时可通过命令行参数配置 Flask 服务：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-H` / `--host` | `0.0.0.0` | 监听地址，`0.0.0.0` 表示接受所有来源连接 |
| `-p` / `--port` | `5000` | 监听端口号 |
| `-d` / `--debug` | `False` | 启用 Flask 调试模式（热重载 + 详细错误日志） |

> **注意**：生产环境建议不使用 `--debug` 模式，可通过 `start.sh` 脚本后台运行。

## HTTP 接口说明

### 通用接口

| 方法 | 接口 | 说明 |
|------|------|------|
| GET | `/api/status` | 服务状态检查 |

### UFS（磁盘）测试接口

| 方法 | 接口 | 说明 |
|------|------|------|
| GET | `/api/ufs/info` | 获取 UFS 磁盘基本信息 |
| GET | `/api/ufs/usage?path=/` | 查询磁盘占比 |
| POST/GET | `/api/ufs/occupy?percent=75&duration=60&path=/&block_size=1M` | 磁盘占比压力测试 |
| GET | `/api/ufs/read-speed?device=/dev/sda&block_size=1M&count=100` | 磁盘读取速率测试 |
| GET | `/api/ufs/write-speed?path=/&block_size=1M&count=100` | 磁盘写入速率测试 |
| GET | `/api/ufs/partitions` | 获取 UFS 分区信息 |
| DELETE/POST | `/api/ufs/stress/stop` | 停止 UFS 压力测试 |

### DRAM（内存）测试接口

| 方法 | 接口 | 说明 |
|------|------|------|
| GET | `/api/dram/info` | 获取 DRAM 内存基本信息 |
| GET | `/api/dram/usage` | 查询当前内存占比 |
| POST/GET | `/api/dram/occupy?percent=75&duration=60&block_size=1M` | 内存占比压力测试 |
| DELETE/POST | `/api/dram/release` | 释放占用的内存 |
| GET | `/api/dram/read-speed?block_size=1M&total_size=1G&threads=1&max_time=10` | 内存读取速率测试 |
| GET | `/api/dram/write-speed?block_size=1M&total_size=1G&threads=1&max_time=10` | 内存写入速率测试 |
| DELETE/POST | `/api/dram/stress/stop` | 停止 DRAM 压力测试 |

## curl 使用说明

[curl](https://curl.se/) 是一个命令行下的 HTTP 客户端工具，用于向上位机发送 HTTP 请求并接收响应。本项目所有接口均支持通过 curl 调用。

### 安装 curl

```bash
# Windows（推荐使用 winget 或 scoop 安装）
winget install curl
# 或从官网下载: https://curl.se/windows/

# Linux（通常已预装，如未安装）
sudo apt install curl        # Debian/Ubuntu
sudo yum install curl        # CentOS/RHEL
```

### 基本语法

```bash
curl [选项] <URL>
```

### 常用选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `-X <METHOD>` | 指定 HTTP 方法（默认 GET） | `curl -X DELETE http://...` |
| `-s` | 静默模式，不显示进度条 | `curl -s http://...` |
| `-S` | 配合 `-s` 使用，出错时仍显示错误信息 | `curl -sS http://...` |
| `-v` | 详细模式，显示请求/响应头 | `curl -v http://...` |
| `-o <file>` | 将响应保存到文件 | `curl -o result.json http://...` |
| `-w <format>` | 自定义输出格式（如状态码、耗时） | `curl -w "\n%{http_code}" http://...` |

### URL 参数拼接规则

本项目参数直接拼接在 URL 查询字符串中，**不使用** POST body：

```bash
# 无参数
curl http://<IP>:5000/api/dram/usage

# 单个参数
curl "http://<IP>:5000/api/ufs/usage?path=/home"

# 多个参数用 & 连接（URL 含特殊字符时必须加引号）
curl "http://<IP>:5000/api/ufs/occupy?percent=75&duration=60&path=/data"
```

> **注意**：当 URL 中包含 `&`、`?` 等特殊字符时，务必用双引号 `"..."` 包裹整个 URL，防止 Shell 解析错误。

### JSON 响应美化

curl 返回的 JSON 默认是紧凑格式，可通过以下方式美化输出：

```bash
# 方法1: 配合 python3 格式化（Linux 推荐）
curl -s http://<IP>:5000/api/dram/usage | python3 -m json.tool

# 方法2: 配合 jq 工具格式化（需安装 jq）
curl -s http://<IP>:5000/api/dram/usage | jq .
```

### Windows CMD / PowerShell 注意事项

```cmd
# Windows CMD: 使用双引号包裹 URL
curl "http://192.168.1.100:5000/api/ufs/occupy?percent=75&duration=60"

# PowerShell: 双引号中的 & 会被解释，需用反引号转义或使用单引号
curl.exe 'http://192.168.1.100:5000/api/ufs/occupy?percent=75&duration=60'
# 或使用 Invoke-WebRequest
curl.exe -X DELETE http://192.168.1.100:5000/api/dram/release
```

> **PowerShell 提示**：PowerShell 中 `curl` 默认是 `Invoke-WebRequest` 的别名，请使用 `curl.exe` 确保调用真正的 curl 程序。

### 常用调试技巧

```bash
# 查看 HTTP 响应状态码
curl -s -o /dev/null -w "%{http_code}" http://<IP>:5000/api/status

# 查看完整的请求/响应头（调试连接问题）
curl -v http://<IP>:5000/api/status

# 设置超时时间（防止长时间阻塞）
curl --connect-timeout 5 --max-time 120 http://<IP>:5000/api/ufs/read-speed

# 将结果保存到文件
curl -s http://<IP>:5000/api/dram/info -o dram_info.json
```

## curl 使用示例

以下示例假设 Linux 目标机 IP 为 `192.168.1.100`，服务端口为 `5000`。

### 1. 服务状态检查
```bash
curl http://192.168.1.100:5000/api/status
```

### 2. 查询磁盘占比
```bash
curl http://192.168.1.100:5000/api/ufs/usage
curl "http://192.168.1.100:5000/api/ufs/usage?path=/home"
```

### 3. 磁盘占比 75% 压力测试
```bash
# 占比 75%，保持 60 秒
curl "http://192.168.1.100:5000/api/ufs/occupy?percent=75&duration=60"

# 占比 80%，保持 120 秒，指定路径
curl "http://192.168.1.100:5000/api/ufs/occupy?percent=80&duration=120&path=/data"

# 使用 POST 方式
curl -X POST "http://192.168.1.100:5000/api/ufs/occupy?percent=75&duration=60"
```

### 4. 磁盘读取速率测试
```bash
# 默认测试
curl http://192.168.1.100:5000/api/ufs/read-speed

# 自定义参数
curl "http://192.168.1.100:5000/api/ufs/read-speed?device=/dev/sda&block_size=4M&count=50"
```

### 5. 查询内存占比
```bash
curl http://192.168.1.100:5000/api/dram/usage
```

### 6. 内存占比 75% 压力测试
```bash
# 占比 75%，保持 60 秒
curl "http://192.168.1.100:5000/api/dram/occupy?percent=75&duration=60"

# 持续占用直到手动释放
curl "http://192.168.1.100:5000/api/dram/occupy?percent=75&duration=0"
```

### 7. 释放占用的内存
```bash
curl -X DELETE http://192.168.1.100:5000/api/dram/release
# 或者
curl -X POST http://192.168.1.100:5000/api/dram/release
```

### 8. 内存读取速率测试
```bash
# 默认测试
curl http://192.168.1.100:5000/api/dram/read-speed

# 自定义参数：2 线程，测试 30 秒
curl "http://192.168.1.100:5000/api/dram/read-speed?threads=2&max_time=30&total_size=2G"
```

### 9. 停止所有压力测试
```bash
curl -X DELETE http://192.168.1.100:5000/api/ufs/stress/stop
curl -X DELETE http://192.168.1.100:5000/api/dram/stress/stop
```

## JSON 返回格式

所有接口返回统一的 JSON 格式：

```json
{
    "status": "ok",
    "exit_code": 0,
    "details": { ... },
    "message": "描述信息"
}
```

| 字段 | 说明 |
|------|------|
| status | `ok` 成功，`error` 失败 |
| exit_code | `0` 成功，非零值表示错误码 |
| details | 测试结果详细数据 |
| message | 结果描述信息 |

## 依赖

- Python 3.6+
- Flask >= 2.3.0
- Linux 系统工具: `dd`, `df`, `lsblk`（通常预装）
- 可选: `sysbench`（用于更精确的内存速率测试）、`hdparm`（用于磁盘缓存速度测试）
