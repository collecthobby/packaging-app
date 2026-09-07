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

# ==========================================
# 1. マスタ情報表示（アコーディオン形式で折りたたみ可能）
# ==========================================
with st.expander("📋 登録マスタ情報（クリックで開閉）", expanded=False):
    tab1, tab2 = st.tabs(["📦 商品マスタ", "📐 箱マスタ"])
    with tab1:
        st.dataframe(df_master, use_container_width=True)
    with tab2:
        st.dataframe(df_boxes, use_container_width=True)
    if st.button("🔄 最新データに更新"):
        st.rerun()

st.markdown("---")

# ==========================================
# 2. 注文シミュレーション設定（画面全幅化）
# ==========================================
st.subheader("🛒 注文シミュレーション")

input_col1, input_col2 = st.columns([1, 2])

with input_col1:
    buffer_margin = st.number_input(
        "🛡️ 緩衝材マージン (全各辺加算: cm)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="商品のまとめサイズ（幅・高さ・奥行）に対して一律でこのcm数を加算して箱サイズと判定します。"
    )

with input_col2:
    selected_ids = st.multiselect(
        "商品を選択してください（複数選択可）", 
        options=df_master.index,
        format_func=lambda x: f"{x}: {df_master.loc[x, '商品名']}"
    )

item_quantities = {}
if selected_ids:
    st.write("**数量設定:**")
    q_cols = st.columns(min(len(selected_ids), 4))
    for idx, item_id in enumerate(selected_ids):
        item_name = df_master.loc[item_id, '商品名']
        col_target = q_cols[idx % 4]
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
                raw_w = ow * fx
                raw_h = oh * fy
                raw_d = od * fz
                
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

# 判定ボタン
if st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True, disabled=not selected_ids):
    items_list = []
    order_summary_list = []
    raw_items_weight = Decimal('0')

    for item_id, qty in item_quantities.items():
        row = df_master.loc[item_id]
        order_summary_list.append(f"{row['商品名']} × {qty}")
        i_weight = clean_decimal(row['重量(kg)'])
        
        iw = float(clean_decimal(row['幅(cm)']))
        ih = float(clean_decimal(row['高さ(cm)']))
        id_ = float(clean_decimal(row['奥行(cm)']))

        for _ in range(qty):
            items_list.append({'id': item_id, 'w': iw, 'h': ih, 'd': id_})
            raw_items_weight += i_weight

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
        box_vol = best_box['volume']
        item_block_vol = best_box['actual_w'] * best_box['actual_h'] * best_box['actual_d']
        unused_vol = box_vol - item_block_vol
        
        fill_rate = (item_block_vol / box_vol) * 100 if box_vol > 0 else 0
        empty_rate = 100.0 - fill_rate

        # ==========================================
        # 3. 判定結果表示（全幅でゆったり表示）
        # ==========================================
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("選択された箱の寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
        m_col2.metric("箱の3辺合計", f"{best_box['box_w'] + best_box['box_h'] + best_box['box_d']:.1f} cm")
        m_col3.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {best_box['box_weight']:.2f} kg")

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
        e_col2.metric("無駄な空間 (隙間スペース)", f"{unused_vol/1000:.1f} L", f"{unused_vol:,.0f} cm³")
        e_col3.metric("箱の空間率", f"商品占有 {fill_rate:.1f}%", f"隙間 {empty_rate:.1f}%", delta_color="inverse")

        # --- ✂️ 箱の加工（切り詰めて小さくする）判定ロジック ---
        st.write("---")
        st.write("**✂️ 箱の加工（リサイズ）提案**")

        box_dims = {'幅': best_box['box_w'], '高さ': best_box['box_h'], '奥行': best_box['box_d']}
        item_dims = sorted([best_box['actual_w'], best_box['actual_h'], best_box['actual_d']], reverse=True)
        box_dims_sorted = sorted([(v, k) for k, v in box_dims.items()], reverse=True)

        margins = []
        for (b_val, name), i_val in zip(box_dims_sorted, item_dims):
            margins.append({
                'name': name,
                'box_val': b_val,
                'item_val': i_val,
                'diff': b_val - i_val
            })

        # ソート処理の修正（lambda を追加）
        margins.sort(key=lambda x: x['diff'], reverse=True)
        max_margin_edge = margins[0]

        if max_margin_edge['diff'] >= 1.0:
            cut_amount = max_margin_edge['diff']
            target_edge_name = max_margin_edge['name']
            original_edge_val = max_margin_edge['box_val']
            new_edge_val = max_margin_edge['item_val']

            original_3sum = best_box['box_w'] + best_box['box_h'] + best_box['box_d']
            new_3sum = original_3sum - cut_amount

            cut_col1, cut_col2 = st.columns([3, 1])
            with cut_col1:
                st.warning(
                    f"✂️ **【切り詰め加工の指示】**\n\n"
                    f"箱の **「{target_edge_name}」** が最も余っています（**{cut_amount:.1f} cm の空き**）。\n\n"
                    f"👉 **{target_edge_name}を {original_edge_val:.1f} cm ➔ {new_edge_val:.1f} cm へ {cut_amount:.1f} cm 切り詰めて折りたたむ** とジャストフィットします。"
                )
            with cut_col2:
                st.info(
                    f"**加工後の箱3辺合計:**\n\n"
                    f"**{new_3sum:.1f} cm** *(元: {original_3sum:.1f} cm)*\n\n"
                    f"削減容積: **{cut_amount * (box_vol/original_edge_val)/1000:.1f} L**"
                )
        else:
            st.success("✅ **加工不要**: 各辺とも隙間が少なく、これ以上大きくカットできる辺はありません。")

        st.session_state.history.insert(0, {
            "注文内容": order_str,
            "判定結果": best_box['name'],
            "必要寸法(+マージン込)": f"{best_box['actual_w']:.1f}x{best_box['actual_h']:.1f}x{best_box['actual_d']:.1f}",
            "加工提案": f"{max_margin_edge['name']}を{max_margin_edge['diff']:.1f}cmカット" if max_margin_edge['diff'] >= 1.0 else "不要",
            "梱包総重量": f"{total_pack_weight:.2f} kg"
        })
    else:
        st.error("⚠️ 選択した商品（+緩衝材マージン）が入る箱が「箱マスタ」にありません。より大きいサイズの箱を登録するか、マージン設定を調整してください。")
        st.session_state.history.insert(0, {
            "注文内容": order_str,
            "判定結果": "適合なし (サイズオーバー)",
            "必要寸法(+マージン込)": "-",
            "加工提案": "-",
            "梱包総重量": "-"
        })

# ==========================================
# 4. 判定履歴（判定結果と同じ全幅で表示）
# ==========================================
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
