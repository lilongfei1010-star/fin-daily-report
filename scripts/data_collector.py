#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪日报 - 数据采集模块
数据源：
  - 东方财富 push2delay.eastmoney.com（板块/个股资金流、A股行情，15秒延迟）
  - 东方财富 datacenter-web（涨停/跌停池）
  - 新浪财经（指数历史K线）
作者: WorkBuddy  生成时间: 2026-07-19
"""
import os, sys, json, time, datetime, traceback, warnings
from typing import Any
warnings.filterwarnings("ignore")

import requests
import akshare as ak

UT = "8dec03ba335b81bf4ebdf7b29ec27d15"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
    "Accept": "*/*",
}
PUSH2_DELAY = "https://push2delay.eastmoney.com/api/qt/clist/get"
PUSH2_ULIST = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
PUSH2_KLINE = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _retry(fn, attempts=3, delay=1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(delay * (i + 1))
    raise last


def _get_json(url, params, timeout=20):
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ============ 工具函数 ============
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


def fmt_pct(v) -> str:
    if v is None or v == "-" or v == "":
        return "-"
    try:
        return f"{float(v):+.2f}%"
    except (TypeError, ValueError):
        return str(v)


def fmt_num(v) -> str:
    if v is None or v == "-" or v == "":
        return "-"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def trade_date_str(d: datetime.date) -> str:
    return d.strftime("%Y%m%d")


def latest_trade_date() -> datetime.date:
    """推断最近一个交易日。
    规则：
      - 周六/周日 → 上周五
      - 工作日且当前时间 < 15:30 → 昨天（若昨天非周末）否则前一个交易日
      - 工作日且当前时间 >= 15:30 → 今天
    """
    now = datetime.datetime.now()
    today = now.date()
    if today.weekday() == 5:  # 周六
        return today - datetime.timedelta(days=1)
    elif today.weekday() == 6:  # 周日
        return today - datetime.timedelta(days=2)
    # 工作日
    if now.hour >= 16:  # 收盘后（16点确保数据齐全）
        return today
    # 盘中或盘前：用上一个交易日
    d = today - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d


def last_n_trade_dates(n: int, end_date: datetime.date = None) -> list:
    """获取最近n个交易日（粗略：排除周末）"""
    if end_date is None:
        end_date = latest_trade_date()
    dates = []
    d = end_date
    while len(dates) < n:
        if d.weekday() < 5:  # 周一到周五
            dates.append(d)
        d -= datetime.timedelta(days=1)
    return list(reversed(dates))


# ============ 模块一：市场情绪 ============

def fetch_index_realtime() -> list:
    """三大指数实时行情"""
    data = _get_json(PUSH2_ULIST, {
        "fltt": 2, "ut": UT,
        "fields": "f2,f3,f4,f5,f6,f12,f14",
        "secids": "1.000001,0.399001,0.399006",
    })
    items = data.get("data", {}).get("diff", []) or []
    result = []
    for it in items:
        result.append({
            "code": it.get("f12"),
            "name": it.get("f14"),
            "close": it.get("f2"),
            "pct": it.get("f3"),
            "change": it.get("f4"),
            "volume": it.get("f5"),
            "amount": it.get("f6"),
        })
    return result


def fetch_index_kline_5d() -> dict:
    """三大指数近5日K线（新浪源）"""
    result = {}
    sym_map = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]
    for sym, name in sym_map:
        try:
            df = _retry(lambda s=sym: ak.stock_zh_index_daily(symbol=s).tail(5))
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "date": str(r["date"]),
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "volume": float(r["volume"]),
                })
            result[name] = rows
        except Exception as e:
            print(f"[WARN] 指数K线 {name} 失败: {e}", file=sys.stderr)
            result[name] = []
    return result


def fetch_zt_pool(date_str: str) -> list:
    """涨停股池"""
    try:
        df = _retry(lambda d=date_str: ak.stock_zt_pool_em(date=d))
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "code": str(r.get("代码", "")),
                "name": str(r.get("名称", "")),
                "pct": r.get("涨跌幅"),
                "amount": r.get("成交额"),
                "lb_count": r.get("连板数", 1),  # 连板数
                "zt_stat": str(r.get("涨停统计", "")),  # 几天几板，如"4/3"
                "industry": str(r.get("所属行业", "")),
                "fb_money": r.get("封板资金"),
                "first_fb_time": str(r.get("首次封板时间", "")),
                "last_fb_time": str(r.get("最后封板时间", "")),
                "break_count": r.get("炸板次数", 0),
                "turnover": r.get("换手率"),
            })
        return rows
    except Exception as e:
        print(f"[WARN] 涨停池 {date_str} 失败: {e}", file=sys.stderr)
        return []


def fetch_dt_pool(date_str: str) -> list:
    """跌停股池"""
    try:
        df = _retry(lambda d=date_str: ak.stock_zt_pool_dtgc_em(date=d))
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "code": str(r.get("代码", "")),
                "name": str(r.get("名称", "")),
                "pct": r.get("涨跌幅"),
                "amount": r.get("成交额"),
                "industry": str(r.get("所属行业", "")),
                "fb_money": r.get("封板资金"),
            })
        return rows
    except Exception as e:
        print(f"[WARN] 跌停池 {date_str} 失败: {e}", file=sys.stderr)
        return []


def compute_zt_summary(zt_list: list) -> dict:
    """从涨停池计算涨停统计：最高连板、最高几天几板及对应概念"""
    if not zt_list:
        return {"zt_count": 0, "max_lb": 0, "max_lb_concept": "-", "max_jtjb": "-", "max_jtjb_concept": "-"}
    # 最高连板
    max_lb_item = max(zt_list, key=lambda x: float(x.get("lb_count") or 1))
    max_lb = int(max_lb_item.get("lb_count") or 1)
    max_lb_concept = max_lb_item.get("industry", "-")
    max_lb_name = max_lb_item.get("name", "-")
    # 最高几天几板：从涨停统计"X/Y"中取X最大
    def parse_jtjb(stat: str):
        if not stat or "/" not in stat:
            return 0
        try:
            return int(stat.split("/")[0])
        except (ValueError, IndexError):
            return 0
    max_jtjb_item = max(zt_list, key=lambda x: parse_jtjb(x.get("zt_stat", "")))
    max_jtjb_val = parse_jtjb(max_jtjb_item.get("zt_stat", ""))
    max_jtjb_concept = max_jtjb_item.get("industry", "-")
    max_jtjb_name = max_jtjb_item.get("name", "-")
    max_jtjb_stat = max_jtjb_item.get("zt_stat", "-")
    return {
        "zt_count": len(zt_list),
        "max_lb": max_lb,
        "max_lb_name": max_lb_name,
        "max_lb_concept": max_lb_concept,
        "max_jtjb_val": max_jtjb_val,
        "max_jtjb_name": max_jtjb_name,
        "max_jtjb_stat": max_jtjb_stat,
        "max_jtjb_concept": max_jtjb_concept,
    }


# ============ 模块二：当日板块资金流 ============

def fetch_sector_fund_today(sector_type="行业") -> list:
    """板块资金流-今日 sector_type: '行业' or '概念'"""
    fs_map = {"行业": "m:90 t:2 f:!50", "概念": "m:90 t:3 f:!50"}
    fs = fs_map.get(sector_type, fs_map["行业"])
    data = _get_json(PUSH2_DELAY, {
        "pn": 1, "pz": 200, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f62",
        "fs": fs, "ut": UT,
        "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f104,f105",
    })
    items = data.get("data", {}).get("diff", []) or []
    result = []
    for it in items:
        result.append({
            "code": it.get("f12"),
            "name": it.get("f14"),
            "close": it.get("f2"),
            "pct": it.get("f3"),
            "main_net": it.get("f62"),
            "main_net_pct": it.get("f184"),
            "super_net": it.get("f66"),
            "big_net": it.get("f72"),
            "mid_net": it.get("f78"),
            "small_net": it.get("f84"),
            "up_count": it.get("f104"),   # 上涨家数
            "down_count": it.get("f105"),  # 下跌家数
        })
    return result


def fetch_sector_fund_5day(sector_type="行业") -> list:
    """板块资金流-5日排名"""
    fs_map = {"行业": "m:90 t:2 f:!50", "概念": "m:90 t:3 f:!50"}
    fs = fs_map.get(sector_type, fs_map["行业"])
    data = _get_json(PUSH2_DELAY, {
        "pn": 1, "pz": 200, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f164",
        "fs": fs, "stat": "5", "ut": UT,
        "fields": "f12,f14,f3,f109,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173",
    })
    items = data.get("data", {}).get("diff", []) or []
    result = []
    for it in items:
        result.append({
            "code": it.get("f12"),
            "name": it.get("f14"),
            "pct": it.get("f3"),  # 5日涨跌幅
            "main_net_5d": it.get("f164"),
            "main_net_pct_5d": it.get("f165"),
        })
    return result


def fetch_sector_fund_by_day(days: int = 5) -> dict:
    """获取近N日每日板块资金流（用于趋势追踪图）。
    push2delay 的 stat 参数支持 1/5/10 汇总，但无法直接给"每日明细"。
    改为：对最近N个交易日分别用 stat=1 取当日净流入前N板块做趋势。
    但 stat=1 也只给当日值。所以这里换思路：用近5日汇总的 f164(净流入) + f165(占比) 做截面排名；
    逐日追踪用"5日榜" + "今日榜" + "10日榜" 三个截面来组合呈现。
    实际逐日历史明细可通过 datacenter-web 的 RPT_BOARD_FUND_FLOW_HISTORY 接口获取，这里先尝试。
    """
    # 尝试 datacenter-web 历史资金流接口
    result = {}
    try:
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        # 拉取最近N天的板块资金流历史
        end_date = latest_trade_date()
        dates = last_n_trade_dates(days, end_date)
        for d in dates:
            d_str = d.strftime("%Y-%m-%d")
            # 行业
            params = {
                "reportName": "RPT_BOARD_FUNDRANKING",
                "columns": "ALL",
                "source": "WEB",
                "client": "WEB",
                "sortColumns": "NET_INFLOW",
                "sortTypes": "-1",
                "pageSize": 20,
                "pageNumber": 1,
                "filter": f"(TRADE_DATE='{d_str}')(SECURITY_TYPE_CODE='901002')",
            }
            try:
                data = _get_json(url, params)
                if data.get("success") and data.get("result"):
                    rows = data["result"]
                    if isinstance(rows, dict):
                        rows = rows.get("data", [])
                    result.setdefault("行业", {})[d_str] = rows
                    continue
            except Exception:
                pass
            result.setdefault("行业", {})[d_str] = None
    except Exception as e:
        print(f"[WARN] 板块资金历史接口失败: {e}", file=sys.stderr)
    return result


# ============ 模块三：板块每日排名 ============

def fetch_sector_daily_rank_5d() -> dict:
    """近5日板块每日排名：概念资金流向/概念涨跌幅/涨停家数/最高连板几天几板
    （已按用户新需求调整：只关注概念板块，不含行业板块）
    """
    dates = last_n_trade_dates(5)
    result = {
        "dates": [d.strftime("%m-%d") for d in dates],
        "fund_rank": [],        # 每日概念资金流TOP5流入/流出
        "pct_rank": [],         # 每日概念涨幅TOP5
        "zt_count": [],         # 每日涨停家数+TOP5概念板块
        "dt_count": [],         # 每日跌停家数
        "max_lb_5d": [],        # 每日最高连板及对应概念
        "max_jtjb_5d": [],      # 每日最高几天几板及对应概念
    }
    for d in dates:
        d_str = d.strftime("%Y%m%d")
        # 当日概念板块资金流
        try:
            fund = fetch_sector_fund_today("概念")
            top5_in = sorted(fund, key=lambda x: float(x.get("main_net") or 0), reverse=True)[:5]
            top5_out = sorted(fund, key=lambda x: float(x.get("main_net") or 0))[:5]
            result["fund_rank"].append({"date": d.strftime("%m-%d"), "top5_in": top5_in, "top5_out": top5_out})
        except Exception as e:
            print(f"[WARN] 概念资金日排名 {d_str} 失败: {e}", file=sys.stderr)
            result["fund_rank"].append({"date": d.strftime("%m-%d"), "top5_in": [], "top5_out": []})
        # 当日概念涨幅TOP5
        try:
            data = _get_json(PUSH2_DELAY, {
                "pn": 1, "pz": 5, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": "m:90 t:3 f:!50", "ut": UT,
                "fields": "f12,f14,f3,f62",
            })
            items = data.get("data", {}).get("diff", []) or []
            result["pct_rank"].append({"date": d.strftime("%m-%d"), "top": [
                {"name": it.get("f14"), "pct": it.get("f3"), "main_net": it.get("f62")} for it in items
            ]})
        except Exception as e:
            print(f"[WARN] 概念涨幅排名 {d_str} 失败: {e}", file=sys.stderr)
            result["pct_rank"].append({"date": d.strftime("%m-%d"), "top": []})
        # 当日涨停池（用于计算涨停家数、最高连板、几天几板、TOP5概念板块）
        try:
            zt = fetch_zt_pool(d_str)
            dt = fetch_dt_pool(d_str)
            industry_count = {}
            for s in zt:
                ind = s.get("industry", "未分类") or "未分类"
                industry_count[ind] = industry_count.get(ind, 0) + 1
            top5 = sorted(industry_count.items(), key=lambda x: x[1], reverse=True)[:5]
            result["zt_count"].append({"date": d.strftime("%m-%d"), "top": top5, "total": len(zt)})
            result["dt_count"].append({"date": d.strftime("%m-%d"), "total": len(dt)})
            # 当日最高连板
            if zt:
                max_lb_item = max(zt, key=lambda x: int(x.get("lb_count") or 1))
                result["max_lb_5d"].append({
                    "date": d.strftime("%m-%d"),
                    "max_lb": int(max_lb_item.get("lb_count") or 1),
                    "name": max_lb_item.get("name", "-"),
                    "concept": max_lb_item.get("industry", "-"),
                })
                # 当日最高几天几板
                def parse_jtjb(stat):
                    if not stat or "/" not in stat:
                        return 0
                    try: return int(stat.split("/")[0])
                    except: return 0
                max_jtjb_item = max(zt, key=lambda x: parse_jtjb(x.get("zt_stat", "")))
                result["max_jtjb_5d"].append({
                    "date": d.strftime("%m-%d"),
                    "stat": max_jtjb_item.get("zt_stat", "-"),
                    "jtjb_val": parse_jtjb(max_jtjb_item.get("zt_stat", "")),
                    "name": max_jtjb_item.get("name", "-"),
                    "concept": max_jtjb_item.get("industry", "-"),
                })
            else:
                result["max_lb_5d"].append({"date": d.strftime("%m-%d"), "max_lb": 0, "name": "-", "concept": "-"})
                result["max_jtjb_5d"].append({"date": d.strftime("%m-%d"), "stat": "-", "jtjb_val": 0, "name": "-", "concept": "-"})
        except Exception as e:
            print(f"[WARN] 涨停数据 {d_str} 失败: {e}", file=sys.stderr)
            result["zt_count"].append({"date": d.strftime("%m-%d"), "top": [], "total": 0})
            result["dt_count"].append({"date": d.strftime("%m-%d"), "total": 0})
            result["max_lb_5d"].append({"date": d.strftime("%m-%d"), "max_lb": 0, "name": "-", "concept": "-"})
            result["max_jtjb_5d"].append({"date": d.strftime("%m-%d"), "stat": "-", "jtjb_val": 0, "name": "-", "concept": "-"})
        time.sleep(0.4)  # 限流
    return result


def fetch_concept_detail_today(top_concepts: list) -> list:
    """获取今日涨停TOP5概念（实际是行业）板块的详细数据（涨停数/跌停数/涨幅/上涨家数/下跌家数）
    top_concepts: [{"name": "电力", "zt_count": 9}, ...] 来自今日涨停池按industry统计
    注意：涨停池的industry字段是东财"行业"分类，所以这里用行业板块行情来匹配
    """
    if not top_concepts:
        return []
    # 取所有行业板块实时行情（含涨跌家数）
    try:
        all_industries = fetch_sector_fund_today("行业")
    except Exception as e:
        print(f"[WARN] 行业板块详情获取失败: {e}", file=sys.stderr)
        return []

    # 取今日跌停池，按行业统计跌停数
    td = latest_trade_date()
    td_str = trade_date_str(td)
    try:
        dt_pool = fetch_dt_pool(td_str)
    except Exception:
        dt_pool = []

    dt_count_by_industry = {}
    for s in dt_pool:
        ind = s.get("industry", "未分类") or "未分类"
        dt_count_by_industry[ind] = dt_count_by_industry.get(ind, 0) + 1

    result = []
    for tc in top_concepts[:5]:
        name = tc.get("name", "")
        zt_cnt = tc.get("zt_count", 0) or tc.get("count", 0)
        dt_cnt = dt_count_by_industry.get(name, 0)
        # 在行业板块中精确匹配，匹配不到则模糊匹配
        matched = None
        for c in all_industries:
            if c.get("name") == name:
                matched = c
                break
        if not matched:
            # 模糊匹配：截断名匹配（东货行业名常被截断为4字，如"汽车零部"=汽车零部件）
            for c in all_industries:
                cname = c.get("name", "")
                if name in cname or cname in name:
                    matched = c
                    break
        if not matched and len(name) >= 2:
            # 进一步模糊：用前2字匹配
            prefix = name[:2]
            for c in all_industries:
                cname = c.get("name", "")
                if cname.startswith(prefix):
                    matched = c
                    break
        if matched:
            result.append({
                "name": name,
                "zt_count": zt_cnt,
                "dt_count": dt_cnt,
                "pct": matched.get("pct", 0),
                "main_net": matched.get("main_net", 0),
                "up_count": matched.get("up_count", "-"),
                "down_count": matched.get("down_count", "-"),
            })
        else:
            result.append({
                "name": name,
                "zt_count": zt_cnt,
                "dt_count": dt_cnt,
                "pct": "-",
                "main_net": "-",
                "up_count": "-",
                "down_count": "-",
            })
    return result


def fetch_concept_up_down_count(concept_codes: list) -> dict:
    """获取概念板块的上涨/下跌家数（push2delay的f104/f105字段）
    concept_codes: ["BK0428", ...]
    """
    if not concept_codes:
        return {}
    result = {}
    # 用clist批量查询
    secids = ",".join(f"90.{code}" for code in concept_codes)
    try:
        data = _get_json(PUSH2_ULIST, {
            "fltt": 2, "ut": UT,
            "fields": "f12,f14,f104,f105,f3",
            "secids": secids,
        })
        items = data.get("data", {}).get("diff", []) or []
        for it in items:
            result[it.get("f12")] = {
                "name": it.get("f14"),
                "up_count": it.get("f104"),   # 上涨家数
                "down_count": it.get("f105"),  # 下跌家数
                "pct": it.get("f3"),
            }
    except Exception as e:
        print(f"[WARN] 概念涨跌家数获取失败: {e}", file=sys.stderr)
    return result


# ============ 模块四：个股资金 ============

def fetch_individual_fund_today() -> list:
    """个股资金流-今日排名"""
    data = _get_json(PUSH2_DELAY, {
        "pn": 1, "pz": 50, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f62",
        "fs": "m:0 t:6 f:!2,m:0 t:13 f:!2,m:0 t:80 f:!2,m:1 t:2 f:!2,m:1 t:23 f:!2",
        "ut": UT,
        "fields": "f2,f3,f12,f14,f62,f184,f175,f263,f160",
    })
    items = data.get("data", {}).get("diff", []) or []
    result = []
    for it in items:
        result.append({
            "code": str(it.get("f12")),
            "name": it.get("f14"),
            "close": it.get("f2"),
            "pct": it.get("f3"),
            "main_net": it.get("f62"),
            "main_net_pct": it.get("f184"),
            "pct_5d": it.get("f175"),
            "pct_10d": it.get("f263"),
        })
    return result


def fetch_individual_fund_5d_daily() -> dict:
    """近5日个股资金流向每日排名（每日TOP5主力净流入）
    push2delay 只给当日实时，无法回溯每日历史。
    改为：返回5日汇总排名 + 当日排名，作为"近5日个股资金追踪"。
    同时尝试 datacenter-web 历史接口，若可用则填充每日明细。
    """
    result = {"today_top5": [], "5d_summary_top5": [], "daily_history": {}}

    # 当日TOP5
    try:
        today = fetch_individual_fund_today()[:5]
        result["today_top5"] = today
    except Exception as e:
        print(f"[WARN] 个股资金当日TOP5 失败: {e}", file=sys.stderr)

    # 5日汇总TOP5（stat=5, fid=f164 主力净流入5日）
    try:
        data = _get_json(PUSH2_DELAY, {
            "pn": 1, "pz": 5, "po": 1, "np": 1,
            "fltt": 2, "invt": 2, "fid": "f164",
            "fs": "m:0 t:6 f:!2,m:0 t:13 f:!2,m:0 t:80 f:!2,m:1 t:2 f:!2,m:1 t:23 f:!2",
            "stat": "5", "ut": UT,
            "fields": "f2,f3,f12,f14,f109,f164,f165",
        })
        items = data.get("data", {}).get("diff", []) or []
        result["5d_summary_top5"] = [{
            "code": str(it.get("f12")),
            "name": it.get("f14"),
            "close": it.get("f2"),
            "pct_5d": it.get("f109"),
            "main_net_5d": it.get("f164"),
            "main_net_pct_5d": it.get("f165"),
        } for it in items]
    except Exception as e:
        print(f"[WARN] 个股资金5日汇总 失败: {e}", file=sys.stderr)

    # 尝试 datacenter-web 每日历史（若报表名正确则填充）
    dates = last_n_trade_dates(5)
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        d_short = d.strftime("%m-%d")
        # 尝试多个可能的报表名
        for rpt in ["RPT_STOCK_FUNDFLOW_RANK", "RPT_INDIVIDUAL_FUND_FLOW"]:
            params = {
                "reportName": rpt, "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "sortColumns": "NET_INFLOW_MAIN", "sortTypes": "-1",
                "pageSize": 5, "pageNumber": 1,
                "filter": f"(TRADE_DATE='{d_str}')",
            }
            try:
                data = _get_json(url, params)
                if data.get("success") and data.get("result"):
                    rows = data["result"]
                    if isinstance(rows, dict):
                        rows = rows.get("data", [])
                    result["daily_history"][d_short] = rows
                    break
            except Exception:
                continue
        else:
            result["daily_history"][d_short] = None
        time.sleep(0.2)
    return result


def _stock_gain_rank_via_push2delay(stat: str, sort_fid: str, gain_fid: str) -> list:
    """通用：用 push2delay 取N日涨幅排名
    stat='1'(默认,20日涨幅用f160) / '5'(5日涨幅用f175) / '10'(10日涨幅用f160)
    sort_fid: 排序字段（与gain_fid相同）  gain_fid: 涨幅字段
    """
    params = {
        "pn": 1, "pz": 30, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": sort_fid,  # 用 fid 排序（非 fid0）
        "fs": "m:0 t:6 f:!2,m:0 t:13 f:!2,m:0 t:80 f:!2,m:1 t:2 f:!2,m:1 t:23 f:!2",
        "ut": UT,
        "fields": f"f2,f3,f12,f14,{gain_fid}",
    }
    if stat and stat != "1":
        params["stat"] = stat
    data = _get_json(PUSH2_DELAY, params)
    items = data.get("data", {}).get("diff", []) or []
    return [{
        "code": str(it.get("f12")),
        "name": it.get("f14"),
        "close": it.get("f2"),
        "pct_today": it.get("f3"),
        "pct_ndays": it.get(gain_fid),
    } for it in items]


def _verify_gain_via_sina(candidates: list, days: int) -> list:
    """用新浪源验证候选股的真实N日涨幅，返回排序后的TOP10"""
    verified = []
    for c in candidates[:30]:
        code = c["code"]
        if not code:
            continue
        prefix = "sh" if code.startswith("6") else ("sz" if code.startswith(("0", "3")) else "bj")
        sym = prefix + code
        try:
            end_date = latest_trade_date()
            start_date = end_date - datetime.timedelta(days=days * 2 + 10)
            df = _retry(lambda s=sym, sd=start_date, ed=end_date: ak.stock_zh_a_daily(
                symbol=s, start_date=sd.strftime("%Y%m%d"), end_date=ed.strftime("%Y%m%d"), adjust="qfq"))
            if len(df) < days + 1:
                continue
            close_now = float(df.iloc[-1]["close"])
            close_ago = float(df.iloc[-(days + 1)]["close"])
            real_gain = (close_now / close_ago - 1) * 100
            verified.append({
                "code": code,
                "name": c["name"],
                "close": close_now,
                "pct_today": c.get("pct_today"),
                "pct_ndays": round(real_gain, 2),
            })
        except Exception as e:
            # 回退使用push2delay的值
            verified.append({
                "code": code,
                "name": c["name"],
                "close": c.get("close"),
                "pct_today": c.get("pct_today"),
                "pct_ndays": c.get("pct_ndays"),
            })
        time.sleep(0.15)
    # 按真实涨幅降序取前10
    verified.sort(key=lambda x: float(x.get("pct_ndays") or 0), reverse=True)
    return verified[:10]


def fetch_stock_gain_rank(days: int) -> list:
    """近N日涨幅前10（5日/10日/20日）
    策略：push2delay 取候选TOP30 → 新浪源验证真实涨幅 → 取前10
    """
    # 字段映射：
    #   5日: stat=5, gain_fid=f175, sort_fid=f175
    #   10日: stat=10, gain_fid=f160, sort_fid=f160
    #   20日: stat=1(默认), gain_fid=f160, sort_fid=f160  (默认stat下f160是20日涨幅)
    if days == 5:
        candidates = _stock_gain_rank_via_push2delay("5", "f175", "f175")
    elif days == 10:
        candidates = _stock_gain_rank_via_push2delay("10", "f160", "f160")
    elif days == 20:
        candidates = _stock_gain_rank_via_push2delay("1", "f160", "f160")
    else:
        candidates = _stock_gain_rank_via_push2delay("5", "f175", "f175")
    return _verify_gain_via_sina(candidates, days)


# ============ 主采集函数 ============

def collect_all_data() -> dict:
    """采集全部四大模块数据，返回dict"""
    print(f"[INFO] 开始采集数据，时间: {datetime.datetime.now()}", file=sys.stderr)
    t0 = time.time()
    data = {"_meta": {"collect_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}

    # 推断最近交易日
    td = latest_trade_date()
    td_str = trade_date_str(td)
    data["_meta"]["trade_date"] = td_str
    print(f"[INFO] 最近交易日: {td_str}", file=sys.stderr)

    # 模块一：市场情绪
    print("[INFO] 模块一：市场情绪", file=sys.stderr)
    data["index_realtime"] = fetch_index_realtime()
    data["index_kline_5d"] = fetch_index_kline_5d()
    data["zt_pool"] = fetch_zt_pool(td_str)
    data["dt_pool"] = fetch_dt_pool(td_str)
    data["zt_summary"] = compute_zt_summary(data["zt_pool"])

    # 模块二：当日及近5日板块（合并原模块二+三，去掉行业板块，只留概念板块）
    print("[INFO] 模块二：当日及近5日板块", file=sys.stderr)
    data["sector_concept_today"] = fetch_sector_fund_today("概念")
    data["sector_industry_today"] = fetch_sector_fund_today("行业")  # 用于涨停TOP5概念详情匹配
    data["sector_concept_5d"] = fetch_sector_fund_5day("概念")
    data["sector_daily_rank_5d"] = fetch_sector_daily_rank_5d()

    # 今日涨停TOP5概念板块的详细数据
    today_zt_top5 = []
    if data["sector_daily_rank_5d"].get("zt_count"):
        today_zt = data["sector_daily_rank_5d"]["zt_count"][-1]  # 最后一天是今天
        today_zt_top5 = [{"name": ind, "zt_count": cnt} for ind, cnt in today_zt.get("top", [])]
    data["concept_detail_today"] = fetch_concept_detail_today(today_zt_top5)

    # 模块三：个股资金
    print("[INFO] 模块三：个股资金", file=sys.stderr)
    data["individual_fund_today"] = fetch_individual_fund_today()
    data["individual_fund_5d_daily"] = fetch_individual_fund_5d_daily()
    data["stock_gain_5d"] = fetch_stock_gain_rank(5)
    data["stock_gain_10d"] = fetch_stock_gain_rank(10)
    data["stock_gain_20d"] = fetch_stock_gain_rank(20)

    print(f"[INFO] 采集完成，耗时 {time.time()-t0:.1f}s", file=sys.stderr)
    return data


if __name__ == "__main__":
    d = collect_all_data()
    out = "/workspace/fin_daily/data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] 数据已保存: {out}")
    # 概览
    print(f"  指数实时: {len(d['index_realtime'])}")
    print(f"  涨停: {len(d['zt_pool'])}, 跌停: {len(d['dt_pool'])}")
    print(f"  概念板块今日: {len(d['sector_concept_today'])}")
    print(f"  今日涨停TOP5概念详情: {len(d.get('concept_detail_today',[]))}")
    print(f"  个股资金流: {len(d['individual_fund_today'])}")
    print(f"  涨幅5日TOP: {len(d['stock_gain_5d'])}")
