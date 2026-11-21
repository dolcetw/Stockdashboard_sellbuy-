"""
每日抓上市櫃個股「主力進出前 15 大買超 / 賣超分點」(富邦 DJ zco 頁，近一日，單位：張)
輸出：
  data/YYYY/broker_top15_YYYYMMDD.csv.gz   當日完整資料
  data/latest.csv.gz                        最新一日 (NAS 固定抓這個)
  data/latest.json                          {"date": "YYYYMMDD", "rows": N, "stocks": N, "file": "..."}
"""
import gzip, io, json, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

URL = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco_{}.djhtm"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
TD = re.compile(r"<TD[^>]*>(.*?)</TD>", re.I | re.S)
BHID = re.compile(r"BHID=([0-9A-Za-z]+)")
DATA = "data"
COLS = ["date", "stock_id", "name", "market", "side", "rank", "broker_id", "broker",
        "buy", "sell", "net", "pct_of_volume"]


# ---------- 股票清單 ----------
def load_stocks():
    """上市 + 上櫃 4 碼普通股 (排除 00 開頭 ETF)。官方 OpenAPI 失敗就用備援清單。"""
    try:
        tw = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
                          headers=HDR, timeout=30).json()
        tp = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
                          headers=HDR, timeout=60).json()
        L = [(r["Code"], r["Name"], "上市") for r in tw]
        L += [(r["SecuritiesCompanyCode"], r["CompanyName"], "上櫃") for r in tp]
        L = [x for x in L if re.fullmatch(r"\d{4}", x[0]) and not x[0].startswith("00")]
        if len(L) > 1500:
            json.dump(L, open("stocks_fallback.json", "w"), ensure_ascii=False)
            return L
    except Exception as e:
        print("stock list fetch failed:", e)
    return json.load(open("stocks_fallback.json"))


# ---------- 解析 ----------
def num(s):
    s = re.sub(r"<[^>]+>", "", s).replace(",", "").replace("%", "").replace("&nbsp;", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse(html, sid):
    m = re.search(r"最後更新日：\s*(\d{4}/\d{2}/\d{2})", html)
    date = m.group(1).replace("/", "") if m else None
    rows, rank = [], {"買超": 0, "賣超": 0}
    for tr in re.findall(r"<TR>(.*?)</tr>", html, re.I | re.S):
        cells = TD.findall(tr)
        if len(cells) != 10:
            continue
        for side, c in (("買超", cells[:5]), ("賣超", cells[5:])):
            name = re.sub(r"<[^>]+>", "", c[0]).replace("&nbsp;", "").strip()
            buy, sell, net, pct = (num(x) for x in c[1:5])
            if not name or name.endswith("券商") or buy is None:
                continue
            b = BHID.search(c[0])
            rank[side] += 1
            rows.append(dict(date=date, stock_id=sid, side=side, rank=rank[side],
                             broker_id=b.group(1) if b else None, broker=name,
                             buy=int(buy), sell=int(sell),
                             net=int(net) if side == "買超" else -int(net),
                             pct_of_volume=pct))
    return date, rows


def fetch(item):
    sid, name, mkt = item
    err = None
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.2, 0.5))
            r = requests.get(URL.format(sid), headers=HDR, timeout=20)
            if r.status_code == 200:
                date, rows = parse(r.content.decode("big5", "ignore"), sid)
                for x in rows:
                    x.update(name=name, market=mkt)
                return sid, date, rows, None
            err = f"HTTP {r.status_code}"
        except Exception as e:
            err = repr(e)
        time.sleep(3 * (attempt + 1))
    return sid, None, [], err


# ---------- 主程式 ----------
def page_date():
    """先看台積電頁的「最後更新日」，判斷今天有沒有新資料。"""
    r = requests.get(URL.format("2330"), headers=HDR, timeout=20)
    d, rows = parse(r.content.decode("big5", "ignore"), "2330")
    return d if rows else None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    d = page_date()
    if not d:
        sys.exit("cannot read page date (site blocked or layout changed)")
    out_file = f"{DATA}/{d[:4]}/broker_top15_{d}.csv.gz"
    if os.path.exists(out_file) and limit is None and os.environ.get("FORCE") != "1":
        print(f"{d} already saved, skip (holiday / weekend / rerun)")
        return

    stocks = load_stocks()[:limit] if limit else load_stocks()
    print(f"date={d} stocks={len(stocks)}", flush=True)
    out, errs, dates = [], {}, {}
    with ThreadPoolExecutor(4) as ex:
        for i, (sid, pd_, rows, err) in enumerate(ex.map(fetch, stocks), 1):
            out += rows
            if err:
                errs[sid] = err
            if pd_:
                dates[pd_] = dates.get(pd_, 0) + 1
            if i % 200 == 0:
                print(i, len(out), len(errs), flush=True)

    df = pd.DataFrame(out, columns=COLS)
    # 防呆：資料中途跨日（網站在跑的途中更新）就只留多數日期
    if len(dates) > 1:
        print("WARNING mixed dates", dates)
    df = df[df.date == d]
    if df.stock_id.nunique() < (len(stocks) * 0.8):
        sys.exit(f"too few stocks scraped ({df.stock_id.nunique()}/{len(stocks)}), abort without saving")

    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    buf = df.to_csv(index=False).encode("utf-8-sig")
    for f in (out_file, f"{DATA}/latest.csv.gz"):
        with gzip.GzipFile(f, "wb", mtime=0) as g:   # mtime=0 讓同內容 gzip 位元相同
            g.write(buf)
    meta = dict(date=d, rows=len(df), stocks=int(df.stock_id.nunique()),
                file=out_file, errors=errs)
    json.dump(meta, open(f"{DATA}/latest.json", "w"), ensure_ascii=False, indent=1)
    print("saved", meta["file"], meta["rows"], "rows", meta["stocks"], "stocks", len(errs), "errors")


if __name__ == "__main__":
    main()
