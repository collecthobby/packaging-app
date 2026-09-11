import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
import itertools

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（国内外・運送会社別・送料自動計算対応）")

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
    df_items = pd.read_csv(url_items)
    df_items = df_items.dropna(how="all")
    df_items.columns = df_items.columns.str.strip()
    df_items = df_items.loc[:, ~df_items.columns.duplicated()]
    df_items = df_items.set_index("商品ID")
    
    # 2. 箱マスタ
    url_boxes = get_sheet_url("箱マスタ")
    df_boxes = pd.read_csv(url_boxes)
    df_boxes = df_boxes.dropna(how="all")
    df_boxes.columns = df_boxes.columns.str.strip()
    
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

    # 3. 国内送料マスタ
    df_shipping_dom = pd.DataFrame()
    try:
        url_shipping_dom = get_sheet_url("送料マスタ")
        df_shipping_dom = pd.read_csv(url_shipping_dom).dropna(how="all")
        df_shipping_dom.columns = df_shipping_dom.columns.str.strip()
    except:
        pass

    # 4. 海外送料マスタ
    df_shipping_intl = pd.DataFrame()
    try:
        url_shipping_intl = get_sheet_url("海外送料マスタ")
        df_shipping_intl = pd.read_csv(url_shipping_intl).dropna(how="all")
        df_shipping_intl.columns = df_shipping_intl.columns.str.strip()
    except:
        pass

    return df_items, df_boxes, df_shipping_dom, df_shipping_intl

try:
    df_master, df_boxes, df_shipping_dom, df_shipping_intl = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました。詳細なエラーは以下の通りです：")
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
    tab1, tab2, tab3, tab4 = st.tabs(["📦 商品", "📐 箱", "🇯🇵 国内送料", "🌏 海外送料"])
    
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

    with tab3:
        if not df_shipping_dom.empty:
            st.dataframe(df_shipping_dom, use_container_width=True)
        else:
            st.warning("⚠️ シート『送料マスタ』が見つかりません。")

    with tab4:
        if not df_shipping_intl.empty:
            st.dataframe(df_shipping_intl, use_container_width=True)
        else:
            st.warning("⚠️ シート『海外送料マスタ』が見つかりません。")
        
    if st.button("🔄 最新データに更新"):
        st.rerun()

# ------------------------------------------
# 右カラム: 🛒 注文シミュレーション設定
# ------------------------------------------
with col_right:
    st.subheader("🛒 注文シミュレーション")

    # 1. 発送モード切り替え（国内 / 海外）
    ship_mode = st.radio(
        "🌐 発送区分の選択",
        ["🇯🇵 国内発送", "🌏 海外発送"],
        horizontal=True
    )

    # 2. 海外発送時の容積重量計算係数の選択 (5000 / 8000 / カスタム)
    vol_factor = 5000.0
    if ship_mode == "🌏 海外発送":
        vf_choice = st.radio(
            "📐 容積重量の計算係数 (÷割数)",
            ["5000 (標準/EMS/クーリエ等)", "8000 (特別便等)", "指定数値入力"],
            horizontal=True,
            help="容積重量 = (縦cm × 横cm × 高さcm) ÷ 係数 で計算します。"
        )
        if "5000" in vf_choice:
            vol_factor = 5000.0
        elif "8000" in vf_choice:
            vol_factor = 8000.0
        else:
            vol_factor = float(st.number_input("任意の計算係数を入力", min_value=1000, max_value=20000, value=5000, step=500))

    cfg_col1, cfg_col2 = st.columns(2)
    with cfg_col1:
        buffer_margin = st.number_input(
            "🛡️ 緩衝材マージン (全各辺加算: cm)",
            min_value=0.0,
            max_value=10.0,
            value=2.0,
            step=0.5,
            help="商品のまとめサイズ（幅・高さ・奥行）に対して一律でこのcm数を加算して箱サイズと判定します。"
        )

    with cfg_col2:
        # モードに応じた送料マスタと配送会社選択オプションの生成
        if ship_mode == "🇯🇵 国内発送":
            active_shipping_df = df_shipping_dom
            ignore_cols = ["サイズ区分", "サイズ", "重量上限(kg)", "重量上限"]
        else:
            active_shipping_df = df_shipping_intl
            ignore_cols = ["重量上限(kg)", "重量上限", "3辺合計上限(cm)", "3辺合計上限"]

        carrier_options = []
        if not active_shipping_df.empty:
            carrier_options = [c for c in active_shipping_df.columns if c not in ignore_cols]
        if not carrier_options:
            carrier_options = ["標準配送"]

        selected_carrier = st.selectbox(
            "🚚 配送会社 / 地帯（ゾーン）を選択",
            options=carrier_options
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
                    
                    bounding_w = raw_w + margin
                    bounding_h = raw_h + margin
                    bounding_d = raw_d + margin
                    
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, raw_w, raw_h, raw_d))

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
                    dim_x.append(dims[0])
                    dim_y.append(dims[1])
                    dim_z.append(dims[2])

                raw_w = max(dim_x) * gx
                raw_h = max(dim_y) * gy
                raw_d = max(dim_z) * gz

                for ow, oh, od in get_orientations(raw_w, raw_h, raw_d):
                    bounding_w = ow + margin
                    bounding_h = oh + margin
                    bounding_d = od + margin
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d, ow, oh, od))

        return best_bounding_boxes

    # --- 送料計算ロジック（国内・海外両対応） ---
    def get_shipping_cost(total_3sum, total_weight_kg, box_volume_cm3, carrier_name, is_intl, divisor):
        if active_shipping_df.empty or carrier_name not in active_shipping_df.columns:
            return 0, "判定不可", 0.0

        df_sorted = active_shipping_df.copy()

        if not is_intl:
            # 【国内発送】 3辺合計（サイズ区分）優先で判定
            size_col = next((c for c in df_sorted.columns if "サイズ" in c), None)
            weight_col = next((c for c in df_sorted.columns if "重量" in c), None)

            if not size_col:
                return 0, "判定不可", 0.0

            df_sorted[size_col] = df_sorted[size_col].apply(lambda x: float(clean_decimal(x)))
            if weight_col:
                df_sorted[weight_col] = df_sorted[weight_col].apply(lambda x: float(clean_decimal(x)))
            df_sorted = df_sorted.sort_values(by=size_col)

            for _, row in df_sorted.iterrows():
                sz_limit = row[size_col]
                wt_limit = float(row[weight_col]) if weight_col else 999.0
                if total_3sum <= sz_limit and float(total_weight_kg) <= wt_limit:
                    cost = int(clean_decimal(row[carrier_name]))
                    return cost, f"{int(sz_limit)}サイズ", 0.0

        else:
            # 【海外発送】 容積重量 (縦x横x高 / 指定係数) と 実重量 の大きい方を適用して判定
            volumetric_weight = box_volume_cm3 / float(divisor)
            effective_weight = max(float(total_weight_kg), volumetric_weight)

            weight_col = next((c for c in df_sorted.columns if "重量" in c), None)
            size_col = next((c for c in df_sorted.columns if "3辺" in c or "サイズ" in c), None)

            if not weight_col:
                return 0, "判定不可", volumetric_weight

            df_sorted[weight_col] = df_sorted[weight_col].apply(lambda x: float(clean_decimal(x)))
            if size_col:
                df_sorted[size_col] = df_sorted[size_col].apply(lambda x: float(clean_decimal(x)))
            df_sorted = df_sorted.sort_values(by=weight_col)

            for _, row in df_sorted.iterrows():
                wt_limit = row[weight_col]
                sz_limit = float(row[size_col]) if size_col else 999.0

                if effective_weight <= wt_limit and total_3sum <= sz_limit:
                    cost = int(clean_decimal(row[carrier_name]))
                    return cost, f"~{wt_limit:.1f}kg区分", volumetric_weight

        return 0, "規格外(オーバー)", volumetric_weight if is_intl else 0.0

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
    is_intl_mode = (ship_mode == "🌏 海外発送")

    if fitted_boxes:
        fitted_boxes.sort(key=lambda x: x['volume'])
        best_box = fitted_boxes[0]

        total_pack_weight = raw_items_weight + best_box['box_weight']
        box_3sum = best_box['box_w'] + best_box['box_h'] + best_box['box_d']
        box_volume_cm3 = best_box['volume']

        # 送料の自動算出
        shipping_cost, size_category, vol_weight = get_shipping_cost(
            box_3sum, total_pack_weight, box_volume_cm3, selected_carrier, is_intl_mode, vol_factor
        )

        # --- 隙間空間の計算 ---
        box_vol = best_box['volume']
        item_block_vol = best_box['actual_w'] * best_box['actual_h'] * best_box['actual_d']
        unused_vol = box_vol - item_block_vol
        
        fill_rate = (item_block_vol / box_vol) * 100 if box_vol > 0 else 0
        empty_rate = 100.0 - fill_rate

        # ------------------------------------------
        # 🎉 最適な箱（全幅表示）
        # ------------------------------------------
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】 ({ship_mode})")

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("選択された箱の寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
        m_col2.metric("箱の3辺合計", f"{box_3sum:.1f} cm", f"区分: {size_category}")
        
        # 重量表示（海外モード時は実重量と容積重量を併記）
        if is_intl_mode:
            applied_wt = max(float(total_pack_weight), vol_weight)
            weight_sub = f"実重量:{total_pack_weight:.2f}kg / 容積重量(÷{int(vol_factor)}):{vol_weight:.2f}kg"
            m_col3.metric("梱包算出重量 (適用)", f"{applied_wt:.2f} kg", weight_sub)
        else:
            m_col3.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {best_box['box_weight']:.2f} kg")
        
        shipping_str = f"¥{shipping_cost:,}" if shipping_cost > 0 else "規格外/未設定"
        m_col4.metric(f"🚚 {selected_carrier} 送料", shipping_str)

        st.write("---")
        
        # ------------------------------------------
        # 📦 選択商品の合算情報 & 💡 空間効率
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
        # ✂️ 箱の加工（リサイズ）提案
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

            new_3sum = box_3sum - cut_amount
            new_vol_cm3 = box_vol * (new_edge_val / original_edge_val)
            
            new_cost, new_size_cat, _ = get_shipping_cost(
                new_3sum, total_pack_weight, new_vol_cm3, selected_carrier, is_intl_mode, vol_factor
            )

            cost_diff_msg = ""
            if new_cost < shipping_cost and new_cost > 0:
                saved = shipping_cost - new_cost
                cost_diff_msg = f"\n\n💰 **送料ダウンチャンス!** カットすると `{size_category}` ➔ `{new_size_cat}` に下がり **{saved:,}円節約** できます！"

            cut_col1, cut_col2 = st.columns([3, 1])
            with cut_col1:
                st.warning(
                    f"✂️ **【切り詰め加工の指示】**\n\n"
                    f"箱の **「{target_edge_name}」** が最も余っています（**{cut_amount:.1f} cm の空き**）。\n\n"
                    f"👉 **{target_edge_name}を {original_edge_val:.1f} cm ➔ {new_edge_val:.1f} cm へ {cut_amount:.1f} cm 切り詰めて折りたたむ** とジャストフィットします。"
                    f"{cost_diff_msg}"
                )
            with cut_col2:
                st.info(
                    f"**加工後の箱3辺合計:**\n\n"
                    f"**{new_3sum:.1f} cm** *(元: {box_3sum:.1f} cm)*\n\n"
                    f"削減容積: **{cut_amount * (box_vol/original_edge_val)/1000:.1f} L**"
                )
        else:
            st.success("✅ **加工不要**: 各辺とも隙間が少なく、これ以上大きくカットできる辺はありません。")

        # 履歴追加
        st.session_state.history.insert(0, {
            "発送区分": f"{ship_mode} (÷{int(vol_factor)})" if is_intl_mode else ship_mode,
            "注文内容": order_str,
            "配送会社": selected_carrier,
            "判定結果": best_box['name'],
            "サイズ区分": size_category,
            "想定送料": f"¥{shipping_cost:,}" if shipping_cost > 0 else "-",
            "必要寸法(+マージン込)": f"{best_box['actual_w']:.1f}x{best_box['actual_h']:.1f}x{best_box['actual_d']:.1f}",
            "加工提案": f"{max_margin_edge['name']}を{max_margin_edge['diff']:.1f}cmカット" if max_margin_edge['diff'] >= 1.0 else "不要",
            "梱包総重量": f"{total_pack_weight:.2f} kg"
        })
    else:
        st.error("⚠️ 選択した商品（+緩衝材マージン）が入る箱が「箱マスタ」にありません。より大きいサイズの箱を登録するか、マージン設定を調整してください。")
        st.session_state.history.insert(0, {
            "発送区分": ship_mode,
            "注文内容": order_str,
            "配送会社": selected_carrier,
            "判定結果": "適合なし (サイズオーバー)",
            "サイズ区分": "-",
            "想定送料": "-",
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
