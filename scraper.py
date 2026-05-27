import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10
BASE_URL = "https://irbank.net"

# 業種 → ディフェンシブ/景気敏感 分類マップ
_SECTOR_TYPE = {
    # ディフェンシブ
    "食料品":         "ディフェンシブ",
    "医薬品":         "ディフェンシブ",
    "電気・ガス業":   "ディフェンシブ",
    "陸運業":         "ディフェンシブ",
    "通信業":         "ディフェンシブ",
    "水産・農林業":   "ディフェンシブ",
    "小売業":         "ディフェンシブ",
    # 景気敏感
    "輸送用機器":     "景気敏感",
    "鉄鋼":           "景気敏感",
    "化学":           "景気敏感",
    "機械":           "景気敏感",
    "電気機器":       "景気敏感",
    "非鉄金属":       "景気敏感",
    "鉱業":           "景気敏感",
    "海運業":         "景気敏感",
    "空運業":         "景気敏感",
    "建設業":         "景気敏感",
    "不動産業":       "景気敏感",
    "繊維製品":       "景気敏感",
    "パルプ・紙":     "景気敏感",
    "ゴム製品":       "景気敏感",
    "窯業・土石製品": "景気敏感",
    # 景気敏感（追加）
    "金属製品":           "景気敏感",
    "ガラス・土石製品":   "景気敏感",
    "石油・石炭製品":     "景気敏感",
    "造船":               "景気敏感",
    # 中間
    "銀行業":             "金融",
    "証券、商品先物取引業": "金融",
    "証券業":             "金融",
    "保険業":             "金融",
    "その他金融業":       "金融",
    "卸売業":             "中間",
    "情報・通信業":       "中間",
    "情報・通信":         "中間",
    "サービス業":         "中間",
    "その他製品":         "中間",
    "精密機器":           "中間",
    "倉庫・運輸関連業":   "中間",
    "医療・福祉":         "ディフェンシブ",
}


def _get(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.encoding = resp.apparent_encoding
        return BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return None


def get_sector(code: str) -> dict:
    """Yahoo Finance profileページから業種分類を取得する。"""
    soup = _get(f"https://finance.yahoo.co.jp/quote/{code}/profile")
    if soup is None:
        return {"sector": "不明", "sector_type": "不明"}

    sector = "不明"
    tags = soup.find_all(True)
    for i, tag in enumerate(tags):
        if tag.get_text(strip=True) == "業種分類" and i + 1 < len(tags):
            sector = tags[i + 1].get_text(strip=True)
            break

    # 完全一致 → 部分一致でフォールバック
    sector_type = _SECTOR_TYPE.get(sector)
    if sector_type is None:
        for key, val in _SECTOR_TYPE.items():
            if key in sector or sector in key:
                sector_type = val
                break
    sector_type = sector_type or "不明"
    return {"sector": sector, "sector_type": sector_type}


def search_code(query: str) -> list[dict]:
    """社名・キーワードから証券コード候補リストを返す。"""
    soup = _get(f"{BASE_URL}/search?query={requests.utils.quote(query)}")
    if soup is None:
        return []

    candidates = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        code = href.strip("/")
        if re.fullmatch(r"\d{4}", code) and code not in seen:
            name = a.get_text(strip=True)
            if name:
                candidates.append({"code": code, "name": name})
                seen.add(code)
    return candidates


def get_company_info(code: str) -> dict:
    """企業名・株価・各種指標を取得する。"""
    soup = _get(f"{BASE_URL}/{code}")
    if soup is None:
        return {"listed": False}

    title = soup.title.get_text(strip=True) if soup.title else ""
    if "NOT FOUND" in title or "404" in title:
        return {"listed": False}

    company_name = "不明"
    if title:
        parts = title.split("|")[0].strip().split()
        if len(parts) >= 2:
            company_name = " ".join(parts[1:])

    stock_price = "不明"
    dividend_yield = "不明"
    per = "不明"
    pbr = "不明"
    roe = "不明"
    eps = "不明"
    bps = "不明"
    equity_ratio = "不明"
    market_cap = "不明"
    dividend_amount = "不明"

    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if "配当利回り" in text and "PER" in text and len(text) < 500:
            m = re.search(r"時価総額([\d兆億,\.]+)", text)
            if m:
                market_cap = m.group(1)
            m = re.search(r"PER（連）予([\d\.\-]+)倍", text)
            if m:
                per = m.group(1) + "倍"
            m = re.search(r"PBR（連）([\d\.\-]+)倍", text)
            if m:
                pbr = m.group(1) + "倍"
            m = re.search(r"配当利回り予([\d\.]+)%\s*\((\d+)\)", text)
            if m:
                dividend_yield = m.group(1) + "%"
                dividend_amount = m.group(2) + "円"
            elif re.search(r"配当利回り予([\d\.]+)%", text):
                m2 = re.search(r"配当利回り予([\d\.]+)%", text)
                dividend_yield = m2.group(1) + "%"
            m = re.search(r"ROE（連）予([\d\.\-]+)%", text)
            if m:
                roe = m.group(1) + "%"
            m = re.search(r"EPS（連）予([\d\.\-,]+)円", text)
            if m:
                eps = m.group(1) + "円"
            m = re.search(r"BPS（連）([\d\.\-,]+)円", text)
            if m:
                bps = m.group(1) + "円"
            m = re.search(r"株主資本比率（連）([\d\.\-]+)%", text)
            if m:
                equity_ratio = m.group(1) + "%"
            break

    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if "終値" in text and "始値" in text and len(text) < 300:
            m = re.search(r"終値[+\-\d\.%]*?([\d,]+)出来高", text)
            if m:
                stock_price = m.group(1) + "円"
            break

    return {
        "listed": True,
        "company_name": company_name,
        "code": code,
        "stock_price": stock_price,
        "dividend_yield": dividend_yield,
        "dividend_amount": dividend_amount,
        "per": per,
        "pbr": pbr,
        "roe": roe,
        "eps": eps,
        "bps": bps,
        "equity_ratio": equity_ratio,
        "market_cap": market_cap,
    }


def get_results(code: str) -> list[dict]:
    """売上高・営業利益・純利益・EPSの年次推移（最大15年）を取得する。"""
    soup = _get(f"{BASE_URL}/{code}/results")
    if soup is None:
        return []

    # ヘッダー名→列インデックスのマッピング候補（優先順に記載・完全一致優先）
    COL_KEYS = {
        "revenue":    ["売上", "経常収益", "収益"],
        "op_profit":  ["営利", "営業利益", "経常"],
        "net_profit": ["当期利益", "純利益", "当期純利益", "純利"],
        "eps":        ["EPS"],
        "roe":        ["ROE"],
    }
    # テーブル検出に使うキーワード（部分一致）
    TABLE_DETECT = ["売上", "収益", "営利", "経常収益"]

    results = []
    for table in soup.find_all("table"):
        # th が重複している場合は先頭の出現分だけ使う
        raw_headers = [th.get_text(strip=True) for th in table.find_all("th")]
        half = len(raw_headers) // 2
        headers = raw_headers[:half] if half and raw_headers[:half] == raw_headers[half:] else raw_headers

        if not any(kw in h for h in headers for kw in TABLE_DETECT):
            continue

        # 各フィールドの列インデックスをヘッダーから動的に解決
        # 完全一致を優先し、なければ部分一致にフォールバック
        col_idx: dict[str, int] = {}
        for field, keywords in COL_KEYS.items():
            for kw in keywords:
                # 完全一致
                for i, h in enumerate(headers):
                    if h == kw:
                        col_idx[field] = i
                        break
                if field in col_idx:
                    break
                # 部分一致（フォールバック）
                for i, h in enumerate(headers):
                    if kw in h:
                        col_idx[field] = i
                        break
                if field in col_idx:
                    break

        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3:
                continue

            def _cell(field: str) -> str:
                idx = col_idx.get(field)
                return cells[idx] if idx is not None and idx < len(cells) else "不明"

            results.append({
                "year":       cells[0] if cells[0] else "不明",
                "revenue":    _cell("revenue"),
                "op_profit":  _cell("op_profit"),
                "net_profit": _cell("net_profit"),
                "eps":        _cell("eps"),
                "roe":        _cell("roe"),
            })
        break
    return results


def get_dividends(code: str) -> list[dict]:
    """過去の配当金履歴を取得する。"""
    soup = _get(f"{BASE_URL}/{code}/dividend")
    if soup is None:
        return []

    dividends = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "合計" not in headers and "中間" not in headers:
            continue

        # 動的に列インデックスを解決（四半期配当など列数が異なる企業に対応）
        def _find_col(keywords: list[str]) -> int | None:
            for kw in keywords:
                for i, h in enumerate(headers):
                    if h == kw:          # 完全一致優先
                        return i
            for kw in keywords:
                for i, h in enumerate(headers):
                    if kw in h:          # 部分一致フォールバック
                        return i
            return None

        # 分割調整列を優先（株式分割があっても一貫したトレンドを表示するため）
        # 分割調整列がなければ合計列にフォールバック
        adjusted_idx = _find_col(["分割調整"])
        total_idx    = adjusted_idx if adjusted_idx is not None else _find_col(["合計"])
        yield_idx    = _find_col(["利回り"])
        interim_idx  = _find_col(["中間"])
        yearend_idx  = _find_col(["期末", "年末"])

        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 3:
                continue

            def _cell(idx: int | None) -> str:
                return cells[idx] if idx is not None and idx < len(cells) else "不明"

            dividends.append({
                "year":    cells[0] if cells[0] else "不明",
                "type":    cells[1] if len(cells) > 1 else "不明",
                "interim": _cell(interim_idx),
                "yearend": _cell(yearend_idx),
                "total":   _cell(total_idx),
                "yield":   _cell(yield_idx),
            })
        break
    return dividends


def _parse_value(text: str) -> float | None:
    """'10.8兆'や'-0.44兆'や'3253億'などを数値（億円）に変換する。"""
    if not text or text in ("不明", "-", "*", "赤字", ""):
        return None
    text = text.replace(",", "").replace("*", "").strip()
    neg = text.startswith("-")
    text = text.lstrip("-")
    try:
        m = re.match(r"([\d\.]+)兆", text)
        if m:
            val = float(m.group(1)) * 10000
            return -val if neg else val
        m = re.match(r"([\d\.]+)億", text)
        if m:
            val = float(m.group(1))
            return -val if neg else val
        m = re.match(r"([\d\.]+)", text)
        if m:
            val = float(m.group(1))
            return -val if neg else val
    except Exception:
        pass
    return None


def scrape_all(query: str) -> dict:
    """
    社名または証券コードを受け取り、全データを返す。

    戻り値のパターン:
    - 正常: {"listed": True, ...}
    - 複数候補: {"multiple": True, "candidates": [...]}
    - 未発見: {"listed": False, "error": "..."}
    """
    query = query.strip()
    # 全角数字・スペースを半角に変換
    query = query.translate(str.maketrans("０１２３４５６７８９　", "0123456789 ")).strip()

    if re.fullmatch(r"\d{4}", query):
        code = query
    else:
        candidates = search_code(query)
        if not candidates:
            return {"listed": False, "error": f"「{query}」に該当する上場企業が見つかりませんでした。"}
        if len(candidates) == 1:
            code = candidates[0]["code"]
        else:
            return {"multiple": True, "candidates": candidates[:10]}

    import time

    info = get_company_info(code)
    if not info.get("listed"):
        return {"listed": False, "error": "該当する上場企業が見つかりませんでした。"}

    time.sleep(0.5)
    results = get_results(code)
    time.sleep(0.5)
    dividends = get_dividends(code)
    time.sleep(0.3)
    sector_info = get_sector(code)

    # グラフ用に数値データを整形
    chart_results = []
    for r in results:
        chart_results.append({
            **r,
            "revenue_val": _parse_value(r["revenue"]),
            "op_profit_val": _parse_value(r["op_profit"]),
            "net_profit_val": _parse_value(r["net_profit"]),
            "eps_val": _parse_value(r["eps"]),
            "roe_val": _parse_value(r["roe"]),
        })

    chart_dividends = []
    for d in dividends:
        chart_dividends.append({
            **d,
            "total_val": _parse_value(d["total"]),
            "yield_val": _parse_value(d["yield"].replace("%", "") if d["yield"] != "不明" else "不明"),
        })

    return {
        "listed": True,
        "error": None,
        **info,
        **sector_info,
        "results": chart_results,
        "dividends": chart_dividends,
    }
