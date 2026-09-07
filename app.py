import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
import itertools

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（全マスタ動的同期）")

# --- セッション状態（判定履歴の保持）の初期化 ---
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
    url_items = get_sheet_url("商品マスタ")
    df_items = pd.read_csv(url_items)
    df_items = df_items.dropna(how="all")
    df_items.columns = df_items.columns.str.strip()
    df_items = df_items.loc[:, ~df_items.columns.duplicated()]
    df_items = df_items.set_index("商品ID")
    
    url_boxes = get_sheet_url("箱マスタ")
    df_boxes = pd.read_csv(url_boxes)
    df_boxes = df_boxes.dropna(how="all")
    df_boxes.columns = df_boxes.columns.str.strip()
    
    # 列名の自動吸収
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
    df_boxes = df_boxes.loc[:, ~df_boxes.columns.duplicated()]
    return df_items, df_boxes

try:
    df_master, df_boxes = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました。詳細なエラーは以下の通りです：")
    st.exception(e)
    st.stop()

# --- メイン画面 layout ---
col_left, col_right = st.columns([1, 1])

# 左側：マスタ確認
with col_left:
    st.subheader("📋 登録マスタ情報")
    tab1, tab2 = st.tabs(["📦 商品マスタ", "📐 箱マスタ"])
    
    with tab1:
        st.dataframe(df_master, use_container_width=True)
    with tab2:
        st.dataframe(df_boxes, use_container_width=True)
        
    if st.button("🔄 最新データに更新"):
        st.rerun()

# 右側：シミュレーション実行
with col_right:
    st.subheader("🛒 注文シミュレーション")
    
    # --- 緩衝材マージンの設定条件 ---
    buffer_margin = st.number_input(
        "🛡️ 緩衝材マージン (まとめた商品サイズの全各辺に加算する厚み: cm)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="商品のまとめサイズ（幅・高さ・奥行）に対して一律でこのcm数を加算して箱サイズと判定します。"
    )
    
    selected_ids = st.multiselect(
        "商品を選択してください（複数選択可）", 
        options=df_master.index,
        format_func=lambda x: f"{x}: {df_master.loc[x, '商品名']}"
    )
    
    item_quantities = {}
    if selected_ids:
        st.write("**数量設定:**")
        q_cols = st.columns(min(len(selected_ids), 3))
        for idx, item_id in enumerate(selected_ids):
            item_name = df_master.loc[item_id, '商品名']
            col_target = q_cols[idx % 3]
            qty = col_target.number_input(
                f"{item_name}", 
                min_value=1, 
                max_value=50, 
                value=1, 
                key=f"qty_{item_id}"
            )
            item_quantities[item_id] = qty

    def calculate_min_bounding_box(items_list, margin):
        """商品のリストから全パッキングパターンを算出し、マージンを加算した最小外包寸法を返す"""
        total_items = len(items_list)
        
        def get_orientations(w, h, d):
            return list(set(itertools.permutations([w, h, d])))

        best_bounding_boxes = []

        factors = []
        for x in range(1, total_items + 1):
            for y in range(1, total_items + 1):
                for z in range(1, total_items + 1):
                    if x * y * z >= total_items:
                        factors.append((x, y, z))

        if len(set([it['id'] for it in items_list])) == 1:
            item_spec = items_list[0]
            w, h, d = item_spec['w'], item_spec['h'], item_spec['d']
            orientations = get_orientations(w, h, d)

            for fx, fy, fz in factors:
                for ow, oh, od in orientations:
                    # 商品をまとめた集合のサイズ
                    raw_w = ow * fx
                    raw_h = oh * fy
                    raw_d = od * fz
                    
                    # まとめた集合の全各辺に緩衝材マージンを一律加算
                    bounding_w = raw_w + margin
                    bounding_h = raw_h + margin
                    bounding_d = raw_d + margin
                    
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, raw_w, raw_h, raw_d))
        else:
            sum_w = sum([it['w'] for it in items_list])
            max_h = max([it['h'] for it in items_list])
            max_d = max([it['d'] for it in items_list])
            
            bounding_w = sum_w + margin
            bounding_h = max_h + margin
            bounding_d = max_d + margin
            
            best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, sum_w, max_h, max_d))

        return best_bounding_boxes

    if st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True, disabled=not selected_ids):
        items_list = []
        order_summary_list = []
        raw_items_weight = Decimal('0')
        total_items_volume = 0.0 # 商品純体積

        for item_id, qty in item_quantities.items():
            row = df_master.loc[item_id]
            order_summary_list.append(f"{row['商品名']} × {qty}")
            i_weight = clean_decimal(row['重量(kg)'])
            
            iw = float(clean_decimal(row['幅(cm)']))
            ih = float(clean_decimal(row['高さ(cm)']))
            id_ = float(clean_decimal(row['奥行(cm)']))

            item_vol = iw * ih * id_

            for _ in range(qty):
                items_list.append({'id': item_id, 'w': iw, 'h': ih, 'd': id_})
                raw_items_weight += i_weight
                total_items_volume += item_vol

        # 緩衝材マージンを加算したサイズ候補を取得
        bounding_candidates = calculate_min_bounding_box(items_list, margin=float(buffer_margin))
        fitted_boxes = []

        for _, box in df_boxes.iterrows():
            b_name = str(box['箱名称'])
            bw = float(clean_decimal(box['幅(cm)']))
            bh = float(clean_decimal(box['高さ(cm)']))
            bd = float(clean_decimal(box['奥行(cm)']))
            b_weight = clean_decimal(box['箱重量(kg)'])

            box_dims_sorted = sorted([bw, bh, bd])
            box_volume = bw * bh * bd

            for cw, ch, cd, raw_w, raw_h, raw_d in bounding_candidates:
                cand_dims_sorted = sorted([cw, ch, cd])
                if (cand_dims_sorted[0] <= box_dims_sorted[0] and
                    cand_dims_sorted[1] <= box_dims_sorted[1] and
                    cand_dims_sorted[2] <= box_dims_sorted[2]):
                    
                    fitted_boxes.append({
                        'volume': box_volume,
                        'name': b_name,
                        'box_w': bw, 'box_h': bh, 'box_d': bd,
                        'box_weight': b_weight,
                        'actual_w': cw, 'actual_h': ch, 'actual_d': cd,
                        'raw_w': raw_w, 'raw_h': raw_h, 'raw_d': raw_d
                    })

        st.markdown("---")
        order_str = ", ".join(order_summary_list)

        if fitted_boxes:
            fitted_boxes.sort(key=lambda x: x['volume'])
            best_box = fitted_boxes[0]

            total_pack_weight = raw_items_weight + best_box['box_weight']

            # --- 隙間空間の計算 ---
            box_vol = best_box['volume'] # 箱の総容積 (cm³)
            unused_vol = box_vol - total_items_volume # 無駄な空間 (cm³)
            fill_rate = (total_items_volume / box_vol) * 100 if box_vol > 0 else 0 # 充填率 (%)
            empty_rate = 100.0 - fill_rate # 空白率 (%)

            st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

            m_col1, m_col2 = st.columns(2)
            m_col1.metric("選択された箱の寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
            m_col2.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {best_box['box_weight']:.2f} kg")

            st.write("---")
            st.write("**📦 選択商品の合算情報**")
            p_col1, p_col2 = st.columns(2)
            p_col1.info(
                f"**商品の必要最小寸法 (緩衝材 +{buffer_margin}cm 込):**\n\n"
                f"**{best_box['actual_w']:.1f} × {best_box['actual_h']:.1f} × {best_box['actual_d']:.1f} cm**\n\n"
                f"*(商品自体の実寸まとめ: {best_box['raw_w']:.1f} × {best_box['raw_h']:.1f} × {best_box['raw_d']:.1f} cm)*"
            )
            p_col2.info(f"**商品のみの合計重量:**\n\n**{raw_items_weight:.2f} kg**")

            # --- 空間効率分析 ---
            st.write("**💡 箱の空間効率・余白分析**")
            e_col1, e_col2, e_col3 = st.columns(3)
            e_col1.metric("箱の容量", f"{box_vol/1000:.1f} L", f"{box_vol:,.0f} cm³")
            e_col2.metric("無駄な空間 (デッドスペース)", f"{unused_vol/1000:.1f} L", f"{unused_vol:,.0f} cm³")
            e_col3.metric("箱の空間率", f"充填 {fill_rate:.1f}%", f"隙間 {empty_rate:.1f}%", delta_color="inverse")

            if empty_rate > 40:
                st.warning(f"⚠️ **すき間注意**: 箱に対して商品の占有率が低い ({fill_rate:.1f}%) ため、緩衝材が多く必要になります。")
            else:
                st.success(f"✅ **フィット良好**: 効率よく梱包されています（隙間率 {empty_rate:.1f}%）。")

            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": best_box['name'],
                "必要寸法(+マージン込)": f"{best_box['actual_w']:.1f}x{best_box['actual_h']:.1f}x{best_box['actual_d']:.1f}",
                "無駄な空間": f"{unused_vol/1000:.1f} L ({empty_rate:.1f}%)",
                "梱包総重量": f"{total_pack_weight:.2f} kg"
            })
        else:
            st.error("⚠️ 選択した商品（+緩衝材マージン）が入る箱が「箱マスタ」にありません。より大きいサイズの箱を登録するか、マージン設定を調整してください。")
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": "適合なし (サイズオーバー)",
                "必要寸法(+マージン込)": "-",
                "無駄な空間": "-",
                "梱包総重量": "-"
            })

# --- 画面下部：判定履歴 ---
st.markdown("---")
st.subheader("📜 判定履歴")

if st.session_state.history:
    df_history = pd.DataFrame(st.session_state.history)
    st.dataframe(df_history, use_container_width=True)

    if st.button("🗑️ 履歴をクリア"):
        st.session_state.history = []
        st.rerun()
else:
    st.info("まだ判定履歴はありません。")
