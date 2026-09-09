import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
import itertools

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（全マスタ動的同期）")

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
# 上部: 左右2カラム（マスタ確認＆入力フォーム）
# ==========================================
col_left, col_right = st.columns([5, 7])

# ------------------------------------------
# 左カラム: 📋 登録マスタ情報（チェックボックス連動）
# ------------------------------------------
with col_left:
    st.subheader("📋 登録マスタ情報")
    tab1, tab2 = st.tabs(["📦 商品マスタ (選択連動)", "📐 箱マスタ"])
    
    selected_from_table = []
    with tab1:
        st.caption("👈 左端のチェックボックスを選択すると、右側の注文に反映されます")
        event = st.dataframe(
            df_master, 
            use_container_width=True,
            on_select="rerun",
            selection_mode="multi-row"
        )
        
        if event and event.selection and event.selection.rows:
            selected_indices = event.selection.rows
            selected_from_table = df_master.index[selected_indices].tolist()

    with tab2:
        st.dataframe(df_boxes, use_container_width=True)
        
    if st.button("🔄 最新データに更新"):
        st.rerun()

# ------------------------------------------
# 右カラム: 🛒 注文シミュレーション設定
# ------------------------------------------
with col_right:
    st.subheader("🛒 注文シミュレーション")

    buffer_margin = st.number_input(
        "🛡️ 緩衝材マージン (全各辺加算: cm)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="商品のまとめサイズ（幅・高さ・奥行）に対して一律でこのcm数を加算して箱サイズと判定します。"
    )

    selected_ids = st.multiselect(
        "商品を選択してください（左の一覧でチェックしても自動反映されます）", 
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
            qty = col_target.number_input(
                f"{item_name}", 
                min_value=1, 
                max_value=50, 
                value=1, 
                key=f"qty_{item_id}"
            )
            item_quantities[item_id] = qty

    def calculate_min_bounding_box(items_list, margin):
        """
        商品のリストから、立体的な配置パターン（横並び・縦積み・奥行配置・グリッド配置）
        を探索し、マージンを加算した最小外包寸法候補のリストを返す
        """
        total_items = len(items_list)
        if total_items == 0:
            return []

        def get_orientations(w, h, d):
            return list(set(itertools.permutations([w, h, d])))

        best_bounding_boxes = []

        # 単一種類の商品のみの場合は、約数分解でグリッド配置を計算
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
                    
                    bounding_w = raw_w + margin
                    bounding_h = raw_h + margin
                    bounding_d = raw_d + margin
                    
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, raw_w, raw_h, raw_d))

        else:
            # 複数種類の商品が混在する場合：
            # 1. すべての商品の向きの組み合わせを考慮
            # 2. 3軸（X, Y, Z）の分割パターン（例：2x2x1、1x4x1、1x1x4等）に商品を割り当てて最小ブロックを形成
            
            # アイテムの総数に応じたグリッド分割（1x4, 2x2 など）
            grid_patterns = []
            for x in range(1, total_items + 1):
                for y in range(1, total_items + 1):
                    for z in range(1, total_items + 1):
                        if x * y * z >= total_items:
                            grid_patterns.append((x, y, z))

            # 各商品の向き（向きを固定した代表パターン）で集計
            # 計算負荷を抑えつつ、各軸の最大幅を算出
            for gx, gy, gz in grid_patterns:
                # 均等にアイテムを分配した際に必要な各方向のサイズ見積もり
                # 各商品を立てたり寝かせたりしたサイズを収集
                dim_x, dim_y, dim_z = [], [], []
                
                for idx, it in enumerate(items_list):
                    # 商品の向き（長辺をX軸、中辺をY軸、短辺をZ軸に揃えるなどの基本姿勢）
                    dims = sorted([it['w'], it['h'], it['d']], reverse=True)
                    dim_x.append(dims[0])
                    dim_y.append(dims[1])
                    dim_z.append(dims[2])

                # グリッド配置時の概算最大寸法
                # 例：2x2配置なら、X方向に2個分、Y方向に2個分の最大値を加算
                raw_w = max(dim_x) * gx
                raw_h = max(dim_y) * gy
                raw_d = max(dim_z) * gz

                # 全体の向きの組み合わせ（回転）も含めて登録
                for ow, oh, od in get_orientations(raw_w, raw_h, raw_d):
                    bounding_w = ow + margin
                    bounding_h = oh + margin
                    bounding_d = od + margin
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, ow, oh, od))

        return best_bounding_boxes
    # 判定実行フラグ
    do_calc = st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True, disabled=not selected_ids)

# ==========================================
# 中部: 判定結果の全画面（全幅）表示エリア
# ==========================================
if do_calc and selected_ids:
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

        # ------------------------------------------
        # 🎉 最適な箱（全幅表示）
        # ------------------------------------------
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("選択された箱の寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
        m_col2.metric("箱の3辺合計", f"{best_box['box_w'] + best_box['box_h'] + best_box['box_d']:.1f} cm")
        m_col3.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {best_box['box_weight']:.2f} kg")

        st.write("---")
        
        # ------------------------------------------
        # 📦 選択商品の合算情報 & 💡 空間効率（全幅表示）
        # ------------------------------------------
        res_col1, res_col2 = st.columns(2)
        
        with res_col1:
            st.write("**📦 選択商品の合算情報**")
            st.info(
                f"**商品の必要最小寸法 (緩衝材 +{buffer_margin}cm 込):**\n\n"
                f"**{best_box['actual_w']:.1f} × {best_box['actual_h']:.1f} × {best_box['actual_d']:.1f} cm**\n\n"
                f"*(商品自体の実寸まとめ: {best_box['raw_w']:.1f} × {best_box['raw_h']:.1f} × {best_box['raw_d']:.1f} cm)*\n\n"
                f"商品のみの合計重量: **{raw_items_weight:.2f} kg**"
            )

        with res_col2:
            st.write("**💡 箱の空間効率・余白分析**")
            e_col1, e_col2 = st.columns(2)
            e_col1.metric("箱の容量", f"{box_vol/1000:.1f} L", f"{box_vol:,.0f} cm³")
            e_col2.metric("無駄な空間 (隙間)", f"{unused_vol/1000:.1f} L", f"{unused_vol:,.0f} cm³")
            st.metric("箱の空間率", f"商品占有 {fill_rate:.1f}%", f"隙間 {empty_rate:.1f}%", delta_color="inverse")

        # ------------------------------------------
        # ✂️ 箱の加工（リサイズ）提案（全幅表示）
        # ------------------------------------------
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

        # 履歴追加
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
# 下部: 📜 判定履歴（全幅表示）
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
