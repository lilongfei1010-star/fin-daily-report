#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪日报 - 主入口脚本
流程：采集数据 → 渲染HTML → 推送钉钉
"""
import os, sys, json, time, datetime, traceback, argparse
from pathlib import Path

WORK_DIR = "/workspace/fin_daily"  # 持久化目录，跨会话保留
OUT_DIR = "/workspace/reports"  # 最终输出目录

sys.path.insert(0, WORK_DIR)
from data_collector import collect_all_data
from html_renderer import render_html
from dingtalk_pusher import build_dingtalk_markdown, send_dingtalk_webhook
from pages_uploader import upload_html_to_pages, PAGES_BASE_URL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook", default=os.environ.get("DINGTALK_WEBHOOK", ""), help="钉钉Webhook URL")
    parser.add_argument("--secret", default=os.environ.get("DINGTALK_SECRET", ""), help="钉钉加签密钥（可选）")
    parser.add_argument("--no-push", action="store_true", help="不推送钉钉，仅生成本地文件")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub Token for Pages upload（必须通过环境变量GITHUB_TOKEN或本参数传入，不要硬编码）")
    parser.add_argument("--no-gist", action="store_true", help="不上传到Gist")
    parser.add_argument("--work-dir", default=WORK_DIR, help="工作目录")
    parser.add_argument("--out-dir", default=OUT_DIR, help="输出目录")
    args = parser.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    data_path = f"{args.out_dir}/data_{today}.json"
    html_path = f"{args.out_dir}/report_{today}.html"

    t0 = time.time()
    log = []

    # 1. 采集数据
    print("[STEP 1] 采集数据...", flush=True)
    try:
        data = collect_all_data()
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        log.append(f"✅ 数据采集完成，{time.time()-t0:.1f}s")
    except Exception as e:
        log.append(f"❌ 数据采集失败: {e}")
        print(traceback.format_exc())
        return False

    # 2. 渲染HTML
    t1 = time.time()
    print("[STEP 2] 渲染HTML...", flush=True)
    try:
        html_str = render_html(data)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_str)
        log.append(f"✅ HTML报告已生成: {html_path} ({len(html_str)//1024}KB, {time.time()-t1:.1f}s)")
    except Exception as e:
        log.append(f"❌ HTML渲染失败: {e}")
        print(traceback.format_exc())
        return False

    # 3. 上传HTML到GitHub Pages获取公网URL
    report_url = ""
    if args.no_gist or not args.github_token:
        log.append(f"⏭️  跳过Pages上传（token={'未配置' if not args.github_token else '手动禁用'}）")
    else:
        t2 = time.time()
        print("[STEP 3] 上传HTML到GitHub Pages...", flush=True)
        try:
            pages_result = upload_html_to_pages(html_str, args.github_token)
            if pages_result.get("success"):
                # 优先用index.html（主页URL更短更稳定），备选每日文件名
                report_url = pages_result.get("index_url") or pages_result.get("url", PAGES_BASE_URL)
                log.append(f"✅ Pages上传成功 ({time.time()-t2:.1f}s): {report_url}")
            else:
                log.append(f"❌ Pages上传失败: {pages_result.get('error')}")
        except Exception as e:
            log.append(f"❌ Pages上传异常: {e}")
            print(traceback.format_exc(), flush=True)

    # 4. 推送钉钉
    t3 = time.time()
    if args.no_push or not args.webhook:
        log.append(f"⏭️  跳过钉钉推送（webhook={'未配置' if not args.webhook else '手动禁用'}）")
    else:
        print("[STEP 4] 推送钉钉...", flush=True)
        try:
            msg = build_dingtalk_markdown(data, report_url)
            result = send_dingtalk_webhook(args.webhook, msg, args.secret)
            if result.get("errcode") == 0:
                log.append(f"✅ 钉钉推送成功 ({time.time()-t3:.1f}s)")
            else:
                log.append(f"❌ 钉钉推送失败: errcode={result.get('errcode')}, errmsg={result.get('errmsg')}")
                print(f"  钉钉返回: {result}", flush=True)
        except Exception as e:
            log.append(f"❌ 钉钉推送异常: {e}")
            print(traceback.format_exc(), flush=True)

    # 输出日志
    print("\n" + "="*50, flush=True)
    for line in log:
        print(line, flush=True)
    print(f"总耗时: {time.time()-t0:.1f}s", flush=True)
    print("="*50, flush=True)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
