#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪日报 - 钉钉推送模块
- 推送Markdown消息（摘要+报告要点）
- 可选：上传HTML报告到沙箱预览服务获取URL
"""
import os, sys, json, time, datetime, requests


def build_dingtalk_markdown(data: dict, report_url: str = "") -> dict:
    """构建钉钉Markdown消息体"""
    meta = data.get("_meta", {})
    report_date = meta.get("trade_date", "")
    if report_date and len(report_date) == 8:
        report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"

    index_rt = data.get("index_realtime", [])
    zt_summary = data.get("zt_summary", {})

    # 板块资金概览
    industry = data.get("sector_industry_today", [])
    def safe_num(v):
        if v is None or v == "" or v == "-":
            return 0.0
        try: return float(v)
        except (TypeError, ValueError): return 0.0
    # 指数概要
    idx_lines = []
    for idx in index_rt:
        pct = safe_num(idx.get("pct"))
        pct_str = f"{pct:+.2f}%" if pct != 0 else "-"
        sign = "▲" if pct > 0 else "▼" if pct < 0 else "—"
        idx_lines.append(f"- **{idx.get('name')}** {idx.get('close')} {pct_str} {sign}")
    idx_text = "\n".join(idx_lines) if idx_lines else "（无数据）"

    in_total = sum(safe_num(s.get("main_net")) for s in industry if safe_num(s.get("main_net")) > 0)
    top3_in = sorted(industry, key=lambda x: safe_num(x.get("main_net")), reverse=True)[:3]
    top3_out = sorted(industry, key=lambda x: safe_num(x.get("main_net")))[:3]

    def fmt(v):
        av = abs(v)
        sign = "-" if v < 0 else ""
        if av >= 1e8: return f"{sign}{av/1e8:.1f}亿"
        if av >= 1e4: return f"{sign}{av/1e4:.0f}万"
        return f"{sign}{av:.0f}"

    sector_text = f"**行业板块资金净流入合计 {fmt(in_total - sum(safe_num(s.get('main_net')) for s in industry if safe_num(s.get('main_net')) < 0))}**\n\n"
    sector_text += "净流入TOP3：\n" + "\n".join(f"- {s.get('name')} {fmt(safe_num(s.get('main_net')))}" for s in top3_in if safe_num(s.get('main_net')) > 0)
    sector_text += "\n\n净流出TOP3：\n" + "\n".join(f"- {s.get('name')} {fmt(safe_num(s.get('main_net')))}" for s in top3_out if safe_num(s.get('main_net')) < 0)

    # 个股资金概览
    individual = data.get("individual_fund_today", [])
    top3_ind = individual[:3]
    ind_text = "**今日主力净流入TOP3**\n"
    for s in top3_ind:
        ind_text += f"- {s.get('name')}({s.get('code')}) {fmt(safe_num(s.get('main_net')))} ({safe_num(s.get('pct')):+.2f}%)\n"

    # 涨幅概览
    gain_10d = data.get("stock_gain_10d", [])[:3]
    gain_text = "**近10日涨幅TOP3**\n" + "\n".join(
        f"- {s.get('name')}({s.get('code')}) {safe_num(s.get('pct_ndays')):+.2f}%" for s in gain_10d)

    # 涨停板
    zt_text = (f"**涨停 {zt_summary.get('zt_count', 0)} 家** · 跌停 {len(data.get('dt_pool', []))} 家\n\n"
               f"- 最高连板：{zt_summary.get('max_lb', 0)}板（{zt_summary.get('max_lb_name', '-')}·{zt_summary.get('max_lb_concept', '-')}）\n"
               f"- 最高几天几板：{zt_summary.get('max_jtjb_stat', '-')}（{zt_summary.get('max_jtjb_name', '-')}·{zt_summary.get('max_jtjb_concept', '-')}）")

    title = f"📊 A股金融市场情绪日报 · {report_date}"
    # 完整报告链接
    link_section = ""
    if report_url:
        link_section = f"\n\n## 📄 完整报告\n[点击查看完整HTML报告]({report_url})\n（含四大模块/15个数据表/交互图表）"

    content = f"""# {title}

> 金融市场每日监控报告 · 数据源：东方财富/新浪财经

## 一、市场情绪
{idx_text}

{zt_text}

## 二、板块资金流向
{sector_text}

## 三、个股资金动向
{ind_text}

{gain_text}{link_section}

---
> 金融市场有风险，投资需谨慎 · 生成时间：{meta.get('collect_time', '')}"""

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": content,
        }
    }


def send_dingtalk_webhook(webhook_url: str, msg: dict, secret: str = None) -> dict:
    """发送钉钉Webhook消息
    webhook_url: 钉钉群机器人Webhook地址
    secret: 可选，加签密钥（如果机器人开启了"加签验证"）
    """
    headers = {"Content-Type": "application/json; charset=utf-8"}
    full_url = webhook_url
    if secret:
        import base64, hmac, hashlib
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{secret}'.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = urllib_quote(base64.b64encode(hmac_code).decode('utf-8'))
        sep = '&' if '?' in full_url else '?'
        full_url = f"{full_url}{sep}timestamp={timestamp}&sign={sign}"

    try:
        r = requests.post(full_url, headers=headers, data=json.dumps(msg, ensure_ascii=False), timeout=20)
        return r.json()
    except Exception as e:
        return {"errcode": -1, "errmsg": str(e)}


def urllib_quote(s: str) -> str:
    """URL编码（钉钉签名要求）"""
    from urllib.parse import quote
    return quote(s, safe='')


if __name__ == "__main__":
    # 单独测试用：从data.json构建消息
    data_file = sys.argv[1] if len(sys.argv) > 1 else "/workspace/fin_daily/data.json"
    with open(data_file, "r", encoding="utf-8") as f:
        d = json.load(f)
    msg = build_dingtalk_markdown(d)
    print(json.dumps(msg, ensure_ascii=False, indent=2))
