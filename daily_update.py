"""
每日自动更新脚本（TRAE 定时任务专用）
=====================================
功能：
  1. 运行 macro_collector.py 采集当日宏观数据
  2. 通过 GitHub API 上传 daily_macro.json 到仓库
  3. Streamlit Cloud 自动检测更新并刷新仪表盘

用法：
  python daily_update.py

环境变量（可选）：
  GH_TOKEN      - GitHub PAT（有 repo 权限即可）
  FRED_API_KEY  - FRED API 密钥（提升宏观数据质量）
  LLM_API_KEY   - LLM 密钥（生成 AI 研判）
  LLM_BASE_URL  - LLM API 地址
  LLM_MODEL     - LLM 模型名
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# ---- 配置 ----
PROJECT_DIR = Path(__file__).parent.resolve()
DATA_FILE = PROJECT_DIR / "daily_macro.json"
GH_OWNER = "acmilanhm"
GH_REPO = "macro-dashboard"
GH_API = "https://api.github.com"
PYTHON = sys.executable

# GitHub Token：优先从环境变量读取，其次从配置文件读取
GH_TOKEN = os.getenv("GH_TOKEN", "")
if not GH_TOKEN:
    _config_path = Path.home() / ".trae-cn" / "work" / "6a77c5877e1337a59f363b14" / "gh_config.json"
    if _config_path.exists():
        import json as _json
        try:
            GH_TOKEN = _json.loads(_config_path.read_text())["gh_token"]
        except Exception:
            pass


def log(msg: str):
    print(f"[daily_update] {msg}", flush=True)


def install_deps():
    """确保依赖已安装。"""
    req_file = PROJECT_DIR / "requirements.txt"
    if req_file.exists():
        log("检查依赖...")
        subprocess.run(
            [PYTHON, "-m", "pip", "install", "-r", str(req_file), "-q"],
            cwd=str(PROJECT_DIR),
            check=False,
            timeout=120,
        )


def run_collector():
    """运行 macro_collector.py 采集数据（直接导入，避免子进程超时）。"""
    log("开始采集宏观数据...")
    old_cwd = os.getcwd()
    os.chdir(str(PROJECT_DIR))
    try:
        # 直接导入并调用，避免 subprocess 超时问题
        sys.path.insert(0, str(PROJECT_DIR))
        from macro_collector import collect_all
        collect_all(str(DATA_FILE))
        log("采集完成")
        return DATA_FILE.exists()
    except Exception as e:
        log(f"采集失败: {e}")
        return DATA_FILE.exists()
    finally:
        os.chdir(old_cwd)


def _upload_file_to_github(file_path: str, local_path: Path, headers: dict) -> bool:
    """上传单个文件到 GitHub（内部辅助函数）。"""
    if not local_path.exists():
        log(f"[WARN] 文件不存在: {local_path}")
        return False

    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    # 检查文件是否已存在（获取 sha）
    sha = None
    r = requests.get(
        f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/contents/{file_path}",
        headers=headers,
        timeout=20,
    )
    if r.status_code == 200:
        sha = r.json().get("sha")

    body = {
        "message": f"chore: update {file_path} {time.strftime('%Y-%m-%d')}",
        "content": content,
    }
    if sha:
        body["sha"] = sha

    r = requests.put(
        f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/contents/{file_path}",
        headers=headers,
        timeout=30,
        json=body,
    )

    if r.status_code in (200, 201):
        log(f"  上传成功: {file_path} ({r.status_code})")
        return True
    else:
        log(f"  上传失败: {file_path} {r.status_code} {r.text[:200]}")
        return False


def upload_to_github():
    """通过 GitHub API 上传 daily_macro.json 和历史数据文件。"""
    if not GH_TOKEN:
        log("[ERROR] 未设置 GH_TOKEN，无法上传到 GitHub")
        return False

    if not DATA_FILE.exists():
        log("[ERROR] daily_macro.json 不存在，无法上传")
        return False

    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    log("上传 daily_macro.json...")
    success = _upload_file_to_github("daily_macro.json", DATA_FILE, headers)

    # 上传今日历史数据文件
    history_dir = PROJECT_DIR / "data" / "history"
    if history_dir.exists():
        today_str = time.strftime("%Y-%m-%d")
        history_file = history_dir / f"{today_str}.json"
        if history_file.exists():
            log(f"上传历史数据 {history_file.name}...")
            _upload_file_to_github(
                f"data/history/{history_file.name}", history_file, headers
            )
        else:
            # 尝试找到最新的历史文件
            history_files = sorted(history_dir.glob("*.json"), reverse=True)
            if history_files:
                latest = history_files[0]
                log(f"上传最新历史数据 {latest.name}...")
                _upload_file_to_github(
                    f"data/history/{latest.name}", latest, headers
                )

    return success


def check_data_quality() -> bool:
    """检查采集到的数据是否有效（至少有价格、宏观或 AI 股票数据）。"""
    if not DATA_FILE.exists():
        return False
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        n_prices = len(data.get("prices", {}))
        n_macro = len(data.get("macro", {}))
        n_events = len(data.get("events", []))
        n_ai_stocks = len(data.get("ai_stocks", {}))
        log(f"数据质量: 价格{n_prices}项 宏观{n_macro}项 AI股票{n_ai_stocks}只 事件{n_events}条")
        # 至少要有价格、宏观或 AI 股票数据才算有效
        if n_prices > 0 or n_macro > 0 or n_ai_stocks > 0:
            return True
        log("[WARN] 采集数据为空（可能 API 限流/网络问题）")
        return False
    except Exception as e:
        log(f"[WARN] 数据质量检查失败: {e}")
        return False


def main():
    log("=" * 50)
    log("每日宏观仪表盘自动更新")
    log(f"项目目录: {PROJECT_DIR}")
    log(f"Python: {PYTHON}")
    log("=" * 50)

    # 1. 安装依赖
    install_deps()

    # 2. 采集数据
    success = run_collector()
    if not success:
        log("数据采集失败")

    # 3. 检查数据质量 - 防止空数据覆盖好数据
    data_valid = check_data_quality()

    # 4. 上传到 GitHub（仅在数据有效时上传）
    if data_valid:
        upload_to_github()
    else:
        log("[SKIP] 数据无效，跳过上传以保留 GitHub 上的之前数据")
        log("        仪表盘将继续显示上一次的有效数据")

    log("更新流程结束")


if __name__ == "__main__":
    main()
