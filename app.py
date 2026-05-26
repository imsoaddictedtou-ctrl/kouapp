from pathlib import Path
from datetime import date
from html import escape
import streamlit as st
from PIL import Image
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scraper

# ── ページ設定 ────────────────────────────────
_icon_path = Path(__file__).parent / "icon.png"
_page_icon = Image.open(_icon_path) if _icon_path.exists() else "📊"

st.set_page_config(
    page_title="秘書コウ - 高配当株分析",
    page_icon=_page_icon,
    layout="wide",
)

# カラーパレット（最大5社）
COLORS = ["#E05252", "#4C9BE8", "#4CAF7D", "#F5A623", "#9B59B6"]

# ── CSS ──────────────────────────────────────
st.markdown("""
<style>
.kpi-card {
    background: #fff;
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    border-left: 5px solid #ccc;
}
.kpi-label { font-size: 13px; color: #666; margin-bottom: 4px; }
.kpi-value { font-size: 28px; font-weight: 700; }
.kpi-sub   { font-size: 12px; color: #888; margin-top: 4px; }
.trend-up   { color: #4CAF7D; }
.trend-down { color: #E05252; }
.summary-box {
    background: #FFF9E6;
    border: 1px solid #F5C842;
    border-radius: 10px;
    padding: 16px 20px;
}
</style>
""", unsafe_allow_html=True)


# ── ヘルパー関数 ────────────────────────────
def trend_icon(values: list) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return "―"
    diff = vals[-1] - vals[0]
    pct = diff / abs(vals[0]) * 100 if vals[0] != 0 else 0
    if pct > 5:
        return "🟢 右肩上がり"
    elif pct < -5:
        return "🔴 減少傾向"
    else:
        return "🟡 横ばい"


def _sort_pairs(years: list, vals: list) -> tuple:
    """年度と値のペアを年度順にソートして返す。"""
    pairs = [(y, v) for y, v in zip(years, vals) if v is not None]
    pairs.sort(key=lambda x: x[0].replace("予", "").replace("（予）", ""))
    if not pairs:
        return [], []
    ys, vs = zip(*pairs)
    return list(ys), list(vs)


def _global_year_order(datasets: list[dict]) -> list[str]:
    """全社の年度を収集してソートした共通カテゴリリストを返す。"""
    all_years = set()
    for d in datasets:
        for y, v in zip(d["years"], d["values"]):
            if v is not None:
                all_years.add(y)
    return sorted(all_years, key=lambda x: x.replace("予", "").replace("（予）", ""))


def make_line_chart(datasets: list[dict], title: str, yaxis_label: str) -> go.Figure:
    """複数社の折れ線グラフを作成。datasets = [{"name":..,"years":..,"values":..,"color":..}]"""
    fig = go.Figure()
    category_order = _global_year_order(datasets)
    for d in datasets:
        ys, vs = _sort_pairs(d["years"], d["values"])
        if not ys:
            continue
        fig.add_trace(go.Scatter(
            x=ys, y=vs,
            mode="lines+markers",
            name=d["name"],
            line=dict(color=d["color"], width=2.5),
            marker=dict(size=6),
        ))
    fig.update_layout(
        title=title,
        xaxis=dict(
            title="会計年度",
            categoryorder="array",
            categoryarray=category_order,
        ),
        yaxis_title=yaxis_label,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="white",
        margin=dict(l=50, r=20, t=60, b=40),
        height=320,
    )
    return fig


def make_bar_chart(datasets: list[dict], title: str, yaxis_label: str) -> go.Figure:
    """配当金棒グラフ。"""
    fig = go.Figure()
    category_order = _global_year_order(datasets)
    for d in datasets:
        ys, vs = _sort_pairs(d["years"], d["values"])
        if not ys:
            continue
        fig.add_trace(go.Bar(
            x=ys, y=vs,
            name=d["name"],
            marker_color=d["color"],
            opacity=0.85,
        ))
    fig.update_layout(
        title=title,
        xaxis=dict(
            title="会計年度",
            categoryorder="array",
            categoryarray=category_order,
        ),
        yaxis_title=yaxis_label,
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="white",
        margin=dict(l=50, r=20, t=60, b=40),
        height=320,
    )
    return fig


def _normalize_year(y: str) -> str:
    """'2010年3月' や '2010/03' や '2010年3月予' を '2010/03' に統一する。"""
    import re
    y = y.replace("予", "").replace("（予）", "").strip()
    m = re.match(r"(\d{4})年(\d{1,2})月", y)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}"
    m = re.match(r"(\d{4})/(\d{2})", y)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return y


def make_dividend_chart(data_list: list[dict]) -> go.Figure:
    """配当金（棒・左軸）＋配当性向（折れ線・右軸）の2軸グラフ。"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 全社の配当年度を収集してソート（x軸共通順）
    all_years: set[str] = set()
    for d in data_list:
        for dv in d.get("dividends", []):
            if dv.get("total_val") is not None:
                all_years.add(dv["year"])
    category_order = sorted(all_years, key=lambda x: x.replace("予", "").replace("（予）", ""))

    for i, d in enumerate(data_list):
        color = COLORS[i % len(COLORS)]
        name = d["company_name"]

        # ── 配当金（棒グラフ・左軸）──
        div_pairs = sorted(
            [(dv["year"], dv["total_val"]) for dv in d.get("dividends", []) if dv.get("total_val") is not None],
            key=lambda x: x[0].replace("予", "").replace("（予）", ""),
        )
        if div_pairs:
            dy, dv_vals = zip(*div_pairs)
            fig.add_trace(
                go.Bar(x=list(dy), y=list(dv_vals), name=f"{name} 配当金",
                       marker_color=color, opacity=0.75),
                secondary_y=False,
            )

        # ── 配当性向（折れ線・右軸）= 配当金 ÷ EPS × 100 ──
        eps_map = {_normalize_year(r["year"]): r["eps_val"] for r in d.get("results", []) if r.get("eps_val") not in (None, 0)}
        payout_pairs = []
        for dv in d.get("dividends", []):
            yr = dv["year"]
            total_val = dv.get("total_val")
            eps_val = eps_map.get(_normalize_year(yr))
            if total_val is not None and eps_val:
                payout = round(total_val / eps_val * 100, 1)
                if 0 < payout < 200:   # 異常値除外
                    payout_pairs.append((yr, payout))
        payout_pairs.sort(key=lambda x: x[0].replace("予", "").replace("（予）", ""))
        if payout_pairs:
            py, pv = zip(*payout_pairs)
            fig.add_trace(
                go.Scatter(x=list(py), y=list(pv), name=f"{name} 配当性向",
                           mode="lines+markers",
                           line=dict(color=color, width=2, dash="dot"),
                           marker=dict(size=5, symbol="diamond")),
                secondary_y=True,
            )

    fig.update_layout(
        title="配当金の推移 ／ 配当性向",
        xaxis=dict(title="会計年度", categoryorder="array", categoryarray=category_order),
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="white",
        margin=dict(l=50, r=60, t=60, b=40),
        height=340,
    )
    fig.update_yaxes(title_text="配当金（円）", secondary_y=False)
    fig.update_yaxes(title_text="配当性向（%）", secondary_y=True, showgrid=False)
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 0.2) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def make_radar_chart(companies: list[dict]) -> go.Figure:
    """総合比較レーダーチャート。"""
    categories = ["配当利回り", "ROE", "自己資本比率", "EPS成長", "配当成長"]
    fig = go.Figure()

    for i, c in enumerate(companies):
        data = c.get("radar_values", [0, 0, 0, 0, 0])
        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Scatterpolar(
            r=data + [data[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=c["company_name"],
            line_color=color,
            fillcolor=_hex_to_rgba(color, 0.2),
            opacity=0.9,
        ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100]),
            bgcolor="#f8f9fa",
        ),
        title="総合比較（レーダーチャート）<br><sub>各指標の最高値=100%として正規化</sub>",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        paper_bgcolor="white",
        height=380,
        margin=dict(l=60, r=60, t=80, b=60),
    )
    return fig


def calc_radar_values(data_list: list[dict]) -> list[dict]:
    """レーダーチャート用に各指標を0〜100に正規化。"""
    def safe_float(s):
        if not s or s == "不明":
            return None
        try:
            return float(str(s).replace("%", "").replace("円", "").replace("倍", "").replace(",", ""))
        except Exception:
            return None

    metrics = []
    for d in data_list:
        dy = safe_float(d.get("dividend_yield"))
        roe = safe_float(d.get("roe"))
        eq  = safe_float(d.get("equity_ratio"))
        # EPS成長率（最新/最古）
        eps_vals = [r["eps_val"] for r in d.get("results", []) if r.get("eps_val") is not None]
        eps_growth = None
        if len(eps_vals) >= 2:
            eps_growth = (eps_vals[-1] / abs(eps_vals[0]) * 100) if eps_vals[0] != 0 else None
        # 配当成長率
        div_vals = [dv["total_val"] for dv in d.get("dividends", []) if dv.get("total_val") is not None]
        div_growth = None
        if len(div_vals) >= 2:
            div_growth = (div_vals[-1] / div_vals[0] * 100) if div_vals[0] != 0 else None

        metrics.append({
            "dy": dy or 0,
            "roe": roe or 0,
            "eq": eq or 0,
            "eps_g": max(0, min(eps_growth or 0, 500)),
            "div_g": max(0, min(div_growth or 0, 500)),
        })

    # 正規化（各指標の最大値を100とする）
    keys = ["dy", "roe", "eq", "eps_g", "div_g"]
    maxvals = {}
    for k in keys:
        vals = [m[k] for m in metrics if m[k] > 0]
        maxvals[k] = max(vals) if vals else 1

    result = []
    for i, (d, m) in enumerate(zip(data_list, metrics)):
        normalized = [
            round(m["dy"]  / maxvals["dy"]  * 100) if maxvals["dy"]  > 0 else 0,
            round(m["roe"] / maxvals["roe"] * 100) if maxvals["roe"] > 0 else 0,
            round(m["eq"]  / maxvals["eq"]  * 100) if maxvals["eq"]  > 0 else 0,
            round(m["eps_g"] / maxvals["eps_g"] * 100) if maxvals["eps_g"] > 0 else 0,
            round(m["div_g"] / maxvals["div_g"] * 100) if maxvals["div_g"] > 0 else 0,
        ]
        result.append({**d, "radar_values": normalized})
    return result


def calc_dividend_policy(d: dict) -> dict:
    """直近10年の配当履歴から配当方針を自動判定する。"""
    import re

    dividends = d.get("dividends", [])
    # 年度順にソートして直近10年分を取得
    sorted_divs = sorted(
        [dv for dv in dividends if dv.get("total_val") is not None],
        key=lambda x: x["year"].replace("予", "").replace("（予）", ""),
    )
    recent = sorted_divs[-10:] if len(sorted_divs) >= 2 else sorted_divs
    vals = [dv["total_val"] for dv in recent]

    # ── 累進配当判定 ──
    cuts = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
    if cuts == 0:
        prog_label = "🟢 累進配当"
        prog_note  = f"直近{len(vals)}年間 減配なし"
    elif cuts <= 2:
        prog_label = "🟡 ほぼ維持"
        prog_note  = f"直近{len(vals)}年間で{cuts}回減配"
    else:
        prog_label = "🔴 業績連動型"
        prog_note  = f"直近{len(vals)}年間で{cuts}回減配"

    # ── 連続増配年数（直近から遡る）──
    streak = 0
    for a, b in zip(reversed(vals), list(reversed(vals))[1:]):
        if a > b:
            streak += 1
        else:
            break

    # ── DOE実績（配当金 ÷ BPS × 100）──
    doe_str = "不明"
    div_amt_raw = d.get("dividend_amount", "不明")
    bps_raw     = d.get("bps", "不明")
    try:
        div_amt = float(re.sub(r"[^\d\.]", "", div_amt_raw)) if div_amt_raw != "不明" else None
        bps_val = float(re.sub(r"[^\d\.]", "", bps_raw))     if bps_raw     != "不明" else None
        if div_amt and bps_val and bps_val > 0:
            doe_str = f"{div_amt / bps_val * 100:.1f}%"
    except Exception:
        pass

    return {
        "prog_label": prog_label,
        "prog_note":  prog_note,
        "streak":     streak,
        "doe":        doe_str,
        "years":      len(vals),
    }


def render_dividend_policy(data_list: list[dict]):
    """配当方針サマリーセクションを表示。"""
    st.markdown("### 📋 配当方針サマリー（直近10年）")
    cols = st.columns(len(data_list))
    for i, (col, d) in enumerate(zip(cols, data_list)):
        color  = COLORS[i % len(COLORS)]
        name   = d.get("company_name", "")
        policy = calc_dividend_policy(d)
        with col:
            st.markdown(f"""
<div class="kpi-card" style="border-left-color:{color}">
  <div class="kpi-label" style="font-weight:600;color:{color};">{escape(name)}</div>
  <div style="font-size:18px;font-weight:700;margin:8px 0;">{policy['prog_label']}</div>
  <div class="kpi-sub">{policy['prog_note']}</div>
  <div style="margin-top:10px;display:flex;gap:16px;">
    <div>
      <div class="kpi-sub">連続増配</div>
      <div style="font-size:20px;font-weight:700;">{policy['streak']}年</div>
    </div>
    <div>
      <div class="kpi-sub">DOE実績</div>
      <div style="font-size:20px;font-weight:700;">{policy['doe']}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_kpi_cards(data_list: list[dict]):
    """KPIサマリーカードを横並びで表示。"""
    cols = st.columns(len(data_list))
    for i, (col, d) in enumerate(zip(cols, data_list)):
        color = COLORS[i % len(COLORS)]
        name = d.get("company_name", "")
        code = d.get("code", "")
        price = d.get("stock_price", "不明")
        dy = d.get("dividend_yield", "不明")
        div_amt = d.get("dividend_amount", "不明")
        roe = d.get("roe", "不明")
        eq = d.get("equity_ratio", "不明")
        results = d.get("results", [])
        valid_results = [r for r in results if r.get("net_profit") not in (None, "不明", "-")]
        latest_profit = valid_results[-1]["net_profit"] if valid_results else "不明"
        latest_year = valid_results[-1]["year"] if valid_results else "不明"
        sector = d.get("sector", "不明")
        sector_type = d.get("sector_type", "不明")
        sector_type_badge = {
            "ディフェンシブ": ("🛡️", "#4CAF7D"),
            "景気敏感":       ("⚡", "#F5A623"),
            "金融":           ("🏦", "#4C9BE8"),
            "中間":           ("➡️", "#9B59B6"),
        }.get(sector_type, ("❓", "#aaa"))
        with col:
            st.markdown(f"""
<div class="kpi-card" style="border-left-color:{color}">
  <div class="kpi-label">{escape(name)}（{escape(code)}）</div>
  <div style="margin:4px 0 8px;">
    <span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;font-size:12px;color:#555;">{escape(sector)}</span>
    <span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;font-size:12px;color:{sector_type_badge[1]};margin-left:4px;font-weight:600;">{sector_type_badge[0]} {escape(sector_type)}</span>
  </div>
  <div class="kpi-value" style="color:{color}">純利益 {escape(latest_profit)}</div>
  <div class="kpi-sub">
    ROE {escape(roe)} ／ 配当 {escape(div_amt)} ／ 自己資本比率 {escape(eq)}
  </div>
  <div class="kpi-sub" style="margin-top:6px;color:#aaa;">📅 {escape(latest_year)} 時点</div>
</div>
""", unsafe_allow_html=True)


def render_charts(data_list: list[dict]):
    """グラフセクションを表示。"""
    years_per = []
    for d in data_list:
        years_per.append([r["year"] for r in d.get("results", [])])

    # 収益・営業利益グラフ
    col1, col2 = st.columns(2)
    with col1:
        datasets = [
            {"name": d["company_name"],
             "years": [r["year"] for r in d.get("results", [])],
             "values": [r["revenue_val"] for r in d.get("results", [])],
             "color": COLORS[i % len(COLORS)]}
            for i, d in enumerate(data_list)
        ]
        st.plotly_chart(make_line_chart(datasets, "売上収益の推移", "億円"), width="stretch")

    with col2:
        datasets = [
            {"name": d["company_name"],
             "years": [r["year"] for r in d.get("results", [])],
             "values": [r["net_profit_val"] for r in d.get("results", [])],
             "color": COLORS[i % len(COLORS)]}
            for i, d in enumerate(data_list)
        ]
        st.plotly_chart(make_line_chart(datasets, "純利益の推移", "億円"), width="stretch")

    # 配当金推移・ROE推移
    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(make_dividend_chart(data_list), width="stretch")

    with col4:
        datasets = [
            {"name": d["company_name"],
             "years": [r["year"] for r in d.get("results", [])],
             "values": [r["roe_val"] for r in d.get("results", [])],
             "color": COLORS[i % len(COLORS)]}
            for i, d in enumerate(data_list)
        ]
        st.plotly_chart(make_line_chart(datasets, "ROEの推移", "%"), width="stretch")

    # EPS推移・レーダーチャート
    col5, col6 = st.columns(2)
    with col5:
        datasets = [
            {"name": d["company_name"],
             "years": [r["year"] for r in d.get("results", [])],
             "values": [r["eps_val"] for r in d.get("results", [])],
             "color": COLORS[i % len(COLORS)]}
            for i, d in enumerate(data_list)
        ]
        st.plotly_chart(make_line_chart(datasets, "EPS（1株当たり利益）の推移", "円"), width="stretch")

    with col6:
        if len(data_list) >= 1:
            radar_data = calc_radar_values(data_list)
            st.plotly_chart(make_radar_chart(radar_data), width="stretch")


def render_trend_summary(data_list: list[dict]):
    """トレンドまとめと財務指標テーブルを表示。"""
    st.markdown("---")
    if len(data_list) > 1:
        st.markdown("### 📌 主要指標 比較テーブル")
        rows = []
        for d in data_list:
            rev_vals = [r["revenue_val"] for r in d.get("results", [])]
            eps_vals = [r["eps_val"] for r in d.get("results", [])]
            div_vals = [dv["total_val"] for dv in d.get("dividends", [])]
            rows.append({
                "会社名": f"{d['company_name']}（{d['code']}）",
                "株価": d.get("stock_price", "不明"),
                "配当利回り": d.get("dividend_yield", "不明"),
                "PER": d.get("per", "不明"),
                "PBR": d.get("pbr", "不明"),
                "ROE": d.get("roe", "不明"),
                "自己資本比率": d.get("equity_ratio", "不明"),
                "EPS": d.get("eps", "不明"),
                "売上トレンド": trend_icon(rev_vals),
                "EPS トレンド": trend_icon(eps_vals),
                "配当トレンド": trend_icon(div_vals),
            })
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        d = data_list[0]
        rev_vals = [r["revenue_val"] for r in d.get("results", [])]
        eps_vals = [r["eps_val"] for r in d.get("results", [])]
        div_vals = [dv["total_val"] for dv in d.get("dividends", [])]
        st.markdown("### 📌 財務指標サマリー")
        c1, c2, c3 = st.columns(3)
        metrics = [
            ("株価", d.get("stock_price"), None),
            ("配当利回り（予）", d.get("dividend_yield"), None),
            ("配当金（予）", d.get("dividend_amount"), None),
            ("PER（予）", d.get("per"), None),
            ("PBR", d.get("pbr"), None),
            ("ROE（予）", d.get("roe"), None),
            ("EPS（予）", d.get("eps"), None),
            ("自己資本比率", d.get("equity_ratio"), None),
            ("時価総額", d.get("market_cap"), None),
        ]
        for j, (label, val, _) in enumerate(metrics):
            [c1, c2, c3][j % 3].metric(label, val or "不明")

        st.markdown("#### トレンド評価")
        tc1, tc2, tc3 = st.columns(3)
        tc1.metric("売上高", trend_icon(rev_vals))
        tc2.metric("EPS", trend_icon(eps_vals))
        tc3.metric("配当金", trend_icon(div_vals))


# ── セッション状態初期化 ────────────────────
for key in ["data_list", "candidates", "pending_idx"]:
    if key not in st.session_state:
        st.session_state[key] = None


# ── サイドバー ────────────────────────────
with st.sidebar:
    st.divider()

    st.markdown("### 分析する企業を入力")
    st.caption("社名または証券コードを入力（最大5社）")

    inputs = []
    for i in range(5):
        val = st.text_input(
            f"企業 {i+1}",
            placeholder="例：三菱商事 / 8058",
            key=f"input_{i}",
            label_visibility="collapsed" if i > 0 else "visible",
        )
        if val.strip():
            inputs.append(val.strip())

    analyze_btn = st.button("🔍 分析開始", type="primary", width="stretch")
    st.divider()
    st.markdown("**使い方**")
    st.markdown("- 1社：個別分析\n- 2〜5社：比較分析\n- 同セクターを並べるとより効果的！")


# ── メインコンテンツ ──────────────────────
_illust_path = Path(__file__).parent / "kou_illust.png"

# タイトルエリア（アイコン／テキスト／イラスト）
col_logo, col_title, col_illust = st.columns([1, 8, 2])
with col_logo:
    if _icon_path.exists():
        st.image(str(_icon_path), width=56)
with col_title:
    if st.session_state.data_list and len(st.session_state.data_list) > 0:
        names = "・".join([d["company_name"] for d in st.session_state.data_list])
        codes = " / ".join([d["code"] for d in st.session_state.data_list])
        st.markdown(f"## {names} 財務分析レポート")
        st.caption(f"証券コード：{codes}　｜　データ出典：IRバンク　｜　作成日：{date.today().strftime('%Y年%m月%d日')}")
    else:
        st.markdown("## 高配当株 財務分析ダッシュボード")
with col_illust:
    if _illust_path.exists():
        st.image(str(_illust_path), width=220)
        st.caption("by 秘書コウ ｜ データソース：IRバンク ｜ 追加料金不要")

st.divider()

# 分析開始
if analyze_btn and inputs:
    st.session_state.data_list = None
    st.session_state.candidates = None

    collected = []
    errors = []

    progress = st.progress(0, text="データ取得中...")
    for idx, query in enumerate(inputs):
        progress.progress((idx + 1) / len(inputs), text=f"「{query}」を取得中...")
        result = scraper.scrape_all(query)

        if result.get("multiple"):
            # 複数候補 → 最初の候補を自動選択（サイドバーで絞り込んでもらう想定）
            st.warning(f"「{query}」は複数ヒットしました。最初の候補「{result['candidates'][0]['name']}」を使用します。別の企業の場合は証券コードで入力してください。")
            result2 = scraper.scrape_all(result["candidates"][0]["code"])
            if result2.get("listed"):
                collected.append(result2)
        elif result.get("listed"):
            collected.append(result)
        else:
            errors.append(result.get("error", f"「{query}」は取得できませんでした。"))

    progress.empty()

    for e in errors:
        st.error(e)

    if collected:
        st.session_state.data_list = collected

# データ表示
if st.session_state.data_list:
    data_list = st.session_state.data_list

    # 凡例
    legend_html = "　".join([
        f'<span style="color:{COLORS[i]};font-weight:bold;">● {escape(d["company_name"])}（{escape(d["code"])}）</span>'
        for i, d in enumerate(data_list)
    ])
    st.markdown(legend_html, unsafe_allow_html=True)
    st.markdown("")

    # KPIカード
    render_kpi_cards(data_list)
    st.markdown("")

    # 配当方針サマリー
    render_dividend_policy(data_list)
    st.markdown("")

    # グラフ
    render_charts(data_list)

    # 指標テーブル・トレンド評価
    render_trend_summary(data_list)

    st.caption("※ 本レポートはIRバンクの公開データをもとに自動生成したものです。投資判断はご自身の責任で行ってください。")

    # 用語解説
    st.markdown("---")
    with st.expander("📖 用語解説（初心者向け）"):
        st.markdown("""
| 用語 | ひとことで言うと | 見方のポイント |
|---|---|---|
| **PER**（株価収益率） | 「株価が利益の何年分か」を示す指標。割高・割安の目安。 | 低いほど割安。15倍以下が目安。ただし業種により差がある。 |
| **PBR**（株価純資産倍率） | 「株価が会社の資産の何倍か」を示す指標。 | 1倍割れは理論上、解散しても株主に利益が出る状態。1倍前後が割安の目安。 |
| **ROE**（自己資本利益率） | 「株主から預かったお金をどれだけ効率よく増やせたか」。 | 8〜10%以上あると優良企業の目安。高いほど経営効率が良い。 |
| **自己資本比率** | 「会社の資産のうち、借金ではなく自分のお金の割合」。 | 40%以上で財務安定の目安。高いほど倒産リスクが低い。 |
| **EPS**（1株当たり利益） | 「株1枚あたり、会社がいくら稼いだか」。 | 右肩上がりなら業績が伸びている証拠。配当の源泉になる数字。 |
| **DOE**（株主資本配当率） | 「株主の資産に対して、配当をどれくらい払っているか」。 | 3%以上を目標とする企業が多い。DOE基準の配当方針は株価に関係なく安定しやすい。 |
""")


elif not analyze_btn:
    # 初期画面
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;color:#999;">
        <div style="font-size:64px;">📊</div>
        <div style="font-size:18px;margin-top:16px;">左のサイドバーから企業を入力して「分析開始」を押してください</div>
        <div style="font-size:14px;margin-top:8px;">1社：個別分析　／　2〜5社：比較分析（同セクター比較もできます）</div>
    </div>
    """, unsafe_allow_html=True)
