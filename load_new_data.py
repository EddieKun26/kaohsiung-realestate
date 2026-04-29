#!/usr/bin/env python3
"""
從 115年第1季 資料夾讀取實價登錄資料
支援 A 檔（買賣）與 B 檔（預售屋）
輸出格式與原 kaohsiung_filtered_*.csv 完全相容

執行方式：
    python load_new_data.py
"""

from pathlib import Path
from datetime import datetime
import pandas as pd

# ── 設定 ──────────────────────────────────────────────────
SOURCE_DIR = Path("./lvr_data/115年第1季")
OUTPUT_DIR = Path("./lvr_data")
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

# ── 工具函式 ───────────────────────────────────────────────
def safe_float(v) -> float:
    try:
        return float(str(v).strip() or 0)
    except (ValueError, TypeError):
        return 0.0

def roc_to_date(roc: str) -> str:
    roc = str(roc).strip().split(".")[0]   # 去除小數點
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
    # 用 skiprows=1 讓 pandas 把英文那行當 header，跳過中文說明行
    df = pd.read_csv(path, encoding="utf-8-sig", skiprows=1, dtype=str)
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})
    df = df.fillna("")

    results = []
    for _, row in df.iterrows():
        district   = row.get("行政區", "").strip()
        bld_type   = row.get("建物型態", "").strip()

        # 篩選：目標行政區
        if district not in TARGET_DISTRICTS:
            continue
        # 篩選：住宅大樓 / 華廈
        if not any(kw in bld_type for kw in TARGET_BUILDING_KEYWORDS):
            continue

        # 面積
        area_sqm   = safe_float(row.get("建物面積_sqm", 0))
        area_ping  = round(area_sqm * SQM_TO_PING, 2)

        # 價格
        total_price = round(safe_float(row.get("總價元", 0)) / 10_000, 1)
        park_price  = round(safe_float(row.get("車位總價元", 0)) / 10_000, 1)

        # 每坪單價（扣車位）
        unit_price  = round((total_price - park_price) / area_ping, 2) if area_ping > 0 else 0.0

        # 含車位
        park_cat   = row.get("車位類別", "").strip()
        has_park   = park_price > 0 or park_cat != ""

        # 房型
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

# ── 主程式 ────────────────────────────────────────────────
def main():
    FILE_MAP = {
        "E_lvr_land_A.csv": "買賣(含新成屋/中古)",
        "E_lvr_land_B.csv": "預售屋",
    }

    all_records = []
    found_files = []
    missing_files = []

    for filename, tx_type in FILE_MAP.items():
        path = SOURCE_DIR / filename
        if path.exists() and path.stat().st_size > 0:
            records = load_csv(path, tx_type)
            print(f"✅ {filename}（{tx_type}）：篩選後 {len(records)} 筆")
            all_records.extend(records)
            found_files.append(filename)
        else:
            print(f"⚠️  {filename}（{tx_type}）：找不到或檔案為空")
            missing_files.append((filename, tx_type))

    if not all_records:
        print("❌ 沒有任何資料，請確認資料夾路徑")
        return

    # 儲存 CSV
    df_out = pd.DataFrame(all_records)
    output_path = OUTPUT_DIR / f"kaohsiung_filtered_{TODAY}.csv"
    df_out.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 輸出完成：{output_path.resolve()}")
    print(f"   共 {len(df_out)} 筆資料")

    # 摘要
    print("\n📊 各交易類型筆數：")
    for t, cnt in df_out["交易類型"].value_counts().items():
        print(f"   {t}：{cnt} 筆")

    print("\n📊 各行政區筆數：")
    for d, cnt in df_out["行政區"].value_counts().items():
        print(f"   {d}：{cnt} 筆")

    if missing_files:
        print("\n⚠️  以下檔案不存在，資料不完整：")
        for fname, ttype in missing_files:
            print(f"   ➤ {fname}（{ttype}）—— 請確認是否已下載")

    print("\n🎉 完成！重新整理 Streamlit 頁面即可看到新資料")

if __name__ == "__main__":
    main()
