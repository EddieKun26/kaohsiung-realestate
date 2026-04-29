#!/usr/bin/env python3
"""
高雄房產成交分析儀表板
資料來源：實價登錄 (kaohsiung_filtered_*.csv)
執行方式：streamlit run dashboard.py
"""

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ── 坪數分組定義 ─────────────────────────────────────────────
PING_BINS   = [0, 20, 25, 30, 35, 40, 45, float("inf")]
PING_LABELS = ["20坪以下", "20-25坪", "25-30坪", "30-35坪", "35-40坪", "40-45坪", "45坪以上"]

# ── 版面設定 ────────────────────────────────────────────────
st.set_page_config(
    page_title="高雄房產成交分析儀表板",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 側欄樣式
st.markdown("""
<style>
/* 側欄橫向區塊：垂直置中對齊 */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    align-items: center !important;
    margin-bottom: 6px !important;
}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
}
/* 篩選標題：消除段落預設 margin，字體統一 */
section[data-testid="stSidebar"] .filter-label p {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    color: #fafafa !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1 !important;
}
/* 獨立標題行（交易類型）加底部間距對齊 */
section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] .filter-label {
    display: block;
    margin-bottom: 6px !important;
}
/* multiselect 上方統一留白 */
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] {
    margin-top: 0 !important;
    margin-bottom: 12px !important;
}
/* 按鈕：撐滿欄寬後文字置中，防折行 */
section[data-testid="stSidebar"] .stButton button {
    width: 100% !important;
    font-size: 0.85rem !important;
    padding: 4px 4px !important;
    height: auto !important;
    min-height: 0 !important;
    white-space: nowrap !important;
    word-break: keep-all !important;
    text-align: center !important;
}
section[data-testid="stSidebar"] .stButton button * {
    font-size: 0.85rem !important;
    white-space: nowrap !important;
    margin: 0 !important;
    padding: 0 !important;
    text-align: center !important;
}
</style>
""", unsafe_allow_html=True)

# 主題色
PRIMARY = "#1f77b4"
DANGER  = "#e74c3c"
WARN    = "#f39c12"

# ── 讀取資料 ────────────────────────────────────────────────
DATA_DIR = Path("./lvr_data")

@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    csv_files = sorted(DATA_DIR.glob("kaohsiung_filtered_*.csv"), reverse=True)
    if not csv_files:
        st.error("找不到資料檔案，請先執行 lvr_kaohsiung.py 下載資料")
        st.stop()
    latest = csv_files[0]
    df = pd.read_csv(latest, encoding="utf-8-sig")

    # 欄位清理
    df["交易日期"] = pd.to_datetime(df["交易日期"], errors="coerce")
    df["年月"] = df["交易日期"].dt.to_period("M").astype(str)
    df["月份"] = df["交易日期"].dt.month
    df["年份"] = df["交易日期"].dt.year

    # 過濾極端值（每坪 < 5 或 > 200 視為異常/筆誤）
    df["單價異常"] = (df["每坪單價(萬)"] < 5) | (df["每坪單價(萬)"] > 200)

    # 異常交易旗標（備註有特殊關係字眼）
    ABNORMAL_KW = ["親友", "員工", "共有人", "特殊關係", "非市場", "贈與", "假交易"]
    df["異常交易"] = df["備註"].fillna("").apply(
        lambda x: any(kw in x for kw in ABNORMAL_KW)
    )

    # 坪數分組
    df["坪數分組"] = pd.cut(
        df["總坪數"], bins=PING_BINS, labels=PING_LABELS, right=False
    ).astype(str)
    # pd.cut 對超出 bins 範圍的值會產生 nan，補回最後一組
    df.loc[df["總坪數"] >= 45, "坪數分組"] = "45坪以上"

    # 成交建案名稱：空值補「無登錄建案」
    df["建案"] = df["成交建案名稱"].fillna("").str.strip()
    df.loc[df["建案"] == "", "建案"] = "無登錄建案"

    return df, latest.name


# 載入
df_all, data_filename = load_data()

# ── 初始化 session_state ────────────────────────────────────
tx_types   = df_all["交易類型"].dropna().unique().tolist()
districts  = sorted(df_all["行政區"].dropna().unique().tolist())
ping_groups = [g for g in PING_LABELS if g in df_all["坪數分組"].unique()]
price_min  = float(df_all["每坪單價(萬)"].replace(0, np.nan).dropna().min())
price_max  = float(df_all["每坪單價(萬)"].replace(0, np.nan).dropna().max())

def reset_filters():
    st.session_state["tx"]       = tx_types
    st.session_state["dist"]     = districts
    st.session_state["ping_grp"] = ping_groups
    st.session_state["price"]    = (price_min, price_max)

def clear_filters():
    st.session_state["tx"]       = []
    st.session_state["dist"]     = []
    st.session_state["ping_grp"] = []
    st.session_state["price"]    = (price_min, price_max)

# ── Sidebar 篩選器 ──────────────────────────────────────────
with st.sidebar:
    st.title("🔍 篩選條件")
    st.caption(f"資料檔：{data_filename}")

    # 全選 / 全清 按鈕
    btn1, btn2 = st.columns(2)
    with btn1:
        st.button("⟳ 全部重設", on_click=reset_filters, use_container_width=True)
    with btn2:
        st.button("✕ 全部清除", on_click=clear_filters, use_container_width=True)

    st.divider()

    # 交易類型
    st.markdown('<p class="filter-label">交易類型</p>', unsafe_allow_html=True)
    sel_tx = st.multiselect("", tx_types, default=tx_types, key="tx",
                            label_visibility="collapsed")

    # 行政區
    col_label, col_a, col_b = st.columns([2, 1, 1])
    with col_label:
        st.markdown('<p class="filter-label">行政區</p>', unsafe_allow_html=True)
    with col_a:
        if st.button("全選", key="dist_all"):
            st.session_state["dist"] = districts
            st.rerun()
    with col_b:
        if st.button("全清", key="dist_none"):
            st.session_state["dist"] = []
            st.rerun()
    sel_districts = st.multiselect("", districts, default=districts, key="dist",
                                   label_visibility="collapsed")

    # 坪數分組
    col_label2, col_c, col_d = st.columns([2, 1, 1])
    with col_label2:
        st.markdown('<p class="filter-label">坪數分組</p>', unsafe_allow_html=True)
    with col_c:
        if st.button("全選", key="ping_grp_all"):
            st.session_state["ping_grp"] = ping_groups
            st.rerun()
    with col_d:
        if st.button("全清", key="ping_grp_none"):
            st.session_state["ping_grp"] = []
            st.rerun()
    sel_ping_groups = st.multiselect("", ping_groups, default=ping_groups, key="ping_grp",
                                     label_visibility="collapsed")

    st.divider()

    # 每坪單價範圍
    sel_price = st.slider(
        "每坪單價 (萬/坪)", min_value=price_min, max_value=price_max,
        value=(price_min, price_max), step=0.5, key="price"
    )

    st.divider()

    # 異常交易
    hide_abnormal = st.checkbox("隱藏異常交易（親友/特殊關係）", value=False)
    hide_price_outlier = st.checkbox("隱藏單價異常值（<5 或 >200萬）", value=True)

    st.divider()
    st.caption("💡 代銷儀表板 | 高雄實價登錄 2026 Q1")


# ── 套用篩選 ────────────────────────────────────────────────
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        df["交易類型"].isin(sel_tx) &
        df["行政區"].isin(sel_districts) &
        df["坪數分組"].isin(sel_ping_groups) &
        df["每坪單價(萬)"].between(*sel_price)
    )
    if hide_abnormal:
        mask &= ~df["異常交易"]
    if hide_price_outlier:
        mask &= ~df["單價異常"]
    return df[mask].copy()


df = apply_filters(df_all)

# ── 主標題 ──────────────────────────────────────────────────
st.title("🏙️ 高雄房產成交分析儀表板")
st.caption("資料期間：2026年 Q1（1–3月）｜高雄 13 個行政區｜住宅大樓 & 華廈")

# ── KPI 卡片 ────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
valid_price = df[df["每坪單價(萬)"] > 0]

with k1:
    st.metric("篩選後筆數", f"{len(df):,} 筆",
              delta=f"全部 {len(df_all)} 筆" if len(df) != len(df_all) else None)
with k2:
    avg_p = valid_price["每坪單價(萬)"].mean()
    st.metric("平均每坪單價", f"{avg_p:.1f} 萬")
with k3:
    median_p = valid_price["每坪單價(萬)"].median()
    st.metric("中位每坪單價", f"{median_p:.1f} 萬")
with k4:
    avg_total = df["成交總價(萬)"].mean()
    st.metric("平均成交總價", f"{avg_total:,.0f} 萬")
with k5:
    abnormal_n = df_all["異常交易"].sum()
    st.metric("異常交易筆數", f"{abnormal_n} 筆",
              delta="已含" if not hide_abnormal and abnormal_n > 0 else "已排除" if hide_abnormal else None,
              delta_color="inverse")

st.divider()

# ── 頁籤 ────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 區域分析", "📐 坪數分析", "📈 成交趨勢", "🏗️ 建案比較", "⚠️ 異常交易", "🔎 全部資料"
])


# ═══════════════════════════════════════════════════════════
# Tab 1：區域分析
# ═══════════════════════════════════════════════════════════
with tab1:
    st.subheader("各行政區價格統計")

    col_a, col_b = st.columns(2)

    # 各區平均單價柱狀圖
    district_stats = (
        valid_price.groupby("行政區")["每坪單價(萬)"]
        .agg(平均單價="mean", 筆數="count", 標準差="std", 中位數="median")
        .reset_index()
        .sort_values("平均單價", ascending=False)
    )
    for col in ["平均單價", "標準差", "中位數"]:
        district_stats[col] = district_stats[col].round(1)

    with col_a:
        fig_bar = px.bar(
            district_stats,
            x="行政區", y="平均單價",
            error_y="標準差",
            text=district_stats["平均單價"].apply(lambda x: f"{x:.1f}"),
            color="平均單價",
            color_continuous_scale="Blues",
            title="各行政區平均每坪單價（萬/坪）",
            labels={"平均單價": "平均單價 (萬/坪)", "行政區": ""},
        )
        fig_bar.update_traces(
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "平均單價：%{y:.1f} 萬/坪<br>"
                "中位數：%{customdata[0]:.1f} 萬/坪<br>"
                "標準差：%{customdata[1]:.1f} 萬<br>"
                "成交筆數：%{customdata[2]} 筆"
                "<extra></extra>"
            ),
            customdata=district_stats[["中位數", "標準差", "筆數"]].values,
        )
        fig_bar.update_layout(coloraxis_showscale=False, height=420)
        st.plotly_chart(fig_bar, use_container_width=True)

    # 各區價格分布箱型圖
    with col_b:
        fig_box_dist = px.box(
            valid_price.sort_values("行政區"),
            x="行政區", y="每坪單價(萬)",
            color="行政區",
            title="各行政區單價分布",
            labels={"每坪單價(萬)": "每坪單價 (萬/坪)", "行政區": ""},
            points="outliers",
        )
        fig_box_dist.update_layout(showlegend=False, height=420)
        st.plotly_chart(fig_box_dist, use_container_width=True)

    # 熱力地圖：行政區 × 坪數分組
    st.subheader("價格熱力地圖（行政區 × 坪數分組）")

    pivot_data = (
        valid_price.groupby(["行政區", "坪數分組"])["每坪單價(萬)"]
        .mean()
        .reset_index()
        .pivot(index="行政區", columns="坪數分組", values="每坪單價(萬)")
    )
    # 依坪數順序排欄位
    ordered_cols = [g for g in PING_LABELS if g in pivot_data.columns]
    pivot_data = pivot_data[ordered_cols]

    fig_heat = px.imshow(
        pivot_data,
        text_auto=".1f",
        color_continuous_scale="YlOrRd",
        title="各區 × 坪數分組 平均每坪單價（萬）",
        labels={"color": "萬/坪"},
        aspect="auto",
    )
    fig_heat.update_layout(height=380)
    st.plotly_chart(fig_heat, use_container_width=True)

    # 區域統計表
    st.subheader("區域統計明細")
    display_stats = district_stats.copy()
    display_stats.columns = ["行政區", "平均單價(萬)", "成交筆數", "標準差", "中位數(萬)"]
    for col in ["平均單價(萬)", "標準差", "中位數(萬)"]:
        display_stats[col] = display_stats[col].round(1)
    st.dataframe(display_stats, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# Tab 2：坪數分析
# ═══════════════════════════════════════════════════════════
with tab2:
    st.subheader("各坪數分組價格與成交分析")

    col_a, col_b = st.columns(2)

    # 各分組單價箱型圖（依坪數順序）
    with col_a:
        valid_price_ord = valid_price.copy()
        valid_price_ord["坪數分組"] = pd.Categorical(
            valid_price_ord["坪數分組"], categories=PING_LABELS, ordered=True
        )
        fig_box_ping = px.box(
            valid_price_ord.sort_values("坪數分組"),
            x="坪數分組", y="每坪單價(萬)",
            color="坪數分組",
            category_orders={"坪數分組": PING_LABELS},
            title="各坪數分組每坪單價分布",
            labels={"每坪單價(萬)": "每坪單價 (萬/坪)", "坪數分組": ""},
            points="outliers",
        )
        fig_box_ping.update_layout(showlegend=False, height=430)
        st.plotly_chart(fig_box_ping, use_container_width=True)

    # 各分組成交量
    with col_b:
        ping_vol = (
            df.groupby("坪數分組").size()
            .reindex(PING_LABELS, fill_value=0)
            .reset_index(name="成交筆數")
        )
        fig_ping_vol = px.bar(
            ping_vol,
            x="坪數分組", y="成交筆數",
            color="成交筆數",
            color_continuous_scale="Teal",
            text="成交筆數",
            title="各坪數分組成交量",
            labels={"坪數分組": "", "成交筆數": "成交筆數"},
            category_orders={"坪數分組": PING_LABELS},
        )
        fig_ping_vol.update_traces(textposition="outside")
        fig_ping_vol.update_layout(coloraxis_showscale=False, height=430)
        st.plotly_chart(fig_ping_vol, use_container_width=True)

    # 散佈圖：坪數 vs 總價（顏色代表坪數分組）
    st.subheader("坪數 vs 成交總價散佈圖")
    sel_ping_scatter = st.multiselect(
        "選擇坪數分組（散佈圖）", ping_groups,
        default=ping_groups,
        key="scatter_ping",
    )
    scatter_df = df[df["坪數分組"].isin(sel_ping_scatter)] if sel_ping_scatter else df

    fig_scatter = px.scatter(
        scatter_df[scatter_df["每坪單價(萬)"] > 0],
        x="總坪數", y="成交總價(萬)",
        color="坪數分組",
        size="每坪單價(萬)",
        category_orders={"坪數分組": PING_LABELS},
        hover_data=["行政區", "建案", "每坪單價(萬)", "交易日期"],
        title="坪數 vs 成交總價（顏色=坪數分組，大小=每坪單價）",
        labels={"總坪數": "總坪數 (坪)", "成交總價(萬)": "成交總價 (萬)"},
        opacity=0.7,
    )
    fig_scatter.update_layout(height=450)
    st.plotly_chart(fig_scatter, use_container_width=True)

    # 坪數分組價格區間統計表
    st.subheader("坪數分組價格區間統計")
    ping_stats = (
        valid_price.groupby("坪數分組")["每坪單價(萬)"]
        .agg(
            成交筆數="count",
            平均單價="mean",
            中位數="median",
            最低="min",
            最高="max",
            標準差="std",
            Q25=lambda x: x.quantile(0.25),
            Q75=lambda x: x.quantile(0.75),
        )
        .reindex(PING_LABELS)
        .reset_index()
    )
    for c in ping_stats.columns[1:]:
        ping_stats[c] = ping_stats[c].round(1)
    st.dataframe(ping_stats, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# Tab 3：成交趨勢
# ═══════════════════════════════════════════════════════════
with tab3:
    st.subheader("月度成交趨勢")

    # 過濾有效日期
    df_trend = df[df["交易日期"].notna()].copy()
    df_trend["年月_dt"] = df_trend["交易日期"].dt.to_period("M").dt.to_timestamp()

    # 月度成交量
    monthly_vol = (
        df_trend.groupby("年月_dt")
        .agg(成交筆數=("每坪單價(萬)", "count"), 平均單價=("每坪單價(萬)", "mean"))
        .reset_index()
    )
    monthly_vol = monthly_vol[monthly_vol["年月_dt"] >= "2026-01-01"]

    col_a, col_b = st.columns(2)

    with col_a:
        fig_vol = px.bar(
            monthly_vol,
            x="年月_dt", y="成交筆數",
            text="成交筆數",
            color="成交筆數",
            color_continuous_scale="Blues",
            title="月度成交量（2026 Q1）",
            labels={"年月_dt": "月份", "成交筆數": "成交筆數"},
        )
        fig_vol.update_traces(textposition="outside")
        fig_vol.update_layout(coloraxis_showscale=False, xaxis_tickformat="%Y/%m", height=380)
        st.plotly_chart(fig_vol, use_container_width=True)

    with col_b:
        fig_price_trend = px.line(
            monthly_vol,
            x="年月_dt", y="平均單價",
            markers=True,
            title="月度平均每坪單價趨勢（2026 Q1）",
            labels={"年月_dt": "月份", "平均單價": "平均單價 (萬/坪)"},
        )
        fig_price_trend.update_layout(xaxis_tickformat="%Y/%m", height=380)
        st.plotly_chart(fig_price_trend, use_container_width=True)

    # 各區 × 月 成交量堆疊圖
    st.subheader("各區月度成交量（2026 Q1）")
    monthly_district = (
        df_trend[df_trend["年月_dt"] >= "2026-01-01"]
        .groupby(["年月_dt", "行政區"])
        .size()
        .reset_index(name="成交筆數")
    )
    fig_stack = px.bar(
        monthly_district,
        x="年月_dt", y="成交筆數",
        color="行政區",
        barmode="stack",
        title="各行政區月度成交量",
        labels={"年月_dt": "月份", "成交筆數": "成交筆數"},
    )
    fig_stack.update_layout(xaxis_tickformat="%Y/%m", height=420)
    st.plotly_chart(fig_stack, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# Tab 4：競品建案比較
# ═══════════════════════════════════════════════════════════
with tab4:
    st.subheader("競品建案比較")
    st.caption("篩選同區域、同坪數的建案，快速比較市場定位")

    cc1, cc2 = st.columns(2)
    with cc1:
        comp_district = st.selectbox("選擇行政區", ["全部"] + districts, key="comp_dist")
    with cc2:
        comp_ping_group = st.selectbox("選擇坪數分組", ["全部"] + ping_groups, key="comp_ping_grp")

    comp_df = df[df["建案"] != "無登錄建案"].copy()
    if comp_district != "全部":
        comp_df = comp_df[comp_df["行政區"] == comp_district]
    if comp_ping_group != "全部":
        comp_df = comp_df[comp_df["坪數分組"] == comp_ping_group]

    if comp_df.empty:
        st.info("此條件下無登錄建案名稱的資料，請調整篩選條件")
    else:
        project_stats = (
            comp_df[comp_df["每坪單價(萬)"] > 0]
            .groupby(["建案", "行政區"])
            .agg(
                成交筆數=("每坪單價(萬)", "count"),
                平均單價=("每坪單價(萬)", "mean"),
                最低單價=("每坪單價(萬)", "min"),
                最高單價=("每坪單價(萬)", "max"),
                平均坪數=("總坪數", "mean"),
                平均總價=("成交總價(萬)", "mean"),
            )
            .reset_index()
            .sort_values("平均單價", ascending=False)
        )
        for c in ["平均單價", "最低單價", "最高單價", "平均坪數", "平均總價"]:
            project_stats[c] = project_stats[c].round(1)

        # 建案平均單價橫向條圖
        fig_proj = px.bar(
            project_stats.head(20),
            x="平均單價", y="建案",
            orientation="h",
            color="行政區",
            text=project_stats.head(20)["平均單價"].apply(lambda x: f"{x:.1f}"),
            error_x=project_stats.head(20).apply(
                lambda r: (r["最高單價"] - r["最低單價"]) / 2, axis=1
            ),
            title="建案平均每坪單價比較（TOP 20）",
            labels={"平均單價": "平均單價 (萬/坪)", "建案": ""},
            hover_data={"成交筆數": True, "最低單價": True, "最高單價": True, "平均總價": True},
        )
        fig_proj.update_traces(textposition="outside")
        fig_proj.update_layout(yaxis_autorange="reversed", height=max(400, len(project_stats.head(20)) * 28))
        st.plotly_chart(fig_proj, use_container_width=True)

        st.subheader("建案明細表")
        st.dataframe(project_stats, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# Tab 5：異常交易
# ═══════════════════════════════════════════════════════════
with tab5:
    st.subheader("異常交易標記")

    df_abnormal = df_all[df_all["異常交易"] | df_all["單價異常"]].copy()

    if df_abnormal.empty:
        st.success("在全部資料中未發現異常交易")
    else:
        a1, a2 = st.columns(2)
        with a1:
            st.metric("親友/特殊關係交易", f"{df_all['異常交易'].sum()} 筆",
                      delta="建議排除，避免干擾市場行情")
        with a2:
            st.metric("單價異常值（<5 或 >200萬）", f"{df_all['單價異常'].sum()} 筆",
                      delta="可能為筆誤或特殊案件")

        # 分類標示
        df_abnormal["異常類型"] = ""
        df_abnormal.loc[df_abnormal["異常交易"], "異常類型"] += "親友/特殊關係 "
        df_abnormal.loc[df_abnormal["單價異常"], "異常類型"] += "單價異常"
        df_abnormal["異常類型"] = df_abnormal["異常類型"].str.strip()

        display_cols = ["行政區", "交易日期", "坪數分組", "總坪數", "成交總價(萬)",
                        "每坪單價(萬)", "建案", "異常類型", "備註"]
        display_cols = [c for c in display_cols if c in df_abnormal.columns]
        st.dataframe(
            df_abnormal[display_cols].sort_values("交易日期", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.info(
            "**注意事項**：親友/特殊關係交易因成交價格偏離市場，"
            "建議分析市場行情時從篩選器勾選「隱藏異常交易」排除。"
        )


# ═══════════════════════════════════════════════════════════
# Tab 6：全部資料 & 匯出
# ═══════════════════════════════════════════════════════════
with tab6:
    st.subheader("全部篩選後資料")

    # 排序選項
    sort_col = st.selectbox(
        "排序依據",
        ["交易日期", "每坪單價(萬)", "成交總價(萬)", "總坪數", "行政區"],
        key="sort_col",
    )
    sort_asc = st.radio("排序方式", ["降序", "升序"], horizontal=True, key="sort_asc") == "升序"

    df_display = df.sort_values(sort_col, ascending=sort_asc)

    display_cols = [
        "交易類型", "行政區", "交易日期", "建案", "地址",
        "建物型態", "移轉層次", "總樓層", "坪數分組", "總坪數",
        "成交總價(萬)", "車位總價(萬)", "每坪單價(萬)",
        "含車位", "車位類別", "備註",
    ]
    # 只顯示存在的欄位
    display_cols = [c for c in display_cols if c in df_display.columns]

    st.dataframe(
        df_display[display_cols].style.apply(
            lambda row: ["background-color: #fff3cd; color: #000000" if row.get("備註", "") else "" for _ in row],
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"共 {len(df_display):,} 筆資料")

    # CSV 下載
    csv_bytes = df_display[display_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 下載篩選後資料（CSV）",
        data=csv_bytes,
        file_name="高雄房產分析_篩選結果.csv",
        mime="text/csv",
    )

    # 分析報告摘要
    st.divider()
    st.subheader("📋 分析報告摘要")

    top_district = district_stats.iloc[0]["行政區"]
    top_price = district_stats.iloc[0]["平均單價"]
    low_district = district_stats.iloc[-1]["行政區"]
    low_price = district_stats.iloc[-1]["平均單價"]

    ping_price_rank = (
        valid_price.groupby("坪數分組")["每坪單價(萬)"].mean()
        .reindex(PING_LABELS).dropna()
    )
    top_ping_group = ping_price_rank.idxmax() if not ping_price_rank.empty else "—"
    most_traded_ping = df["坪數分組"].value_counts().index[0] if not df.empty else "—"
    most_traded_district = df["行政區"].value_counts().index[0] if not df.empty else "—"
    abnormal_pct = df_all["異常交易"].mean() * 100

    report_md = f"""
### 高雄房產成交分析摘要報告

**資料概況**
- 分析筆數：{len(df):,} 筆（篩選後）／全部 {len(df_all):,} 筆
- 資料期間：{df_all['交易日期'].min().strftime('%Y-%m-%d')} ~ {df_all['交易日期'].max().strftime('%Y-%m-%d')}
- 異常交易：{df_all['異常交易'].sum()} 筆（佔 {abnormal_pct:.1f}%）

**價格分析（每坪單價）**
- 整體平均：{valid_price['每坪單價(萬)'].mean():.1f} 萬/坪
- 整體中位數：{valid_price['每坪單價(萬)'].median():.1f} 萬/坪
- 最高均價行政區：**{top_district}** ({top_price:.1f} 萬/坪)
- 最低均價行政區：**{low_district}** ({low_price:.1f} 萬/坪)

**交易熱度**
- 最多成交行政區：**{most_traded_district}**（{df['行政區'].value_counts().iloc[0] if not df.empty else 0} 筆）
- 最熱門坪數分組：**{most_traded_ping}**（{df['坪數分組'].value_counts().iloc[0] if not df.empty else 0} 筆）
- 最高均價坪數分組：**{top_ping_group}**

**建議**
- {top_district}{"、" + district_stats.iloc[1]["行政區"] if len(district_stats) > 1 else ""} 為高單價核心區，適合訴求精品客群
- {most_traded_district} 成交量最活躍，市場流動性佳，競爭也最激烈
- 建議優先排除異常交易後進行行情分析，避免數字失真
"""
    st.markdown(report_md)

    report_bytes = report_md.encode("utf-8")
    st.download_button(
        label="📄 下載分析報告（TXT）",
        data=report_bytes,
        file_name="高雄房產分析報告.txt",
        mime="text/plain",
    )
