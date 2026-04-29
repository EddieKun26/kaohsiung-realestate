#!/usr/bin/env python3
"""
從多個實價登錄資料夾讀取資料，合併去重後更新分析 CSV
支援 A 檔（買賣）與 B 檔（預售屋）

執行方式：
    python load_new_data.py
"""

from pathlib import Path
from datetime import datetime
import pandas as pd

# ── 設定 ──────────────────────────────────────────────────
DATA_ROOT = Path("./lvr_data")

# 要讀取的資料夾清單（相對於 DATA_ROOT）
SOURCE_DIRS = [
    "115年第1季",
    "20260211_opendata",
    "20260221_opendata",
    "download (3)",
]

# 每個資料夾中要讀取的高雄檔案（不分大小寫）
FILE_MAP = {
    "e_lvr_land_a": "買賣(含新成屋/中古)",
    "e_lvr_land_b": "預售屋",
}

OUTPUT_DIR = DATA_ROOT
TODAY = datetime.now().strftime("%Y%m%d")

TARGET_DISTRICTS = [
    "楠梓區", "左營區", "鼓山區", "三民區",
    "苓雅區", "新興區", "前金區", "鹽埕區",
    "前鎮區", "小港區", "鳳山區", "仁武區", "橋頭區",
]
TARGET_BUILDING_KEYWORDS = ["住宅大樓", "華廈"]
SQM_TO_PING = 0.3025

# 英文欄名 → 處理用別名
COL_MAP = {
    "The villages and towns urban district":            "行政區",
    "land sector position building sector house number plate": "地址",
    "transaction year month and day":                  "交易年月日_raw",
    "shifting level":                                  "移轉層次",
    "total floor number":                              "總樓層",
    "building state":                                  "建物型態",
    "building shifting total area":                    "建物面積_sqm",
    "Building present situation pattern - room":        "房",
    "building present situation pattern - hall":        "廳",
    "building present situation pattern - health":      "衛",
    "total price NTD":                                 "總價元",
    "the berth category":                              "車位類別",
    "berth shifting total area square meter":           "車位面積_sqm",
    "the berth total price NTD":                       "車位總價元",
    "the note":                                        "備註",
    "build case":                                      "成交建案名稱",
}

# 去重依據欄位（以字串比對，避免浮點精度問題）
DEDUP_COLS = ["地址", "交易日期", "成交總價(萬)", "總坪數"]

# ── 工具函式 ───────────────────────────────────────────────
def safe_float(v) -> float:
    try:
        return float(str(v).strip() or 0)
    except (ValueError, TypeError):
        return 0.0

def roc_to_date(roc: str) -> str:
    roc = str(roc).strip().split(".")[0]
    if not roc.isdigit():
        return ""
    try:
        padded = roc.zfill(7)
        y = int(padded[:3]) + 1911
        m = int(padded[3:5])
        d = int(padded[5:7])
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return ""
        return f"{y}-{m:02d}-{d:02d}"
    except Exception:
        return ""

def load_csv(path: Path, tx_type: str) -> list[dict]:
    """讀取一個 LVR CSV（新格式），回傳篩選後的記錄清單"""
    df = pd.read_csv(path, encoding="utf-8-sig", skiprows=1, dtype=str)
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})
    df = df.fillna("")

    results = []
    for _, row in df.iterrows():
        district = row.get("行政區", "").strip()
        bld_type = row.get("建物型態", "").strip()

        if district not in TARGET_DISTRICTS:
            continue
        if not any(kw in bld_type for kw in TARGET_BUILDING_KEYWORDS):
            continue

        area_sqm   = safe_float(row.get("建物面積_sqm", 0))
        area_ping  = round(area_sqm * SQM_TO_PING, 2)
        total_price = round(safe_float(row.get("總價元", 0)) / 10_000, 1)
        park_price  = round(safe_float(row.get("車位總價元", 0)) / 10_000, 1)
        unit_price  = round((total_price - park_price) / area_ping, 2) if area_ping > 0 else 0.0
        park_cat   = row.get("車位類別", "").strip()
        has_park   = park_price > 0 or park_cat != ""
        room_type  = (
            f"{row.get('房', '')}房"
            f"{row.get('廳', '')}廳"
            f"{row.get('衛', '')}衛"
        )

        results.append({
            "交易類型":       tx_type,
            "行政區":         district,
            "交易日期":       roc_to_date(row.get("交易年月日_raw", "")),
            "地址":           row.get("地址", "").strip(),
            "建物型態":       bld_type,
            "移轉層次":       row.get("移轉層次", "").strip(),
            "總樓層":         row.get("總樓層", "").strip(),
            "房型":           room_type,
            "總坪數":         area_ping,
            "成交總價(萬)":   total_price,
            "車位總價(萬)":   park_price,
            "每坪單價(萬)":   unit_price,
            "含車位":         "是" if has_park else "否",
            "車位類別":       park_cat,
            "成交建案名稱":   row.get("成交建案名稱", "").strip(),
            "備註":           row.get("備註", "").strip(),
        })
    return results

def find_csv(folder: Path, stem: str) -> Path | None:
    """大小寫不分地尋找 CSV 檔案"""
    for f in folder.glob("*.csv"):
        if f.stem.lower() == stem.lower():
            return f
    return None

# ── 主程式 ────────────────────────────────────────────────
def main():
    all_records: list[dict] = []

    # 1. 讀取現有最新的過濾後 CSV（作為基底）
    existing_csvs = sorted(OUTPUT_DIR.glob("kaohsiung_filtered_*.csv"), reverse=True)
    if existing_csvs:
        base_path = existing_csvs[0]
        df_base = pd.read_csv(base_path, encoding="utf-8-sig", dtype=str)
        all_records.extend(df_base.to_dict("records"))
        print(f"✅ 讀取現有資料：{base_path.name}（{len(df_base)} 筆）")
    else:
        print("⚠️  找不到現有 kaohsiung_filtered_*.csv，將從頭建立")

    # 2. 從各新資料夾讀取
    print("\n── 讀取新資料夾 ─────────────────────────────────────")
    for folder_name in SOURCE_DIRS:
        folder = DATA_ROOT / folder_name
        if not folder.exists():
            print(f"  ⚠️  {folder_name}：資料夾不存在，跳過")
            continue
        for stem, tx_type in FILE_MAP.items():
            csv_path = find_csv(folder, stem)
            if csv_path and csv_path.stat().st_size > 0:
                records = load_csv(csv_path, tx_type)
                print(f"  ✅ {folder_name}/{csv_path.name}（{tx_type}）：篩選後 {len(records)} 筆")
                all_records.extend(records)
            else:
                print(f"  ⚠️  {folder_name}/{stem}.csv：找不到或空白，跳過")

    if not all_records:
        print("\n❌ 沒有任何資料，請確認資料夾路徑")
        return

    df_out = pd.DataFrame(all_records)

    # 型別統一（避免字串 vs 數值混用導致去重失敗）
    for col in ["總坪數", "成交總價(萬)", "車位總價(萬)", "每坪單價(萬)"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").round(2)

    # 3. 修復建案名稱中的 ? 佔位符
    # 原理：政府資料轉碼失敗時某些字元被替換為 ASCII ?（0x3F）
    # 先套用手動字典，再用「相同長度且非 ? 位置完全相符」自動比對
    MANUAL_FIX: dict[str, str] = {
        "築?":   "築悅",
    }

    import re
    def _make_pattern(name: str) -> str:
        return "".join("." if c == "?" else re.escape(c) for c in name)

    all_names = df_out["成交建案名稱"].dropna().unique()
    clean_names = [n for n in all_names if "?" not in n and n.strip()]
    fix_map: dict[str, str] = dict(MANUAL_FIX)
    for dirty in all_names:
        if "?" not in dirty or not dirty.strip() or dirty in fix_map:
            continue
        pat = re.compile("^" + _make_pattern(dirty) + "$")
        candidates = [n for n in clean_names if len(n) == len(dirty) and pat.match(n)]
        if len(candidates) == 1:
            fix_map[dirty] = candidates[0]
        elif len(candidates) > 1:
            freq = df_out["成交建案名稱"].value_counts()
            fix_map[dirty] = max(candidates, key=lambda n: freq.get(n, 0))

    if fix_map:
        df_out["成交建案名稱"] = df_out["成交建案名稱"].replace(fix_map)
        print(f"\n🔧 建案名稱修復 {len(fix_map)} 筆：")
        for bad, good in fix_map.items():
            print(f"   {bad!r} → {good!r}")

    # 4. 去重複（保留先出現的）
    before = len(df_out)
    df_out = df_out.drop_duplicates(subset=DEDUP_COLS, keep="first")
    after  = len(df_out)
    print(f"\n📋 去重：{before} → {after} 筆（移除 {before - after} 筆重複）")

    # 4. 輸出 CSV
    output_path = OUTPUT_DIR / f"kaohsiung_filtered_{TODAY}.csv"
    df_out.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 輸出完成：{output_path.resolve()}")
    print(f"   共 {len(df_out)} 筆資料")

    # 5. 摘要
    print("\n📊 各交易類型筆數：")
    for t, cnt in df_out["交易類型"].value_counts().items():
        print(f"   {t}：{cnt} 筆")

    print("\n📊 各行政區筆數（前 10）：")
    for d, cnt in df_out["行政區"].value_counts().head(10).items():
        print(f"   {d}：{cnt} 筆")

    # 資料日期範圍
    dates = pd.to_datetime(df_out["交易日期"], errors="coerce").dropna()
    if not dates.empty:
        print(f"\n📅 資料期間：{dates.min().strftime('%Y-%m-%d')} ～ {dates.max().strftime('%Y-%m-%d')}")

    print("\n🎉 完成！重新整理 Streamlit 頁面即可看到新資料")

if __name__ == "__main__":
    main()
