#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪日报 - HTML渲染模块
将采集的JSON数据渲染为专业HTML报告：
- 顶部锚点导航（点击跳转各模块）
- 表格首列固定、横向可滚动
- Plotly交互式趋势图
- 专业深色金融风格
"""
import json, os, sys, datetime, html
from typing import Any

# ============ 工具函数 ============
def esc(v) -> str:
    """HTML转义"""
    if v is None or v == "":
        return "-"
    return html.escape(str(v))


def fmt_amt(v) -> str:
    """金额格式化：亿/万"""
    if v is None or v == "-" or v == "":
        return "-"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e8:
        return f"{sign}{av/1e8:.2f}亿"
    elif av >= 1e4:
        return f"{sign}{av/1e4:.2f}万"
    return f"{sign}{av:.0f}"


def fmt_pct(v, with_sign=True) -> str:
    if v is None or v == "-" or v == "":
        return "-"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if with_sign:
        return f"{v:+.2f}%"
    return f"{v:.2f}%"


def fmt_pct_color(v) -> str:
    """带颜色的涨跌幅"""
    if v is None or v == "":
        return '<span class="muted">-</span>'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if v > 0:
        return f'<span class="up">+{v:.2f}%</span>'
    elif v < 0:
        return f'<span class="down">{v:.2f}%</span>'
    return f'<span class="flat">{v:.2f}%</span>'


def fmt_amt_color(v) -> str:
    """带颜色的金额"""
    if v is None or v == "":
        return '<span class="muted">-</span>'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if v > 0:
        return f'<span class="up">{fmt_amt(v)}</span>'
    elif v < 0:
        return f'<span class="down">{fmt_amt(v)}</span>'
    return f'<span class="flat">{fmt_amt(v)}</span>'


def safe_float(v, default=0.0):
    if v is None or v == "" or v == "-":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ============ SVG 图表（纯SVG，无需JS库，兼容所有环境） ============

def _svg_line_chart(series: list, x_labels: list, width: int = 800, height: int = 300,
                    y_label: str = "", title: str = "") -> str:
    """纯SVG折线图
    series: [{"name": "上证", "data": [3913, 3967, ...], "color": "#ff4d4f"}, ...]
    x_labels: ["07-13", "07-14", ...]
    """
    if not series or not x_labels:
        return '<div class="empty">暂无数据</div>'
    padding = {"l": 60, "r": 20, "t": 30, "b": 40}
    plot_w = width - padding["l"] - padding["r"]
    plot_h = height - padding["t"] - padding["b"]

    # 计算y轴范围
    all_vals = [v for s in series for v in s["data"] if v is not None]
    if not all_vals:
        return '<div class="empty">暂无数据</div>'
    y_min, y_max = min(all_vals), max(all_vals)
    if y_min == y_max:
        y_min -= 1; y_max += 1
    y_range = y_max - y_min
    y_min -= y_range * 0.1
    y_max += y_range * 0.1

    n = len(x_labels)
    x_step = plot_w / (n - 1) if n > 1 else plot_w

    def x_pos(i): return padding["l"] + i * x_step
    def y_pos(v): return padding["t"] + plot_h * (1 - (v - y_min) / (y_max - y_min))

    # 网格线
    grid_lines = ""
    for i in range(5):
        y = padding["t"] + plot_h * i / 4
        val = y_max - (y_max - y_min) * i / 4
        grid_lines += f'<line x1="{padding["l"]}" y1="{y}" x2="{width-padding["r"]}" y2="{y}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>'
        grid_lines += f'<text x="{padding["l"]-8}" y="{y+4}" text-anchor="end" fill="#8b949e" font-size="10">{val:.2f}</text>'

    # x轴标签
    x_labels_svg = ""
    for i, label in enumerate(x_labels):
        x_labels_svg += f'<text x="{x_pos(i)}" y="{height-padding["b"]+18}" text-anchor="middle" fill="#8b949e" font-size="10">{label}</text>'

    # 折线
    lines_svg = ""
    legend_svg = ""
    for i, s in enumerate(series):
        color = s.get("color", "#888")
        data = s["data"]
        points = []
        for j, v in enumerate(data):
            if v is not None:
                points.append(f"{x_pos(j)},{y_pos(v)}")
        if points:
            path = "M " + " L ".join(points)
            lines_svg += f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>'
            for p in points:
                x, y = p.split(",")
                lines_svg += f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>'
        # 图例
        legend_x = padding["l"] + i * 120
        legend_svg += f'<rect x="{legend_x}" y="8" width="12" height="3" fill="{color}"/>'
        legend_svg += f'<text x="{legend_x+18}" y="13" fill="#e6edf3" font-size="11">{s["name"]}</text>'

    title_svg = f'<text x="{width/2}" y="20" text-anchor="middle" fill="#e6edf3" font-size="13" font-weight="600">{title}</text>' if title else ""
    y_label_svg = f'<text x="15" y="{height/2}" transform="rotate(-90 15 {height/2})" text-anchor="middle" fill="#8b949e" font-size="11">{y_label}</text>' if y_label else ""

    return f'''<div class="chart-container">
<svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;background:rgba(20,20,30,0.6);border-radius:8px;">
{legend_svg}
{title_svg}
{y_label_svg}
{grid_lines}
{x_labels_svg}
{lines_svg}
</svg>
</div>'''


def _svg_bar_chart(categories: list, series: list, width: int = 800, height: int = 350,
                   y_label: str = "", title: str = "", grouped: bool = False) -> str:
    """纯SVG柱状图
    categories: ["07-13", "07-14", ...] x轴标签
    series: [{"name": "行业A", "data": [1.2, 2.3, ...], "color": "#ff4d4f"}, ...]
    grouped: True=分组柱状，False=单系列
    """
    if not series or not categories:
        return '<div class="empty">暂无数据</div>'
    padding = {"l": 60, "r": 20, "t": 40, "b": 40}
    plot_w = width - padding["l"] - padding["r"]
    plot_h = height - padding["t"] - padding["b"]

    all_vals = [v for s in series for v in s["data"] if v is not None]
    if not all_vals:
        return '<div class="empty">暂无数据</div>'
    y_min = min(0, min(all_vals))
    y_max = max(0, max(all_vals))
    if y_max == y_min: y_max += 1
    y_max += (y_max - y_min) * 0.15

    n_cat = len(categories)
    n_ser = len(series)
    group_w = plot_w / n_cat
    bar_w = (group_w * 0.7) / n_ser if grouped else group_w * 0.6

    def y_pos(v): return padding["t"] + plot_h * (1 - (v - y_min) / (y_max - y_min))

    # 网格
    grid_lines = ""
    for i in range(5):
        y = padding["t"] + plot_h * i / 4
        val = y_max - (y_max - y_min) * i / 4
        grid_lines += f'<line x1="{padding["l"]}" y1="{y}" x2="{width-padding["r"]}" y2="{y}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>'
        grid_lines += f'<text x="{padding["l"]-8}" y="{y+4}" text-anchor="end" fill="#8b949e" font-size="10">{val:.1f}</text>'

    # 0线
    if y_min < 0 < y_max:
        zero_y = y_pos(0)
        grid_lines += f'<line x1="{padding["l"]}" y1="{zero_y}" x2="{width-padding["r"]}" y2="{zero_y}" stroke="rgba(255,255,255,0.3)" stroke-width="1"/>'

    # 柱子
    bars_svg = ""
    for ci, cat in enumerate(categories):
        group_x = padding["l"] + ci * group_w + group_w * 0.15
        for si, s in enumerate(series):
            v = s["data"][ci] if ci < len(s["data"]) else None
            if v is None: continue
            color = s.get("color", "#888")
            bar_x = group_x + si * bar_w
            bar_y = y_pos(v)
            zero_y = y_pos(0) if y_min < 0 else padding["t"] + plot_h
            bar_h = abs(zero_y - bar_y)
            if v < 0: bar_y = zero_y
            bars_svg += f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w*0.85}" height="{bar_h}" fill="{color}" rx="2"/>'
            # 数值标签
            label_y = bar_y - 4 if v >= 0 else bar_y + bar_h + 12
            bars_svg += f'<text x="{bar_x+bar_w*0.425}" y="{label_y}" text-anchor="middle" fill="#8b949e" font-size="9">{v:.1f}</text>'
        # x轴标签
        label_x = padding["l"] + ci * group_w + group_w * 0.5
        bars_svg += f'<text x="{label_x}" y="{height-padding["b"]+18}" text-anchor="middle" fill="#8b949e" font-size="10">{cat}</text>'

    # 图例
    legend_svg = ""
    for i, s in enumerate(series):
        lx = padding["l"] + i * 120
        legend_svg += f'<rect x="{lx}" y="8" width="12" height="12" fill="{s.get("color","#888")}" rx="2"/>'
        legend_svg += f'<text x="{lx+18}" y="18" fill="#e6edf3" font-size="11">{s["name"]}</text>'

    title_svg = f'<text x="{width/2}" y="25" text-anchor="middle" fill="#e6edf3" font-size="13" font-weight="600">{title}</text>' if title else ""
    y_label_svg = f'<text x="15" y="{height/2}" transform="rotate(-90 15 {height/2})" text-anchor="middle" fill="#8b949e" font-size="11">{y_label}</text>' if y_label else ""

    return f'''<div class="chart-container">
<svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;background:rgba(20,20,30,0.6);border-radius:8px;">
{legend_svg}
{title_svg}
{y_label_svg}
{grid_lines}
{bars_svg}
</svg>
</div>'''


def chart_index_5d(kline_data: dict) -> str:
    """三大指数近5日走势图（收盘价折线 + 成交量柱状）"""
    colors = {"上证指数": "#ff4d4f", "深证成指": "#52c41a", "创业板指": "#1890ff"}
    # 收集日期
    all_dates = []
    for name, rows in kline_data.items():
        if rows:
            all_dates = [r["date"][-5:] for r in rows]
            break
    if not all_dates:
        return '<div class="empty">指数K线数据为空</div>'

    # 折线图：收盘价
    line_series = []
    for name, rows in kline_data.items():
        if not rows: continue
        closes = [r["close"] for r in rows]
        line_series.append({"name": name, "data": closes, "color": colors.get(name, "#888")})

    line_svg = _svg_line_chart(line_series, all_dates, width=800, height=320, title="近5日收盘价走势", y_label="收盘价")

    # 成交量柱状图
    bar_series = []
    for name, rows in kline_data.items():
        if not rows: continue
        vols = [round(r["volume"] / 1e8, 1) for r in rows]  # 亿
        bar_series.append({"name": name, "data": vols, "color": colors.get(name, "#888")})

    bar_svg = _svg_bar_chart(all_dates, bar_series, width=800, height=220, title="近5日成交量(亿)", grouped=False)

    return f'<div class="chart-group">{line_svg}{bar_svg}</div>'


def chart_sector_fund_5d(daily_rank: dict) -> str:
    """近5日板块资金流向趋势图（行业TOP5净流入柱状图按日分组）"""
    fund_rank = daily_rank.get("fund_rank", [])
    if not fund_rank:
        return '<div class="empty">暂无数据</div>'
    dates = [d["date"] for d in fund_rank]
    all_industries = {}
    for d in fund_rank:
        for s in d.get("top5_in", []):
            name = s.get("name", "")
            if name:
                all_industries[name] = all_industries.get(name, 0) + safe_float(s.get("main_net"))
    top5_industries = sorted(all_industries.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_names = [x[0] for x in top5_industries]

    palette = ["#ff4d4f", "#52c41a", "#1890ff", "#faad14", "#722ed1"]
    series = []
    for i, name in enumerate(top5_names):
        vals = []
        for d in fund_rank:
            found = 0
            for s in d.get("top5_in", []):
                if s.get("name") == name:
                    found = round(safe_float(s.get("main_net")) / 1e8, 2)
                    break
            vals.append(found)
        series.append({"name": name, "data": vals, "color": palette[i % len(palette)]})

    return _svg_bar_chart(dates, series, width=800, height=350, title="近5日行业板块主力净流入TOP5(亿)", y_label="净流入(亿)", grouped=True)


def chart_zt_count_5d(daily_rank: dict) -> str:
    """近5日每日涨停家数趋势"""
    zt_count = daily_rank.get("zt_count", [])
    if not zt_count:
        return '<div class="empty">暂无数据</div>'
    dates = [d["date"] for d in zt_count]
    totals = [d.get("total", 0) for d in zt_count]
    # 根据家数着色
    colors = []
    for t in totals:
        if t < 50: colors.append("#ff4d4f")
        elif t < 100: colors.append("#faad14")
        else: colors.append("#52c41a")
    # 单系列但每根柱子不同颜色 → 用多个series
    series = [{"name": "涨停家数", "data": totals, "color": "#ff4d4f"}]
    return _svg_bar_chart(dates, series, width=800, height=280, title="近5日每日涨停家数", y_label="家数")


# ============ 表格渲染 ============
def render_table(headers: list, rows: list, fixed_first_col: bool = True, extra_class: str = "") -> str:
    """渲染表格：首列固定，横向可滚动"""
    fixed_class = " fixed-col" if fixed_first_col else ""
    th_html = "".join(f'<th class="{"sticky-col" if i==0 and fixed_first_col else ""}">{h}</th>' for i, h in enumerate(headers))
    tr_html = []
    for row in rows:
        tds = ""
        for i, h in enumerate(headers):
            val = row.get(h, "-") if isinstance(row, dict) else row[i] if i < len(row) else "-"
            cls = "sticky-col" if i == 0 and fixed_first_col else ""
            tds += f'<td class="{cls}">{val if isinstance(val,str) else val}</td>'
        tr_html.append(f'<tr>{tds}</tr>')
    return f'''<div class="table-wrap{fixed_class} {extra_class}">
<table class="data-table">
<thead><tr>{th_html}</tr></thead>
<tbody>{"".join(tr_html)}</tbody>
</table>
</div>'''


# ============ 模块渲染 ============
def render_module1_sentiment(data: dict) -> str:
    """模块一：市场情绪（按用户新需求调整）
    ① 三大指数：表格（侧重5日成交量）+ 成交量折线图
    ② 涨跌停：5日涨跌停表格 + 折线图
    ③ 近5日最高连板/几天几板及对应概念：表格 + 下方涨停跌停数截图
    ④ 近5日每日涨停TOP5概念板块 + 今日涨停TOP5概念板块详细数据
    """
    index_rt = data.get("index_realtime", [])
    index_5d = data.get("index_kline_5d", {})
    zt_summary = data.get("zt_summary", {})
    daily_rank = data.get("sector_daily_rank_5d", {})

    # ========== ① 三大指数：5日成交量表格 + 成交量折线图 ==========
    sh_rows = index_5d.get("上证指数", [])
    sz_rows = index_5d.get("深证成指", [])
    cy_rows = index_5d.get("创业板指", [])
    # 实时卡片
    cards = ""
    for idx in index_rt:
        pct_cls = "up" if safe_float(idx.get("pct")) > 0 else "down" if safe_float(idx.get("pct")) < 0 else "flat"
        cards += f'''<div class="idx-card">
<div class="idx-name">{esc(idx.get("name"))}</div>
<div class="idx-close">{esc(idx.get("close"))}</div>
<div class="idx-pct {pct_cls}">{fmt_pct(idx.get("pct"))}</div>
<div class="idx-amt">成交额 {fmt_amt(idx.get("amount"))}</div>
</div>'''

    # 5日表格：日期、上证(收盘/涨幅/成交量)、深证、创业板
    headers = ["日期", "上证收盘", "上证涨幅", "上证成交量", "深证收盘", "深证涨幅", "深证成交量", "创业板收盘", "创业板涨幅", "创业板成交量"]
    rows = []
    max_len = max(len(sh_rows), len(sz_rows), len(cy_rows))
    for i in range(max_len):
        def get_row(rows, i):
            if i >= len(rows): return ("-", "-", "-")
            r = rows[i]
            pct = ((r["close"]/r["open"]-1)*100) if r.get("open") else None
            return (esc(r["close"]), fmt_pct_color(pct), fmt_amt(r.get("volume")))
        sh_c, sh_p, sh_v = get_row(sh_rows, i)
        sz_c, sz_p, sz_v = get_row(sz_rows, i)
        cy_c, cy_p, cy_v = get_row(cy_rows, i)
        date = sh_rows[i]["date"][-5:] if i < len(sh_rows) else (sz_rows[i]["date"][-5:] if i < len(sz_rows) else (cy_rows[i]["date"][-5:] if i < len(cy_rows) else "-"))
        rows.append({
            "日期": date, "上证收盘": sh_c, "上证涨幅": sh_p, "上证成交量": sh_v,
            "深证收盘": sz_c, "深证涨幅": sz_p, "深证成交量": sz_v,
            "创业板收盘": cy_c, "创业板涨幅": cy_p, "创业板成交量": cy_v,
        })
    index_table = render_table(headers, rows)

    # 成交量折线图
    all_dates = [r["date"][-5:] for r in sh_rows] if sh_rows else []
    line_series = []
    colors_map = {"上证指数": "#ff4d4f", "深证成指": "#52c41a", "创业板指": "#1890ff"}
    for name, rows_data in [("上证指数", sh_rows), ("深证成指", sz_rows), ("创业板指", cy_rows)]:
        if rows_data:
            vols = [round(r["volume"] / 1e8, 1) for r in rows_data]
            line_series.append({"name": name, "data": vols, "color": colors_map.get(name, "#888")})
    volume_chart = _svg_line_chart(line_series, all_dates, width=800, height=300, title="近5日三大指数成交量(亿)", y_label="成交量(亿)") if line_series else '<div class="empty">暂无数据</div>'

    # ========== ② 涨跌停：5日表格 + 折线图 ==========
    zt_count_list = daily_rank.get("zt_count", [])
    dt_count_list = daily_rank.get("dt_count", [])
    headers = ["日期", "涨停家数", "跌停家数", "涨跌比"]
    rows = []
    for i in range(len(zt_count_list)):
        zt = zt_count_list[i].get("total", 0)
        dt = dt_count_list[i].get("total", 0) if i < len(dt_count_list) else 0
        ratio = f"{zt/dt:.2f}" if dt > 0 else "∞"
        rows.append({
            "日期": zt_count_list[i].get("date", "-"),
            "涨停家数": f'<span class="up"><b>{zt}</b></span>',
            "跌停家数": f'<span class="down"><b>{dt}</b></span>',
            "涨跌比": ratio,
        })
    zt_dt_table = render_table(headers, rows)

    # 涨跌停折线图
    chart_dates = [d.get("date", "-") for d in zt_count_list]
    zt_totals = [d.get("total", 0) for d in zt_count_list]
    dt_totals = [d.get("total", 0) if i < len(dt_count_list) else 0 for i, d in enumerate(zt_count_list)]
    zt_dt_chart_series = [
        {"name": "涨停家数", "data": zt_totals, "color": "#ff4d4f"},
        {"name": "跌停家数", "data": dt_totals, "color": "#52c41a"},
    ]
    zt_dt_chart = _svg_line_chart(zt_dt_chart_series, chart_dates, width=800, height=300, title="近5日涨停/跌停家数趋势", y_label="家数")

    # ========== ③ 近5日最高连板/几天几板及对应概念 ==========
    max_lb_list = daily_rank.get("max_lb_5d", [])
    max_jtjb_list = daily_rank.get("max_jtjb_5d", [])
    headers = ["日期", "最高连板", "对应个股", "对应概念", "最高几天几板", "对应个股", "对应概念"]
    rows = []
    for i in range(max(len(max_lb_list), len(max_jtjb_list))):
        lb = max_lb_list[i] if i < len(max_lb_list) else {}
        jt = max_jtjb_list[i] if i < len(max_jtjb_list) else {}
        rows.append({
            "日期": lb.get("date", jt.get("date", "-")),
            "最高连板": f'<span class="lb-badge">{lb.get("max_lb", 0)}板</span>',
            "对应个股": esc(lb.get("name", "-")),
            "对应概念": esc(lb.get("concept", "-")),
            "最高几天几板": f'<span class="jtjb-badge">{esc(jt.get("stat", "-"))}</span>',
            "对应个股": esc(jt.get("name", "-")),
            "对应概念": esc(jt.get("concept", "-")),
        })
    lb_jtjb_table = render_table(headers, rows)

    # ========== ④ 近5日每日涨停TOP5概念板块 + 今日涨停TOP5概念详情 ==========
    # 近5日每日涨停TOP5概念
    headers = ["日期", "TOP1", "TOP2", "TOP3", "TOP4", "TOP5"]
    rows = []
    for d in zt_count_list:
        date = d.get("date", "")
        tops = d.get("top", [])
        row = {"日期": date}
        for i in range(5):
            if i < len(tops):
                row[f"TOP{i+1}"] = f'{esc(tops[i][0])}<br><span class="muted">{tops[i][1]}家</span>'
            else:
                row[f"TOP{i+1}"] = "-"
        rows.append(row)
    zt_top5_concept_table = render_table(headers, rows)

    # 今日涨停TOP5概念板块详情
    concept_detail = data.get("concept_detail_today", [])
    headers = ["概念板块", "涨停数", "跌停数", "涨幅", "主力净流入", "上涨家数", "下跌家数"]
    rows = []
    for c in concept_detail:
        rows.append({
            "概念板块": esc(c.get("name")),
            "涨停数": f'<span class="up"><b>{c.get("zt_count", 0)}</b></span>',
            "跌停数": f'<span class="down"><b>{c.get("dt_count", 0)}</b></span>',
            "涨幅": fmt_pct_color(c.get("pct")),
            "主力净流入": fmt_amt_color(c.get("main_net")),
            "上涨家数": f'<span class="up">{esc(c.get("up_count", "-"))}</span>',
            "下跌家数": f'<span class="down">{esc(c.get("down_count", "-"))}</span>',
        })
    concept_detail_table = render_table(headers, rows)

    return f'''<section id="m1" class="module">
<h2 class="module-title"><span class="num">01</span> 市场情绪</h2>
<div class="idx-cards">{cards}</div>
<h3 class="sub-title">① 近5日三大指数情况（侧重量能）</h3>
{index_table}
{volume_chart}
<h3 class="sub-title">② 近5日涨停/跌停家数</h3>
{zt_dt_table}
{zt_dt_chart}
<h3 class="sub-title">③ 近5日最高连板 / 最高几天几板及对应概念</h3>
{lb_jtjb_table}
<h3 class="sub-title">④ 近5日每日涨停TOP5概念板块</h3>
{zt_top5_concept_table}
<h4 class="table-title">今日涨停TOP5概念板块详情</h4>
{concept_detail_table}
</section>'''


def render_module2_sector_today(data: dict) -> str:
    """模块二：当日及近5日板块（按用户新需求合并，去掉行业板块，只留概念板块，不画图）
    ① 今日概念板块净流入TOP5
    ② 今日概念板块净流出TOP5
    ③ 近5日概念板块每日净流入TOP5表格
    ④ 近5日概念板块每日净流出TOP5表格
    """
    concept = data.get("sector_concept_today", [])
    daily_rank = data.get("sector_daily_rank_5d", {})
    fund_rank = daily_rank.get("fund_rank", [])

    # ① 今日概念净流入TOP5
    top5_in = sorted(concept, key=lambda x: safe_float(x.get("main_net")), reverse=True)[:5]
    headers = ["概念板块", "涨跌幅", "主力净流入", "净占比", "超大单", "大单", "中单", "小单", "上涨家数", "下跌家数"]
    rows = [{"概念板块": esc(s.get("name")), "涨跌幅": fmt_pct_color(s.get("pct")),
             "主力净流入": fmt_amt_color(s.get("main_net")), "净占比": fmt_pct(s.get("main_net_pct"), False),
             "超大单": fmt_amt_color(s.get("super_net")), "大单": fmt_amt_color(s.get("big_net")),
             "中单": fmt_amt_color(s.get("mid_net")), "小单": fmt_amt_color(s.get("small_net")),
             "上涨家数": f'<span class="up">{esc(s.get("up_count","-"))}</span>',
             "下跌家数": f'<span class="down">{esc(s.get("down_count","-"))}</span>'} for s in top5_in]
    in_table = render_table(headers, rows)

    # ② 今日概念净流出TOP5
    top5_out = sorted(concept, key=lambda x: safe_float(x.get("main_net")))[:5]
    rows = [{"概念板块": esc(s.get("name")), "涨跌幅": fmt_pct_color(s.get("pct")),
             "主力净流入": fmt_amt_color(s.get("main_net")), "净占比": fmt_pct(s.get("main_net_pct"), False),
             "超大单": fmt_amt_color(s.get("super_net")), "大单": fmt_amt_color(s.get("big_net")),
             "中单": fmt_amt_color(s.get("mid_net")), "小单": fmt_amt_color(s.get("small_net")),
             "上涨家数": f'<span class="up">{esc(s.get("up_count","-"))}</span>',
             "下跌家数": f'<span class="down">{esc(s.get("down_count","-"))}</span>'} for s in top5_out]
    out_table = render_table(headers, rows)

    # ③ 近5日概念板块每日净流入TOP5
    headers = ["日期", "TOP1", "TOP2", "TOP3", "TOP4", "TOP5"]
    rows = []
    for d in fund_rank:
        date = d.get("date", "")
        tops = d.get("top5_in", [])
        row = {"日期": date}
        for i in range(5):
            if i < len(tops):
                row[f"TOP{i+1}"] = f'{esc(tops[i].get("name"))}<br><span class="muted">{fmt_amt(tops[i].get("main_net"))}</span>'
            else:
                row[f"TOP{i+1}"] = "-"
        rows.append(row)
    fund_in_5d_table = render_table(headers, rows)

    # ④ 近5日概念板块每日净流出TOP5
    rows = []
    for d in fund_rank:
        date = d.get("date", "")
        tops = d.get("top5_out", [])
        row = {"日期": date}
        for i in range(5):
            if i < len(tops):
                row[f"TOP{i+1}"] = f'{esc(tops[i].get("name"))}<br><span class="muted">{fmt_amt(tops[i].get("main_net"))}</span>'
            else:
                row[f"TOP{i+1}"] = "-"
        rows.append(row)
    fund_out_5d_table = render_table(headers, rows)

    # 关键信号
    signals = []
    if concept:
        in_total = sum(safe_float(s.get("main_net")) for s in concept if safe_float(s.get("main_net")) > 0)
        out_total = -sum(safe_float(s.get("main_net")) for s in concept if safe_float(s.get("main_net")) < 0)
        signals.append(f"概念板块主力净流入合计 <b>{fmt_amt(in_total - out_total)}</b>（流入 {fmt_amt(in_total)} / 流出 {fmt_amt(out_total)}）")
    if fund_rank:
        today_top = fund_rank[-1].get("top5_in", []) if fund_rank else []
        if today_top:
            signals.append(f"今日概念资金流入TOP1：<b>{esc(today_top[0].get('name'))}</b> {fmt_amt(today_top[0].get('main_net'))}")
        today_out = fund_rank[-1].get("top5_out", []) if fund_rank else []
        if today_out:
            signals.append(f"今日概念资金流出TOP1：<b>{esc(today_out[0].get('name'))}</b> {fmt_amt(today_out[0].get('main_net'))}")
    signals_html = "".join(f'<li class="signal-item">{s}</li>' for s in signals)
    signals_block = f'<div class="signals"><div class="signal-title">🔑 关键信号</div><ul>{signals_html}</ul></div>' if signals else ""

    return f'''<section id="m2" class="module">
<h2 class="module-title"><span class="num">02</span> 当日及近5日板块</h2>
<h3 class="sub-title">① 今日概念板块净流入 TOP5</h3>
{in_table}
<h3 class="sub-title">② 今日概念板块净流出 TOP5</h3>
{out_table}
<h3 class="sub-title">③ 近5日概念板块每日净流入 TOP5</h3>
{fund_in_5d_table}
<h3 class="sub-title">④ 近5日概念板块每日净流出 TOP5</h3>
{fund_out_5d_table}
{signals_block}
</section>'''


def render_module4_individual(data: dict) -> str:
    """模块四：个股资金"""
    today = data.get("individual_fund_today", [])
    fund_5d = data.get("individual_fund_5d_daily", {})
    gain_5d = data.get("stock_gain_5d", [])
    gain_10d = data.get("stock_gain_10d", [])
    gain_20d = data.get("stock_gain_20d", [])

    # ⑧ 近5日个股资金流向每日排名
    today_top5 = fund_5d.get("today_top5", [])[:5]
    summary_5d = fund_5d.get("5d_summary_top5", [])[:5]
    daily_history = fund_5d.get("daily_history", {})

    headers = ["名称", "代码", "今日涨跌幅", "今日主力净流入", "净占比"]
    rows = [{"名称": esc(s.get("name")), "代码": esc(s.get("code")),
             "今日涨跌幅": fmt_pct_color(s.get("pct")),
             "今日主力净流入": fmt_amt_color(s.get("main_net")),
             "净占比": fmt_pct(s.get("main_net_pct"), False)} for s in today_top5]
    today_table = render_table(headers, rows)

    headers = ["名称", "代码", "5日涨跌幅", "5日主力净流入", "净占比"]
    rows = [{"名称": esc(s.get("name")), "代码": esc(s.get("code")),
             "5日涨跌幅": fmt_pct_color(s.get("pct_5d")),
             "5日主力净流入": fmt_amt_color(s.get("main_net_5d")),
             "净占比": fmt_pct(s.get("main_net_pct_5d"), False)} for s in summary_5d]
    summary_table = render_table(headers, rows)

    # 每日历史明细（若datacenter可用）
    daily_html = ""
    if daily_history and any(v for v in daily_history.values()):
        headers = ["日期", "名称", "代码", "主力净流入"]
        rows = []
        for date, items in daily_history.items():
            if not items:
                continue
            for s in items[:5]:
                rows.append({"日期": date, "名称": esc(s.get("SECURITY_NAME") or s.get("name") or "-"),
                             "代码": esc(s.get("SECURITY_CODE") or s.get("code") or "-"),
                             "主力净流入": fmt_amt_color(s.get("NET_INFLOW_MAIN") or s.get("main_net"))})
        if rows:
            daily_html = f'<h3 class="sub-title">⑧ 近5日个股资金流向每日明细</h3>{render_table(headers, rows)}'

    # ⑨ 近10日涨幅前10
    headers = ["排名", "名称", "代码", "最新价", "今日涨跌幅", "10日涨幅"]
    rows = [{"排名": i+1, "名称": esc(s.get("name")), "代码": esc(s.get("code")),
             "最新价": esc(s.get("close")), "今日涨跌幅": fmt_pct_color(s.get("pct_today")),
             "10日涨幅": fmt_pct_color(s.get("pct_ndays"))} for i, s in enumerate(gain_10d)]
    gain10_table = render_table(headers, rows)

    # ⑩ 近20日涨幅前10
    headers = ["排名", "名称", "代码", "最新价", "今日涨跌幅", "20日涨幅"]
    rows = [{"排名": i+1, "名称": esc(s.get("name")), "代码": esc(s.get("code")),
             "最新价": esc(s.get("close")), "今日涨跌幅": fmt_pct_color(s.get("pct_today")),
             "20日涨幅": fmt_pct_color(s.get("pct_ndays"))} for i, s in enumerate(gain_20d)]
    gain20_table = render_table(headers, rows)

    # 5日涨幅前10
    headers = ["排名", "名称", "代码", "最新价", "今日涨跌幅", "5日涨幅"]
    rows = [{"排名": i+1, "名称": esc(s.get("name")), "代码": esc(s.get("code")),
             "最新价": esc(s.get("close")), "今日涨跌幅": fmt_pct_color(s.get("pct_today")),
             "5日涨幅": fmt_pct_color(s.get("pct_ndays"))} for i, s in enumerate(gain_5d)]
    gain5_table = render_table(headers, rows)

    return f'''<section id="m4" class="module">
<h2 class="module-title"><span class="num">03</span> 个股资金</h2>
<h3 class="sub-title">⑧ 近5日个股资金流向排名</h3>
<h4 class="table-title">今日主力净流入 TOP5</h4>
{today_table}
<h4 class="table-title">5日主力净流入 TOP5（汇总）</h4>
{summary_table}
{daily_html}
<h3 class="sub-title">⑨ 近10日涨幅前10</h3>
{gain10_table}
<h3 class="sub-title">⑩ 近20日涨幅前10</h3>
{gain20_table}
<h3 class="sub-title">附：近5日涨幅前10</h3>
{gain5_table}
</section>'''


# ============ 主HTML模板 ============
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股市场情绪日报 · {report_date}</title>
<style>
:root {{
  --bg: #0d1117;
  --bg-card: #161b22;
  --bg-table: #1c2128;
  --border: #30363d;
  --text: #e6edf3;
  --text-muted: #8b949e;
  --up: #f85149;
  --down: #3fb950;
  --flat: #8b949e;
  --accent: #58a6ff;
  --accent2: #bc8cff;
  --zt: #ff4d4f;
  --dt: #52c41a;
  --lb: #faad14;
  --jtjb: #722ed1;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  line-height: 1.6;
  padding: 0;
}}
.header {{
  background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
  border-bottom: 1px solid var(--border);
  padding: 24px 32px;
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(10px);
}}
.header h1 {{
  font-size: 22px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}}
.header .meta {{
  color: var(--text-muted);
  font-size: 12px;
}}
.nav {{
  display: flex;
  gap: 8px;
  margin-top: 16px;
  flex-wrap: wrap;
}}
.nav a {{
  display: inline-block;
  padding: 8px 16px;
  background: var(--bg-card);
  color: var(--accent);
  text-decoration: none;
  border-radius: 6px;
  font-size: 13px;
  border: 1px solid var(--border);
  transition: all 0.2s;
}}
.nav a:hover {{
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}}
.nav a .nav-num {{
  display: inline-block;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  background: rgba(88,166,255,0.2);
  border-radius: 4px;
  margin-right: 6px;
  font-size: 11px;
}}
.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 32px;
}}
.module {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 24px;
}}
.module-title {{
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--accent);
  display: flex;
  align-items: center;
  gap: 12px;
}}
.module-title .num {{
  display: inline-block;
  background: var(--accent);
  color: #fff;
  width: 36px;
  height: 36px;
  line-height: 36px;
  text-align: center;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 700;
}}
.sub-title {{
  font-size: 16px;
  font-weight: 600;
  margin: 24px 0 12px;
  color: var(--accent2);
  padding-left: 10px;
  border-left: 3px solid var(--accent2);
}}
.table-title {{
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: var(--text);
}}
.hint {{
  color: var(--text-muted);
  font-size: 13px;
  margin: 8px 0 12px;
  padding: 8px 12px;
  background: rgba(88,166,255,0.06);
  border-radius: 6px;
}}
.hint b {{ color: var(--accent); }}
.idx-cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}}
.idx-card {{
  background: var(--bg-table);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}}
.idx-name {{ font-size: 13px; color: var(--text-muted); }}
.idx-close {{ font-size: 24px; font-weight: 700; margin: 4px 0; }}
.idx-pct {{ font-size: 16px; font-weight: 600; }}
.idx-pct.up {{ color: var(--up); }}
.idx-pct.down {{ color: var(--down); }}
.idx-pct.flat {{ color: var(--flat); }}
.idx-amt {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
.summary-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin: 16px 0;
}}
.sum-card {{
  background: var(--bg-table);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}}
.sum-card.zt {{ border-left: 4px solid var(--zt); }}
.sum-card.dt {{ border-left: 4px solid var(--dt); }}
.sum-card.lb {{ border-left: 4px solid var(--lb); }}
.sum-card.jtjb {{ border-left: 4px solid var(--jtjb); }}
.sum-val {{ font-size: 22px; font-weight: 700; color: var(--text); }}
.sum-card.zt .sum-val {{ color: var(--zt); }}
.sum-card.dt .sum-val {{ color: var(--dt); }}
.sum-card.lb .sum-val {{ color: var(--lb); }}
.sum-card.jtjb .sum-val {{ color: var(--jtjb); }}
.sum-label {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
.sum-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 6px; }}
.up {{ color: var(--up); }}
.down {{ color: var(--down); }}
.flat {{ color: var(--flat); }}
.muted {{ color: var(--text-muted); font-size: 12px; }}
.lb-badge {{
  display: inline-block;
  background: var(--lb);
  color: #000;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 12px;
}}
.jtjb-badge {{
  display: inline-block;
  background: var(--jtjb);
  color: #fff;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 12px;
}}
.zt-num {{ color: var(--zt); font-size: 18px; }}
.table-wrap {{
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 16px;
  background: var(--bg-table);
}}
.data-table {{
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
  white-space: nowrap;
}}
.data-table th, .data-table td {{
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border);
}}
.data-table th {{
  background: #21262d;
  color: var(--accent);
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}}
.data-table th.sticky-col, .data-table td.sticky-col {{
  position: sticky;
  left: 0;
  background: var(--bg-table);
  z-index: 3;
  min-width: 100px;
}}
.data-table th.sticky-col {{
  background: #21262d;
  z-index: 4;
}}
.data-table tbody tr:hover {{
  background: rgba(88,166,255,0.05);
}}
.data-table tbody tr:hover td.sticky-col {{
  background: rgba(88,166,255,0.08);
}}
.signals {{
  background: rgba(252,184,31,0.06);
  border: 1px solid rgba(252,184,31,0.3);
  border-radius: 8px;
  padding: 16px;
  margin: 12px 0;
}}
.signal-title {{ color: var(--lb); font-weight: 600; margin-bottom: 8px; }}
.signal-item {{
  font-size: 13px;
  padding: 4px 0;
  list-style: none;
  padding-left: 16px;
  position: relative;
}}
.signal-item::before {{
  content: "▸";
  position: absolute;
  left: 0;
  color: var(--lb);
}}
.empty {{ color: var(--text-muted); padding: 20px; text-align: center; }}
.chart-container {{ margin: 16px 0; }}
.chart-group {{ display: flex; flex-direction: column; gap: 12px; }}
.chart-container svg {{ max-width: 100%; height: auto; }}
.footer {{
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 24px;
  border-top: 1px solid var(--border);
  margin-top: 24px;
}}
.footer a {{ color: var(--accent); text-decoration: none; }}
@media (max-width: 768px) {{
  .container {{ padding: 16px; }}
  .header {{ padding: 16px; }}
  .module {{ padding: 16px; }}
}}
</style>
</head>
<body>
<div class="header">
<h1>📊 A股市场情绪日报</h1>
<div class="meta">报告日期：{report_date} · 采集时间：{collect_time} · 数据源：东方财富 / 新浪财经</div>
<nav class="nav">
<a href="#m1"><span class="nav-num">01</span>市场情绪</a>
<a href="#m2"><span class="nav-num">02</span>当日及近5日板块</a>
<a href="#m3"><span class="nav-num">03</span>个股资金</a>
</nav>
</div>
<div class="container">
{module1}
{module2}
{module3}
</div>
<div class="footer">
<p>本报告由 WorkBuddy 自动生成 · 仅供投资参考，不构成投资建议</p>
<p>数据源：东方财富 push2delay / datacenter-web · 新浪财经 · 生成时间 {gen_time}</p>
</div>
</body>
</html>'''


def render_html(data: dict) -> str:
    """主渲染函数"""
    meta = data.get("_meta", {})
    report_date = meta.get("trade_date", "")
    if report_date and len(report_date) == 8:
        report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"
    collect_time = meta.get("collect_time", "")
    gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    m1 = render_module1_sentiment(data)
    m2 = render_module2_sector_today(data)
    m3 = render_module4_individual(data)

    return HTML_TEMPLATE.format(
        report_date=report_date,
        collect_time=collect_time,
        gen_time=gen_time,
        module1=m1, module2=m2, module3=m3, module4="",
    )


if __name__ == "__main__":
    data_file = sys.argv[1] if len(sys.argv) > 1 else "/workspace/fin_daily/data.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "/workspace/fin_daily/report.html"
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    html_str = render_html(data)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_str)
    print(f"[OK] HTML报告已生成: {out_file} ({len(html_str)} 字符)")
