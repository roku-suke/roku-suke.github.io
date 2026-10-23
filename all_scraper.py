import datetime
import json
import os
import re
import time
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

SERIES_CONFIG = {
    "18promax": {
        "name": "iPhone 18 Pro Max",
        "colors": ["バーガンディ", "ブラック", "シルバー", "グレイシャー"],
        "models": [
            "18 Pro Max 256GB",
            "18 Pro Max 512GB",
            "18 Pro Max 1TB",
            "18 Pro Max 2TB",
        ],
    },
    "18pro": {
        "name": "iPhone 18 Pro",
        "colors": ["バーガンディ", "ブラック", "シルバー", "グレイシャー"],
        "models": [
            "18 Pro 256GB",
            "18 Pro 512GB",
            "18 Pro 1TB",
            "18 Pro 2TB",
        ],
    },
    "duo": {
        "name": "iPhone Duo",
        "colors": ["スターホワイト", "ナイトスカイ"],
        "models": [
            "iPhone Duo 256GB",
            "iPhone Duo 512GB",
            "iPhone Duo 1TB",
            "iPhone Duo 2TB",
        ],
    },
}

ALL_MODELS = (
    SERIES_CONFIG["18promax"]["models"]
    + SERIES_CONFIG["18pro"]["models"]
    + SERIES_CONFIG["duo"]["models"]
)

APPLE_PRICES = {
    "18 Pro Max 256GB": 239800,
    "18 Pro Max 512GB": 274800,
    "18 Pro Max 1TB": 344800,
    "18 Pro Max 2TB": 449800,
    "18 Pro 256GB": 219800,
    "18 Pro 512GB": 254800,
    "18 Pro 1TB": 324800,
    "18 Pro 2TB": 429800,
    "iPhone Duo 256GB": 364800,
    "iPhone Duo 512GB": 399800,
    "iPhone Duo 1TB": 469800,
    "iPhone Duo 2TB": 574800,
}

HISTORY_FILE = "price_history.json"
OUTPUT_FILE = "all_prices.json"
JS_OUTPUT_FILE = "all_prices.js"
CHECK_LOG_FILE = "check_log.txt"


def get_series_colors(model_name):
    if "Duo" in model_name:
        return SERIES_CONFIG["duo"]["colors"]
    return SERIES_CONFIG["18pro"]["colors"]


def parse_color_diff_and_availability(color_name, remarks_text):
    if not remarks_text:
        return True, 0

    rem = remarks_text.replace(" ", "").replace(" ", "")

    # 「他色買取不可」判定
    if "他色買取不可" in rem:
        if color_name in ["バーガンディ", "スターホワイト"]:
            return True, 0
        else:
            return False, 0

    aliases = [color_name]
    if color_name == "グレイシャー":
        aliases.extend(["グレイシャ-", "グレーシャー"])
    elif color_name == "スターホワイト":
        aliases.extend(["ホワイト", "白"])
    elif color_name == "ナイトスカイ":
        aliases.extend(["スカイ"])

    alias_pattern = "|".join(re.escape(a) for a in aliases)

    # 特定色「買取不可」判定
    if re.search(rf"(?:{alias_pattern})[^\d]*?買取不可", rem):
        return False, 0

    # 減額抽出
    m1 = re.search(rf"(?:{alias_pattern})[^\d+-]*?([+-]\s*[\d,]+)", rem)
    if m1:
        val = int(m1.group(1).replace(",", ""))
        if abs(val) >= 500:
            return True, val

    m2 = re.search(rf"(?:{alias_pattern})[^\d]*?([\d,]+)\s*円", rem)
    if m2:
        val = int(m2.group(1).replace(",", ""))
        if val >= 500:
            return True, -val

    return True, 0


def fetch_usd_jpy():
    try:
        res = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD", timeout=10
        )
        return res.json().get("rates", {}).get("JPY", 0)
    except Exception:
        return 0


# 1. 買取一丁目
def fetch_1chome():
    print("[1/6] 買取一丁目 取得中...")
    products = [
        {"name": "18 Pro Max 256GB", "itemId": "1648", "itemDetailId": "2300"},
        {"name": "18 Pro Max 512GB", "itemId": "1649", "itemDetailId": "2303"},
        {"name": "18 Pro Max 1TB", "itemId": "1650", "itemDetailId": "2306"},
        {"name": "18 Pro Max 2TB", "itemId": "1651", "itemDetailId": "2309"},
        {"name": "18 Pro 256GB", "itemId": "1652", "itemDetailId": "2312"},
        {"name": "18 Pro 512GB", "itemId": "1653", "itemDetailId": "2315"},
        {"name": "18 Pro 1TB", "itemId": "1654", "itemDetailId": "2318"},
        {"name": "18 Pro 2TB", "itemId": "1655", "itemDetailId": "2321"},
        {"name": "iPhone Duo 256GB", "itemId": "1656", "itemDetailId": "2324"},
        {"name": "iPhone Duo 512GB", "itemId": "1657", "itemDetailId": "2327"},
        {"name": "iPhone Duo 1TB", "itemId": "1658", "itemDetailId": "2330"},
        {"name": "iPhone Duo 2TB", "itemId": "1659", "itemDetailId": "2333"},
    ]
    results = {}
    for p in products:
        m_colors = get_series_colors(p["name"])
        url = (
            f"https://www.1-chome.com/api/keitai/getKeitaiItem"
            f"?keitaiItemId={p['itemId']}&keitaiItemKbId={p['itemDetailId']}"
        )
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json().get("data", {})
            kb_details = (
                data.get("keitaiItemKb", {}).get("keitaiKbDetails", [])
            )
            target = next(
                (
                    d
                    for d in kb_details
                    if str(d.get("keitaiItemKbId")) == str(p["itemDetailId"])
                ),
                None,
            )

            if target:
                base_price = int(target.get("kbDetailPrice", 0))
                detail_id = target.get("keitaiKbDetailId")
                color_list = (data.get("keitaiItemColorDtoGroup") or {}).get(
                    str(detail_id), []
                )

                found_colors = {}
                if isinstance(color_list, list) and len(color_list) > 0:
                    for item in color_list:
                        c_name = item.get("color", "").strip()
                        if c_name == "グレイシャ-":
                            c_name = "グレイシャー"
                        v_price = int(item.get("varPrice") or 0)
                        found_colors[c_name] = base_price + v_price

                color_prices = {}
                for c in m_colors:
                    color_prices[c] = found_colors.get(c, base_price)
                results[p["name"]] = color_prices
            else:
                results[p["name"]] = {c: None for c in m_colors}
        except Exception:
            results[p["name"]] = {c: None for c in m_colors}
        time.sleep(0.2)
    return results


# 2. モバイル一番
def fetch_mobile_ichiban():
    print("[2/6] モバイル一番 取得中...")
    pages = [
        ("https://www.mobile-ichiban.com/Prod/1/01/40", [
            ("18 Pro Max 256GB", "S013610"), ("18 Pro Max 512GB", "S013612"),
            ("18 Pro Max 1TB", "S013614"), ("18 Pro Max 2TB", "S013616")
        ]),
        ("https://www.mobile-ichiban.com/Prod/1/01/39", [
            ("18 Pro 256GB", "S013602"), ("18 Pro 512GB", "S013604"),
            ("18 Pro 1TB", "S013606"), ("18 Pro 2TB", "S013608")
        ]),
        ("https://www.mobile-ichiban.com/Prod/1/01/41", [
            ("iPhone Duo 256GB", "S013938"), ("iPhone Duo 512GB", "S013939"),
            ("iPhone Duo 1TB", "S013940"),   ("iPhone Duo 2TB", "S013941")
        ])
    ]
    results = {}
    remarks_log = {}

    for url, items in pages:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            html = res.text

            for name, sid in items:
                m_colors = get_series_colors(name)
                base_price = None
                remarks = ""

                p_match = re.search(r'id="NewPrice_' + sid + r'">([^<]+)</label>', html)
                if p_match:
                    cn = re.sub(r"[^\d]", "", p_match.group(1))
                    if cn:
                        base_price = int(cn)

                r_match = re.search(r'id="Img_' + sid + r'"[\s\S]*?<small class="my-prod-remarks"[^>]*>([\s\S]*?)</small>', html)
                remarks = r_match.group(1) if r_match else ""

                remarks_log[name] = remarks
                color_prices = {}
                for c in m_colors:
                    if base_price is None:
                        color_prices[c] = None
                        continue
                    is_avail, diff = parse_color_diff_and_availability(c, remarks)
                    color_prices[c] = (base_price + diff) if is_avail else None

                results[name] = color_prices
        except Exception as e:
            print(f"モバイル一番 エラー ({url}): {e}")
        time.sleep(0.3)

    for name in ALL_MODELS:
        if name not in results:
            m_colors = get_series_colors(name)
            results[name] = {c: None for c in m_colors}
    return results, remarks_log


# 3. 買取楽園 カラー価格解析補助
def parse_rakuen_color_prices(base_price, desc_raw, colors):
    if base_price is None:
        return {c: None for c in colors}

    desc = re.sub(r'<[^>]+>', ' ', desc_raw)
    desc = desc.replace('\n', ' ').replace('\r', ' ').replace(' ', ' ')

    prices = {c: base_price for c in colors}

    # 「他色買取不可」判定
    if "他色買取不可" in desc or "他色不可" in desc:
        for c in colors:
            if c not in ["バーガンディ", "スターホワイト"]:
                prices[c] = None

    if "ナイトスカイ" in colors:
        alias_to_color = {
            "スターホワイト": "スターホワイト", "ホワイト": "スターホワイト", "白": "スターホワイト",
            "ナイトスカイ": "ナイトスカイ", "スカイ": "ナイトスカイ", "ブラック": "ナイトスカイ", "黒": "ナイトスカイ",
        }
    else:
        alias_to_color = {
            "バーガンディ": "バーガンディ", "紫": "バーガンディ",
            "ブラック": "ブラック", "黒": "ブラック",
            "シルバー": "シルバー", "銀": "シルバー",
            "グレイシャー": "グレイシャー", "グレーシャー": "グレイシャー", "グレイシャ-": "グレイシャー", "青": "グレイシャー",
        }

    token_pat = r'(?:バーガンディ|グレイシャー|グレーシャー|グレイシャ-|スターホワイト|ナイトスカイ|ホワイト|ブラック|シルバー|スカイ|[黒青銀白紫])'
    color_group_pat = rf'(?:{token_pat}(?:[ /、]{token_pat})*)'

    # 直接価格指定 ("青 266,000" / "黒/青 330,500" / "黒/青/銀 375,000")
    for m in re.finditer(rf'({color_group_pat})\s*[:：]?\s*[¥￥]?\s*([\d,]{{5,}})\s*円?', desc):
        raw_colors = m.group(1)
        raw_val = re.sub(r'[^\d]', '', m.group(2))
        if raw_val:
            val = int(raw_val)
            for tok in re.split(r'[ /、]+', raw_colors):
                target_c = alias_to_color.get(tok)
                if target_c and target_c in prices:
                    prices[target_c] = val

    # 差額指定 ("黒/青 -2000" / "他色 -3000")
    for m in re.finditer(rf'({color_group_pat}|他色)\s*[:：]?\s*([▲△▼+-]\s*[\d,]+)', desc):
        raw_colors = m.group(1)
        raw_diff = m.group(2).replace('▲', '-').replace('▼', '-').replace('△', '+')
        raw_num = re.sub(r'[^\d-]', '', raw_diff)
        if raw_num:
            diff = int(raw_num)
            if raw_colors == "他色":
                for c in colors:
                    if c not in ["バーガンディ", "スターホワイト"]:
                        prices[c] = base_price + diff
            else:
                for tok in re.split(r'[ /、]+', raw_colors):
                    target_c = alias_to_color.get(tok)
                    if target_c and target_c in prices:
                        prices[target_c] = base_price + diff

    # 特定色「買取不可」 ("銀 買取不可")
    for m in re.finditer(rf'({color_group_pat})\s*[:：]?\s*買取不可', desc):
        raw_colors = m.group(1)
        for tok in re.split(r'[ /、]+', raw_colors):
            target_c = alias_to_color.get(tok)
            if target_c and target_c in prices:
                prices[target_c] = None

    return prices


# 3. 買取楽園
def fetch_kaitorirakuen():
    print("[3/6] 買取楽園 取得中...")
    urls = [
        "https://www.keitairakuen.com/product-category/keitai/iphone/iphone18-%e3%82%b7%e3%83%aa%e3%83%bc%e3%82%ba/iphone18-promax/",
        "https://www.keitairakuen.com/product-category/keitai/iphone/iphone18-%e3%82%b7%e3%83%aa%e3%83%bc%e3%82%ba/iphone18-pro/",
        "https://www.keitairakuen.com/product-category/keitai/iphone/iphone18-%e3%82%b7%e3%83%aa%e3%83%bc%e3%82%ba/iphone-duo/",
    ]
    pattern = re.compile(
        r'<p class="name product-title[^>]*>(.*?)</p>[\s\S]*?<div class="woocommerce-loop-description">([\s\S]*?)</div>[\s\S]*?<p class="global-attribute-price">新品:.*?&yen;</span>([\d,]+)</bdi>'
    )
    results = {}

    for url in urls:
        for attempt in range(3):
            try:
                res = requests.get(url, headers=HEADERS, timeout=20)
                if res.status_code == 200:
                    for m_name, desc_text, price in pattern.findall(res.text):
                        if "未開封" in desc_text:
                            for target in ALL_MODELS:
                                clean_t = target.replace(" Pro Max ", " Promax ").replace(" ", "").lower()
                                if clean_t in m_name.replace(" ", "").lower():
                                    base_p = int(price.replace(",", ""))
                                    m_colors = get_series_colors(target)
                                    results[target] = parse_rakuen_color_prices(base_p, desc_text, m_colors)
                    break
            except Exception as e:
                print(f"買取楽園 一時エラー ({url}): {e}")
            time.sleep(0.5)

    for name in ALL_MODELS:
        if name not in results:
            m_colors = get_series_colors(name)
            results[name] = {c: None for c in m_colors}

    return results


# 4. 買取ルデヤ
def fetch_rudeya():
    print("[4/6] 買取ルデヤ 取得中 (待機)...")
    results = {}
    for name in ALL_MODELS:
        m_colors = get_series_colors(name)
        results[name] = {c: None for c in m_colors}
    return results


# 5. MobileMix
def fetch_mobilemix():
    print("[5/6] MobileMix 取得中...")
    results = {}
    remarks_log = {}
    diag_mix = []

    pro_url = "https://mobile-mix.jp/?category=7"
    pro_map = [
        ("18 Pro Max 256GB", "613"), ("18 Pro Max 512GB", "614"),
        ("18 Pro Max 1TB", "615"),   ("18 Pro Max 2TB", "616"),
        ("18 Pro 256GB", "617"),     ("18 Pro 512GB", "618"),
        ("18 Pro 1TB", "619"),       ("18 Pro 2TB", "620")
    ]
    try:
        res = requests.get(pro_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        for name, mid in pro_map:
            m_colors = get_series_colors(name)
            base_price = None
            remarks = ""

            p_elem = soup.find(id=f"model{mid}")
            if p_elem:
                cn = re.sub(r"[^\d]", "", p_elem.get_text())
                if cn and int(cn) > 50000:
                    base_price = int(cn)

            tr_elem = soup.find("tr", id=mid)
            if tr_elem:
                next_tr = tr_elem.find_next_sibling("tr")
                if next_tr:
                    tds = next_tr.find_all("td")
                    if len(tds) >= 2:
                        remarks = tds[1].get_text()

            remarks_log[name] = remarks
            color_prices = {}
            for c in m_colors:
                if base_price is None:
                    color_prices[c] = None
                    continue
                is_avail, diff = parse_color_diff_and_availability(c, remarks)
                color_prices[c] = (base_price + diff) if is_avail else None
            results[name] = color_prices
    except Exception as e:
        print(f"MobileMix Pro系エラー: {e}")

    duo_urls = [
        "https://mobile-mix.jp/?category=3",
        "https://mobile-mix.jp/?category=7"
    ]
    duo_models = ["iPhone Duo 256GB", "iPhone Duo 512GB", "iPhone Duo 1TB", "iPhone Duo 2TB"]

    for d_url in duo_urls:
        try:
            res = requests.get(d_url, headers=HEADERS, timeout=15)
            diag_mix.append(f"URL: {d_url} (HTTP {res.status_code}, len:{len(res.text)})")
            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.find_all("tr")

            for name in duo_models:
                if results.get(name) and any(v is not None for v in results[name].values()):
                    continue

                m_colors = get_series_colors(name)
                cap = re.search(r"(256GB|512GB|1TB|2TB)", name).group(1)
                cap_short = cap.replace("B", "")
                base_price = None
                remarks = ""

                for idx, r in enumerate(rows):
                    txt = r.get_text().replace(" ", "").replace(" ", "")
                    if "Duo" in txt and (cap in txt or cap_short in txt):
                        nums = re.findall(r"[\d,]{6,}", txt)
                        for n in nums:
                            val = int(n.replace(",", ""))
                            if 300000 <= val <= 800000:
                                base_price = val
                                if idx + 1 < len(rows):
                                    next_tds = rows[idx + 1].find_all("td")
                                    remarks = next_tds[1].get_text() if len(next_tds) >= 2 else rows[idx + 1].get_text()
                                break
                        if base_price:
                            break

                if base_price:
                    remarks_log[name] = remarks
                    color_prices = {}
                    for c in m_colors:
                        is_avail, diff = parse_color_diff_and_availability(c, remarks)
                        color_prices[c] = (base_price + diff) if is_avail else None
                    results[name] = color_prices
        except Exception as e:
            diag_mix.append(f"エラー: {d_url} ({e})")

    for name in ALL_MODELS:
        if name not in results:
            m_colors = get_series_colors(name)
            results[name] = {c: None for c in m_colors}
    return results, remarks_log, diag_mix


# 6. モバステ (Pastec)
def fetch_mobaste():
    print("[6/6] モバステ (Pastec) 取得中...")
    configs = [
        {
            "url": "https://pastec.net/iphone?series_child_id=644",
            "items": [
                ("18 Pro Max 256GB", "9"), ("18 Pro Max 512GB", "10"),
                ("18 Pro Max 1TB", "11"), ("18 Pro Max 2TB", "12")
            ]
        },
        {
            "url": "https://pastec.net/iphone?series_child_id=643",
            "items": [
                ("18 Pro 256GB", "9"), ("18 Pro 512GB", "10"),
                ("18 Pro 1TB", "11"), ("18 Pro 2TB", "12")
            ]
        }
    ]
    results = {}
    for cfg in configs:
        try:
            res = requests.get(cfg["url"], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")

            for name, sid in cfg["items"]:
                m_colors = get_series_colors(name)
                base_price = None
                remarks = ""

                tr_tag = soup.find("tr", attrs={"data-storage-id": sid})
                if tr_tag:
                    p_span = tr_tag.find("span", class_=re.compile(r"price--unopened"))
                    if p_span:
                        cn = re.sub(r"[^\d]", "", p_span.get_text())
                        if cn:
                            base_price = int(cn)
                    caution_div = tr_tag.find("div", class_=re.compile(r"p-priceTable__caution"))
                    if caution_div:
                        remarks = caution_div.get_text()

                color_prices = {}
                for c in m_colors:
                    if base_price is None:
                        color_prices[c] = None
                        continue
                    is_avail, diff = parse_color_diff_and_availability(c, remarks)
                    color_prices[c] = (base_price + diff) if is_avail else None

                results[name] = color_prices
        except Exception:
            pass
        time.sleep(0.3)

    for name in ALL_MODELS:
        if name not in results:
            m_colors = get_series_colors(name)
            results[name] = {c: None for c in m_colors}
    return results


# 7. 履歴保存・変動判定
def process_history(current_data, now_dt):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append({
        "timestamp": now_dt.isoformat(),
        "data": current_data
    })

    cutoff_35d = now_dt - datetime.timedelta(days=35)
    history = [
        h for h in history
        if datetime.datetime.fromisoformat(h["timestamp"]) >= cutoff_35d
    ]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

    recent_48_entries = history[-48:]
    cutoff_7d = now_dt - datetime.timedelta(days=7)

    shops = ["chome", "ichiban", "rakuen", "rudeya", "mobilemix", "mobaste"]
    analysis = {}

    for model in ALL_MODELS:
        analysis[model] = {}
        colors = current_data.get(model, {}).keys()

        for c in colors:
            analysis[model][c] = {
                "shifts": {s: "" for s in shops},
                "trend": "-"
            }

            for shop in shops:
                curr_p = current_data.get(model, {}).get(c, {}).get(shop)
                shift_val = ""

                if isinstance(curr_p, (int, float)):
                    prices_in_48 = []
                    for entry in reversed(recent_48_entries):
                        p = entry.get("data", {}).get(model, {}).get(c, {}).get(shop)
                        if isinstance(p, (int, float)):
                            prices_in_48.append(p)

                    prev_diff_p = None
                    for p in prices_in_48:
                        if p != curr_p:
                            prev_diff_p = p
                            break

                    if prev_diff_p is not None:
                        if curr_p > prev_diff_p:
                            shift_val = "up"
                        elif curr_p < prev_diff_p:
                            shift_val = "down"

                analysis[model][c]["shifts"][shop] = shift_val

            recent_max = []
            older_max = []
            for entry in history:
                e_dt = datetime.datetime.fromisoformat(entry["timestamp"])
                p_dict = entry.get("data", {}).get(model, {}).get(c, {})
                v_list = [v for v in p_dict.values() if isinstance(v, (int, float))]
                if v_list:
                    m_val = max(v_list)
                    if e_dt >= cutoff_7d:
                        recent_max.append(m_val)
                    else:
                        older_max.append(m_val)

            trend_val = "-"
            if recent_max and len(older_max) >= 3:
                avg_recent = sum(recent_max) / len(recent_max)
                avg_older = sum(older_max) / len(older_max)
                diff_pct = (avg_recent - avg_older) / avg_older * 100
                if diff_pct >= 0.3:
                    trend_val = "上昇↑"
                elif diff_pct <= -0.3:
                    trend_val = "下降↓"
                else:
                    trend_val = "横ばい→"

            analysis[model][c]["trend"] = trend_val

    return analysis


def main():
    now_dt = datetime.datetime.now()
    print("=== 全6店舗・3シリーズ価格データ取得および厳密分析開始 ===")

    usd_jpy = fetch_usd_jpy()

    d_1chome = fetch_1chome()
    d_ichiban, rem_ichiban = fetch_mobile_ichiban()
    d_rakuen = fetch_kaitorirakuen()
    d_rudeya = fetch_rudeya()
    d_mobilemix, rem_mix, diag_mix = fetch_mobilemix()
    d_mobaste = fetch_mobaste()

    raw_current = {}
    for model in ALL_MODELS:
        raw_current[model] = {}
        colors = get_series_colors(model)
        for c in colors:
            raw_current[model][c] = {
                "chome": d_1chome.get(model, {}).get(c),
                "ichiban": d_ichiban.get(model, {}).get(c),
                "rakuen": d_rakuen.get(model, {}).get(c),
                "rudeya": d_rudeya.get(model, {}).get(c),
                "mobilemix": d_mobilemix.get(model, {}).get(c),
                "mobaste": d_mobaste.get(model, {}).get(c),
            }

    summary_lines = []
    summary_lines.append("=" * 85)
    summary_lines.append(f"【実取得データ厳密チェックサマリー】 ({now_dt.strftime('%Y/%m/%d %H:%M:%S')})")
    summary_lines.append("=" * 85)
    for test_m in ALL_MODELS:
        summary_lines.append(f"\n▼ {test_m}:")
        rem_i = rem_ichiban.get(test_m, "").replace("\n", " ").strip()
        rem_m = rem_mix.get(test_m, "").replace("\n", " ").strip()
        if rem_i:
            summary_lines.append(f"  [一番備考]: {rem_i[:60]}")
        if rem_m:
            summary_lines.append(f"  [ Mix備考]: {rem_m[:60]}")

        for c in get_series_colors(test_m):
            v = raw_current[test_m][c]
            summary_lines.append(
                f"  [{c:^7}] 一丁目:{str(v['chome']):>7} | 一番:{str(v['ichiban']):>7} | "
                f"楽園:{str(v['rakuen']):>7} | Mix:{str(v['mobilemix']):>7} | モバステ:{str(v['mobaste']):>7}"
            )

    summary_lines.append("\n" + "-" * 85)
    summary_lines.append("【Mix(Duo)診断情報】")
    for d in diag_mix[:5]:
        summary_lines.append("  " + d)
    summary_lines.append("=" * 85)

    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text + "\n")

    with open(CHECK_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(summary_text)

    analysis = process_history(raw_current, now_dt)

    series_output = {}
    for s_key, s_info in SERIES_CONFIG.items():
        m_list = []
        for model in s_info["models"]:
            list_price = APPLE_PRICES.get(model, 0)
            c_list = []
            for c in s_info["colors"]:
                shops = raw_current[model].get(c, {})
                shifts = analysis.get(model, {}).get(c, {}).get("shifts", {})
                trend = analysis.get(model, {}).get(c, {}).get("trend", "-")

                c_list.append({
                    "name": c,
                    "chome": shops.get("chome"),
                    "cShift": shifts.get("chome", ""),
                    "ichiban": shops.get("ichiban"),
                    "iShift": shifts.get("ichiban", ""),
                    "rakuen": shops.get("rakuen"),
                    "rShift": shifts.get("rakuen", ""),
                    "rudeya": shops.get("rudeya"),
                    "mobilemix": shops.get("mobilemix"),
                    "mShift": shifts.get("mobilemix", ""),
                    "mobaste": shops.get("mobaste"),
                    "sShift": shifts.get("mobaste", ""),
                    "trend": trend
                })

            m_list.append({
                "model": model,
                "listPrice": list_price,
                "colors": c_list
            })
        series_output[s_key] = m_list

    final_output = {
        "updated_at": now_dt.strftime("%Y/%m/%d %H:%M:%S"),
        "usd_jpy": usd_jpy,
        "series": series_output
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    with open(JS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("window.SCRAPED_PRICES_DATA = " + json.dumps(final_output, ensure_ascii=False) + ";")

    print(f"データ生成完了！ '{CHECK_LOG_FILE}' に全機種の詳細サマリーを保存しました。")
    print("\n------------------------------------------------------------")

    # GitHub Actions上の自動実行時はそのまま終了し、PCローカル実行時のみEnter待ちにする
    if not os.environ.get("GITHUB_ACTIONS"):
        input("確認が完了したら、Enterキーを押してウィンドウを閉じてください...")


if __name__ == "__main__":
    main()
