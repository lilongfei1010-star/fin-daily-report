#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪日报 - GitHub Pages上传模块
- 上传HTML到 fin-daily-report 仓库的 gh-pages 分支
- 公开访问URL: https://lilongfei1010-star.github.io/fin-daily-report/金融日报_YYYYMMDD.html
- 不覆盖现有index.html和历史报告
"""
import os, sys, json, requests, time
from datetime import datetime
import base64

REPO = "lilongfei1010-star/fin-daily-report"
BRANCH = "gh-pages"
PAGES_BASE_URL = f"https://lilongfei1010-star.github.io/fin-daily-report"


def upload_html_to_pages(html_content: str, token: str, filename: str = None, also_update_index: bool = True) -> dict:
    """上传HTML到GitHub Pages
    filename: 文件名（不含路径），默认 金融日报_YYYYMMDD.html
    also_update_index: 是否同时覆盖 index.html（访问主页即可看到最新报告）
    """
    if filename is None:
        today = datetime.now().strftime("%Y%m%d")
        filename = f"金融日报_{today}.html"

    H = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    targets = [filename]
    if also_update_index:
        targets.append("index.html")
    last_error = ""

    for target in targets:
        url = f"https://api.github.com/repos/{REPO}/contents/{target}"
        # 检查文件是否已存在（获取sha）
        sha = None
        for attempt in range(3):
            try:
                r = requests.get(url, headers=H, params={"ref": BRANCH}, timeout=30)
                if r.status_code == 200:
                    sha = r.json().get("sha")
                    break
                elif r.status_code == 404:
                    break  # 新文件
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)

        # 上传
        payload = {
            "message": f"update {target}" if sha else f"add {target}",
            "content": base64.b64encode(html_content.encode("utf-8")).decode("utf-8"),
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha

        target_success = False
        for attempt in range(5):
            try:
                r = requests.put(url, headers=H, json=payload, timeout=60)
                if r.status_code in (200, 201):
                    target_success = True
                    break
                elif r.status_code == 503:
                    wait = 5 * (attempt + 1)
                    print(f"[WARN] Pages上传503，{wait}秒后重试 ({attempt+1}/5)", file=sys.stderr)
                    time.sleep(wait)
                    continue
                else:
                    err = r.json().get("message", f"HTTP {r.status_code}")
                    if attempt < 4:
                        time.sleep(3)
                        continue
                    last_error = f"{target}: {err}"
                    break
            except Exception as e:
                if attempt < 4:
                    time.sleep(3)
                    continue
                last_error = f"{target}: {e}"
                break

        if not target_success:
            return {"success": False, "url": "", "filename": target, "error": last_error}

    return {
        "success": True,
        "url": f"{PAGES_BASE_URL}/{filename}",
        "index_url": f"{PAGES_BASE_URL}/",
        "filename": filename,
        "error": ""
    }


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("错误：请通过环境变量GITHUB_TOKEN传入GitHub Token", file=sys.stderr)
        sys.exit(1)
    html_file = sys.argv[1] if len(sys.argv) > 1 else "/workspace/reports/report_20260720.html"
    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()
    result = upload_html_to_pages(content, token)
    print(json.dumps(result, ensure_ascii=False, indent=2))
