import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
import itertools

# 画面基本設定
st.set_page_config(page_title="梱包サイズ＆全発送方法一括比較システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ＆全発送方法一括比較システム")

# --- セッション状態の初期化 ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- Googleスプレッドシート連携設定 ---
SHEET_ID = "13ijkSncdvliXRxUVKVl_xglaxPHTgOD8_hdQFXgE0pc"

def clean_decimal(val) -> Decimal:
    """入力値をクリーニングして安全にDecimal型へ変換する関数"""
    if pd.isna(val):
        return Decimal('0')
    val_str = str(val).strip()
    val_str = val_str.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    val_str = val_str.replace(',', '')
    val_str = re.sub(r'[^0-9.]', '', val_str)
    
    if not val_str:
        return Decimal('0')
    try:
        return Decimal(val_str)
    except:
        return Decimal('0')

def get_sheet_url(sheet_name: str) -> str:
    encoded_name = quote(sheet_name)
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_name}"

def load_data():
    # 1. 商品マスタ
    url_items = get_sheet_url("商品マスタ")
    df_items = pd.read_csv(url_items).dropna(how="all")
    df_items.columns = df_items.columns.str.strip()
    df_items = df_items.loc[:, ~df_items.columns.duplicated()]
    df_items = df_items.set_index("商品ID")
    
    # 2. 箱マスタ
    url_boxes = get_sheet_url("箱マスタ")
    df_boxes = pd.read_csv(url_boxes).dropna(how="all")
    
    # 1. 空白列の削除と空白文字のトリム
    df_boxes = df_boxes.loc[:, df_boxes.columns.notna()]
    df_boxes.columns = df_boxes.columns.astype(str).str.strip()

    # 2. 判定キーワードによる標準列名への変換
    box_col_map = {}
    for col in df_boxes.columns:
        if "箱" in col and "名" in col:
            box_col_map[col] = "箱名称"
        elif "幅" in col:
            box_col_map[col] = "幅(cm)"
        elif "高さ" in col or "高" in col:
            box_col_map[col] = "高さ(cm)"
        elif "奥行" in col:
            box_col_map[col] = "奥行(cm)"
        elif "重" in col:
            box_col_map[col] = "箱重量(kg)"
    
    df_boxes = df_boxes.rename(columns=box_col_map)

    # 3. リネーム後に重複した列名を一元化（最初の1列のみ残す）
    df_boxes = df_boxes.loc[:, ~df_boxes.columns.duplicated(keep="first")]

    # 4. それでも同名列が残る場合の安全策（末尾に _1, _2 等を付与してユニーク化）
    cols = list(df_boxes.columns)
    counts = {}
    for i, col in enumerate(cols):
        if cols.count(col) > 1:
            counts[col] = counts.get(col, 0) + 1
            if counts[col] > 1:
                cols[i] = f"{col}_{counts[col]-1}"
    df_boxes.columns = cols

    # 3. 各ルール別送料マスタの読み込み（複数シート対応）
    shipping_masters = {}
    
    # 国内マスタ
    try:
        df_dom = pd.read_csv(get_sheet_url("ヤフオクおてがる配送(ヤマト運輸)")).dropna(how="all")
        df_dom.columns = df_dom.columns.str.strip()
        shipping_masters["🇯🇵 国内発送 (サイズ基準)"] = {"df": df_dom, "type": "dom"}
    except:
        pass

    # 海外マスタ (÷5000)
    try:
        df_intl5000 = pd.read_csv(get_sheet_url("海外送料_5000")).dropna(how="all")
        df_intl5000.columns = df_intl5000.columns.str.strip()
        shipping_masters["🌏 海外発送 (容積重量 ÷5000)"] = {"df": df_intl5000, "type": "intl", "divisor": 5000.0}
    except:
        # バックアップ用：旧「海外送料マスタ」名でも読み込み可能に
        try:
            df_intl = pd.read_csv(get_sheet_url("海外送料マスタ")).dropna(how="all")
            df_intl.columns = df_intl.columns.str.strip()
            shipping_masters["🌏 海外発送 (容積重量 ÷5000)"] = {"df": df_intl, "type": "intl", "divisor": 5000.0}
        except:
            pass

    # 海外マスタ (÷8000)
    try:
        df_intl8000 = pd.read_csv(get_sheet_url("海外送料_8000")).dropna(how="all")
        df_intl8000.columns = df_intl8000.columns.str.strip()
        shipping_masters["🌏 海外発送 (容積重量 ÷8000)"] = {"df": df_intl8000, "type": "intl", "divisor": 8000.0}
    except:
        pass

    return df_items, df_boxes, shipping_masters

try:
    df_master, df_boxes, shipping_masters = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました：")
    st.exception(e)
    st.stop()

# ==========================================
# 上部: 左右2カラム（マスタ確認＆入力フォーム）
# ==========================================
col_left, col_right = st.columns([5, 7])

# ------------------------------------------
# 左カラム: 📋 登録マスタ情報
# ------------------------------------------
with col_left:
    st.subheader("📋 登録マスタ情報")
    tabs = st.tabs(["📦 商品", "📐 箱"] + list(shipping_masters.keys()))
    
    selected_from_table = []
    with tabs[0]:
        st.caption("👈 チェックボックスを選択すると右側に反映されます")
        event = st.dataframe(df_master, use_container_width=True, on_select="rerun", selection_mode="multi-row")
        if event and event.selection and event.selection.rows:
            selected_from_table = df_master.index[event.selection.rows].tolist()

    with tabs[1]:
        st.dataframe(df_boxes, use_container_width=True)

    for i, (m_name, m_info) in enumerate(shipping_masters.items()):
        with tabs[i + 2]:
            st.dataframe(m_info["df"], use_container_width=True)
        
    if st.button("🔄 最新データに更新"):
        st.rerun()

# ------------------------------------------
# 右カラム: 🛒 注文シミュレーション設定
# ------------------------------------------
with col_right:
    st.subheader("🛒 注文シミュレーション")

    buffer_margin = st.number_input(
        "🛡️ 緩衝材マージン (全各辺加算: cm)",
        min_value=0.0, max_value=10.0, value=2.0, step=0.5,
        help="商品のまとめサイズに対して一律でこのcm数を加算して箱サイズと判定します。"
    )

    selected_ids = st.multiselect(
        "商品を選択してください", 
        options=df_master.index,
        default=selected_from_table,
        format_func=lambda x: f"{x}: {df_master.loc[x, '商品名']}"
    )

    item_quantities = {}
    if selected_ids:
        st.write("**数量設定:**")
        q_cols = st.columns(min(len(selected_ids), 3))
        for idx, item_id in enumerate(selected_ids):
            item_name = df_master.loc[item_id, '商品名']
            col_target = q_cols[idx % 3]
            qty = col_target.number_input(f"{item_name}", min_value=1, max_value=50, value=1, key=f"qty_{item_id}")
            item_quantities[item_id] = qty

    def calculate_min_bounding_box(items_list, margin):
        total_items = len(items_list)
        if total_items == 0:
            return []

        def get_orientations(w, h, d):
            return list(set(itertools.permutations([w, h, d])))

        best_bounding_boxes = []

        if len(set([it['id'] for it in items_list])) == 1:
            item_spec = items_list[0]
            w, h, d = item_spec['w'], item_spec['h'], item_spec['d']
            orientations = get_orientations(w, h, d)

            factors = []
            for x in range(1, total_items + 1):
                for y in range(1, total_items + 1):
                    for z in range(1, total_items + 1):
                        if x * y * z >= total_items:
                            factors.append((x, y, z))

            for fx, fy, fz in factors:
                for ow, oh, od in orientations:
                    raw_w = ow * fx
                    raw_h = oh * fy
                    raw_d = od * fz
                    best_bounding_boxes.append((raw_w + margin, raw_h + margin, raw_d + margin, raw_w, raw_h, raw_d))
        else:
            grid_patterns = []
            for x in range(1, total_items + 1):
                for y in range(1, total_items + 1):
                    for z in range(1, total_items + 1):
                        if x * y * z >= total_items:
                            grid_patterns.append((x, y, z))

            for gx, gy, gz in grid_patterns:
                dim_x, dim_y, dim_z = [], [], []
                for idx, it in enumerate(items_list):
                    dims = sorted([it['w'], it['h'], it['d']], reverse=True)
                    dim_x.append(dims[0]); dim_y.append(dims[1]); dim_z.append(dims[2])

                raw_w = max(dim_x) * gx; raw_h = max(dim_y) * gy; raw_d = max(dim_z) * gz

                for ow, oh, od in get_orientations(raw_w, raw_h, raw_d):
                    best_bounding_boxes.append((ow + margin, oh + margin, od + margin, ow, oh, od))

        return best_bounding_boxes

    # --- 送料計算汎用関数 ---
    def calc_carrier_cost(df_shipping, total_3sum, total_weight_kg, box_volume_cm3, rule_type, divisor=5000.0):
        results = {}
        ignore_cols = ["サイズ区分", "サイズ", "重量上限(kg)", "重量上限", "3辺合計上限(cm)", "3辺合計上限"]
        carriers = [c for c in df_shipping.columns if c not in ignore_cols]

        df_sorted = df_shipping.copy()

        if rule_type == "dom":
            size_col = next((c for c in df_sorted.columns if "サイズ" in c), None)
            weight_col = next((c for c in df_sorted.columns if "重量" in c), None)
            if not size_col: return results

            df_sorted[size_col] = df_sorted[size_col].apply(lambda x: float(clean_decimal(x)))
            if weight_col:
                df_sorted[weight_col] = df_sorted[weight_col].apply(lambda x: float(clean_decimal(x)))
            df_sorted = df_sorted.sort_values(by=size_col)

            for c in carriers:
                matched = False
                for _, row in df_sorted.iterrows():
                    sz_limit = row[size_col]
                    wt_limit = float(row[weight_col]) if weight_col else 999.0
                    if total_3sum <= sz_limit and float(total_weight_kg) <= wt_limit:
                        cost = int(clean_decimal(row[c]))
                        results[c] = {"cost": cost, "cat": f"{int(sz_limit)}サイズ", "weight_used": float(total_weight_kg)}
                        matched = True
                        break
                if not matched:
                    results[c] = {"cost": 0, "cat": "規格外", "weight_used": float(total_weight_kg)}
        else:
            volumetric_weight = box_volume_cm3 / float(divisor)
            effective_weight = max(float(total_weight_kg), volumetric_weight)

            weight_col = next((c for c in df_sorted.columns if "重量" in c), None)
            size_col = next((c for c in df_sorted.columns if "3辺" in c or "サイズ" in c), None)
            if not weight_col: return results

            df_sorted[weight_col] = df_sorted[weight_col].apply(lambda x: float(clean_decimal(x)))
            if size_col:
                df_sorted[size_col] = df_sorted[size_col].apply(lambda x: float(clean_decimal(x)))
            df_sorted = df_sorted.sort_values(by=weight_col)

            for c in carriers:
                matched = False
                for _, row in df_sorted.iterrows():
                    wt_limit = row[weight_col]
                    sz_limit = float(row[size_col]) if size_col else 999.0
                    if effective_weight <= wt_limit and total_3sum <= sz_limit:
                        cost = int(clean_decimal(row[c]))
                        results[c] = {"cost": cost, "cat": f"~{wt_limit:.1f}kg区分", "weight_used": effective_weight, "vol_weight": volumetric_weight}
                        matched = True
                        break
                if not matched:
                    results[c] = {"cost": 0, "cat": "規格外", "weight_used": effective_weight, "vol_weight": volumetric_weight}

        return results

    do_calc = st.button("🚀 推奨箱＆全ルール別送料を一括判定する", type="primary", use_container_width=True, disabled=not selected_ids)

# ==========================================
# 中部: 全計算結果を一発全表示
# ==========================================
if do_calc and selected_ids:
    items_list = []
    order_summary_list = []
    raw_items_weight = Decimal('0')

    for item_id, qty in item_quantities.items():
        row = df_master.loc[item_id]
        order_summary_list.append(f"{row['商品名']} × {qty}")
        i_weight = clean_decimal(row['重量(kg)'])
        iw, ih, id_ = float(clean_decimal(row['幅(cm)'])), float(clean_decimal(row['高さ(cm)'])), float(clean_decimal(row['奥行(cm)']))

        for _ in range(qty):
            items_list.append({'id': item_id, 'w': iw, 'h': ih, 'd': id_})
            raw_items_weight += i_weight

    bounding_candidates = calculate_min_bounding_box(items_list, margin=float(buffer_margin))
    fitted_boxes = []

    for _, box in df_boxes.iterrows():
        b_name = str(box['箱名称'])
        bw, bh, bd = float(clean_decimal(box['幅(cm)'])), float(clean_decimal(box['高さ(cm)'])), float(clean_decimal(box['奥行(cm)']))
        b_weight = clean_decimal(box['箱重量(kg)'])
        box_dims_sorted = sorted([bw, bh, bd])
        box_volume = bw * bh * bd

        for cw, ch, cd, raw_w, raw_h, raw_d in bounding_candidates:
            cand_dims_sorted = sorted([cw, ch, cd])
            if (cand_dims_sorted[0] <= box_dims_sorted[0] and
                cand_dims_sorted[1] <= box_dims_sorted[1] and
                cand_dims_sorted[2] <= box_dims_sorted[2]):
                fitted_boxes.append({
                    'volume': box_volume, 'name': b_name,
                    'box_w': bw, 'box_h': bh, 'box_d': bd, 'box_weight': b_weight,
                    'actual_w': cw, 'actual_h': ch, 'actual_d': cd,
                    'raw_w': raw_w, 'raw_h': raw_h, 'raw_d': raw_d
                })

    st.markdown("---")
    order_str = ", ".join(order_summary_list)

    if fitted_boxes:
        fitted_boxes.sort(key=lambda x: x['volume'])
        best_box = fitted_boxes[0]

        total_pack_weight = raw_items_weight + best_box['box_weight']
        box_3sum = best_box['box_w'] + best_box['box_h'] + best_box['box_d']
        box_vol = best_box['volume']

        # ------------------------------------------
        # 🎉 1. 最適な箱基本情報
        # ------------------------------------------
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")
        b_col1, b_col2, b_col3, b_col4 = st.columns(4)
        b_col1.metric("選択箱寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
        b_col2.metric("箱の3辺合計", f"{box_3sum:.1f} cm")
        b_col3.metric("梱包総重量(実寸)", f"{total_pack_weight:.2f} kg", f"商品:{raw_items_weight:.2f}kg + 箱:{best_box['box_weight']:.2f}kg")
        b_col4.metric("箱の容積", f"{box_vol/1000:.1f} L", f"{box_vol:,.0f} cm³")

        st.write("---")

        # ------------------------------------------
        # 💰 2. 全ルール別・配送会社別 送料比較一覧表（トグル無し全表示）
        # ------------------------------------------
        st.subheader("💰 全発送方法・会社別 送料一括比較結果")

        comparison_rows = []
        for rule_title, m_info in shipping_masters.items():
            rule_type = m_info["type"]
            divisor = m_info.get("divisor", 5000.0)
            df_m = m_info["df"]

            res = calc_carrier_cost(df_m, box_3sum, total_pack_weight, box_vol, rule_type, divisor)

            for carrier_name, detail in res.items():
                cost_val = detail["cost"]
                comparison_rows.append({
                    "発送区分/ルール": rule_title,
                    "配送会社/サービス": carrier_name,
                    "適用区分": detail["cat"],
                    "適用算出重量": f"{detail['weight_used']:.2f} kg",
                    "想定送料": cost_val if cost_val > 0 else 9999999  # ソート用
                })

        if comparison_rows:
            df_comp = pd.DataFrame(comparison_rows)
            df_comp_sorted = df_comp.sort_values(by="想定送料")
            
            # 最安値表示用のフォーマット調整
            df_comp_display = df_comp_sorted.copy()
            df_comp_display["想定送料"] = df_comp_display["想定送料"].apply(lambda x: f"¥{x:,}" if x < 9999999 else "規格外 / 対応なし")

            st.dataframe(df_comp_display, use_container_width=True, hide_index=True)

            # 最安値ハイライトカード
            cheapest = df_comp_sorted.iloc[0]
            if cheapest["想定送料"] < 9999999:
                st.info(f"🏆 **最安発送方法**: 【{cheapest['発送区分/ルール']} - {cheapest['配送会社/サービス']}】 ➔ **¥{cheapest['想定送料']:,}** （区分: {cheapest['適用区分']}）")

        # ------------------------------------------
        # ✂️ 3. 箱の加工提案
        # ------------------------------------------
        st.write("---")
        st.write("**✂️ 箱の加工（リサイズ）提案**")
        box_dims = {'幅': best_box['box_w'], '高さ': best_box['box_h'], '奥行': best_box['box_d']}
        item_dims = sorted([best_box['actual_w'], best_box['actual_h'], best_box['actual_d']], reverse=True)
        box_dims_sorted = sorted([(v, k) for k, v in box_dims.items()], reverse=True)

        margins = [{'name': k, 'box_val': b_val, 'item_val': i_val, 'diff': b_val - i_val}
                   for (b_val, k), i_val in zip(box_dims_sorted, item_dims)]
        margins.sort(key=lambda x: x['diff'], reverse=True)
        max_margin_edge = margins[0]

        if max_margin_edge['diff'] >= 1.0:
            st.warning(
                f"✂️ **【切り詰め加工】** 箱の **「{max_margin_edge['name']}」** を **{max_margin_edge['box_val']:.1f} cm ➔ {max_margin_edge['item_val']:.1f} cm** へ **{max_margin_edge['diff']:.1f} cm** 切り詰めると隙間を無くせます。"
            )
        else:
            st.success("✅ **加工不要**: 各辺ともジャストフィットしています。")

        # 履歴追加
        st.session_state.history.insert(0, {
            "注文内容": order_str,
            "判定箱": best_box['name'],
            "最安発送手段": f"{cheapest['配送会社/サービス']} (¥{cheapest['想定送料']:,})" if cheapest['想定送料'] < 9999999 else "なし",
            "梱包総重量": f"{total_pack_weight:.2f} kg"
        })
    else:
        st.error("⚠️ 選択した商品が入る箱が「箱マスタ」にありません。")

# ==========================================
# 下部: 📜 判定履歴
# ==========================================
st.markdown("---")
st.subheader("📜 判定履歴")
if st.session_state.history:
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
    if st.button("🗑️ 履歴をクリア"):
        st.session_state.history = []
        st.rerun()
