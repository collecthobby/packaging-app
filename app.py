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

# ==========================================
# 共通制限チェック関数（小形包装物・特定サービス用）
# ==========================================
def check_small_packet_limits(dims, total_3sum, total_weight_kg):
    """
    国際エアパケットなどの小形包装物共通規格チェック
    - 最長辺 <= 60cm
    - 3辺合計 <= 90cm
    - 重量 <= 2.0kg
    """
    length = dims[0]  # 最長辺
    if length > 60.0:
        return False, "規格外(最長辺60cm超)"
    if total_3sum > 90.0:
        return False, "規格外(3辺合計90cm超)"
    if total_weight_kg > 2.0:
        return False, "規格外(重量2kg超)"
    return True, ""

def check_speedpak_limits(dims, total_3sum, total_weight_kg):
    """
    eBay SpeedPAK Economy 規格チェック
    - 最長辺 <= 66cm
    - 胴回り（最長辺 + 2*(幅+高さ)） <= 274cm
    """
    length = dims[0]
    width = dims[1]
    height = dims[2]

    if length > 66.0:
        return False, "規格外(長さ66cm超)"

    girth = length + 2 * (width + height)
    if girth > 274.0:
        return False, "規格外(胴回り274cm超)"

    return True, ""


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
    
    df_boxes = df_boxes.loc[:, df_boxes.columns.notna()]
    df_boxes.columns = df_boxes.columns.astype(str).str.strip()

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
    df_boxes = df_boxes.loc[:, ~df_boxes.columns.duplicated(keep="first")]

    cols = list(df_boxes.columns)
    counts = {}
    for i, col in enumerate(cols):
        if cols.count(col) > 1:
            counts[col] = counts.get(col, 0) + 1
            if counts[col] > 1:
                cols[i] = f"{col}_{counts[col]-1}"
    df_boxes.columns = cols

    # --- 送料シート共通のクリーンアップ関数 ---
    def clean_shipping_df(sheet_name):
        url = get_sheet_url(sheet_name)
        df = pd.read_csv(url)
        df = df.dropna(how="all").dropna(how="all", axis=1)
        df.columns = df.columns.astype(str).str.strip()
        df = df.loc[:, ~df.columns.str.contains(r'^Unnamed', case=False, regex=True)]
        df = df.loc[:, df.columns != ""]
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
        return df

    # 3. 発送マスター辞書（ここを一元管理）
    shipping_masters = {}

    # 日本郵便（おてがる配送）
    try:
        shipping_masters["🚚 ヤフオクゆうパック"] = {
            "df": clean_shipping_df("ヤフオクおてがる配送(日本郵便)"),
            "type": "dom"
        }
    except: pass

    # ヤマト運輸（おてがる配送）
    try:
        shipping_masters["🐱 ヤフオクヤマト"] = {
            "df": clean_shipping_df("ヤフオクおてがる配送(ヤマト運輸)"),
            "type": "dom"
        }
    except: pass

    # 国際エアパケット（小形包装物チェックを適用）
    try:
        shipping_masters["✈️ 国際エアパケット(米国)"] = {
            "df": clean_shipping_df("国際エアパケット(米国)"),
            "type": "intl",
            "divisor": 99999999.0,
            "custom_check": check_small_packet_limits
        }
    except: pass

    # 佐川急便
    try:
        shipping_masters["🚛 佐川急便 (サイズ基準)"] = {
            "df": clean_shipping_df("佐川急便_飛脚"),
            "type": "dom"
        }
    except:
        try:
            shipping_masters["🌏 海外発送 (容積重量 ÷8000)"] = {
                "df": clean_shipping_df("海外送料_8000"),
                "type": "intl",
                "divisor": 8000.0
            }
        except: pass

    # eBay SpeedPAK Economy
    try:
        shipping_masters["📦 eBay SpeedPAK Economy"] = {
            "df": clean_shipping_df("eBay SpeedPAK Economy"),
            "type": "intl",
            "divisor": 8000.0,
            "custom_check": check_speedpak_limits
        }
    except: pass

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

    # --- 汎用送料計算ロジック ---
    def calc_carrier_cost(df_shipping, total_3sum, total_weight_kg, box_volume_cm3, rule_type, divisor=5000.0, box_dims=None, custom_check=None):
        results = {}
        ignore_cols = ["サイズ区分", "サイズ", "重量上限(kg)", "重量上限", "3辺合計上限(cm)", "3辺合計上限"]
        carriers = [c for c in df_shipping.columns if c not in ignore_cols]

        df_sorted = df_shipping.copy()

        # カスタムチェック判定（関数が設定されている場合のみ呼び出し）
        if box_dims and custom_check:
            sorted_dims = sorted(box_dims, reverse=True)  # [最長辺, 中間辺, 最短辺]
            is_valid, reason = custom_check(sorted_dims, total_3sum, float(total_weight_kg))
            if not is_valid:
                for c in carriers:
                    results[c] = {"cost": 0, "cat": reason, "weight_used": float(total_weight_kg)}
                return results

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

do_calc = st.button("🚀 発送方法を一括計算", type="primary", use_container_width=True)

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

        # ---------------------------------------------------------
        # 📐 1辺のみリサイズ（カット）の計算ロジック
        # ---------------------------------------------------------
        box_dims_with_name = [
            (best_box['box_w'], '幅'),
            (best_box['box_h'], '高さ'),
            (best_box['box_d'], '奥行')
        ]
        box_dims_sorted = sorted(box_dims_with_name, key=lambda x: x[0], reverse=True)

        item_dims_sorted = sorted([best_box['actual_w'], best_box['actual_h'], best_box['actual_d']], reverse=True)

        margins = []
        for (b_val, b_name), i_val in zip(box_dims_sorted, item_dims_sorted):
            margins.append({
                'name': b_name,
                'orig_val': b_val,
                'target_val': i_val,
                'diff': b_val - i_val
            })

        margins.sort(key=lambda x: x['diff'], reverse=True)
        target_edge = margins[0]  # カット対象の1辺

        resized_dims = {}
        for m in margins:
            if m['name'] == target_edge['name'] and target_edge['diff'] >= 1.0:
                resized_dims[m['name']] = m['target_val']
            else:
                resized_dims[m['name']] = m['orig_val']

        res_w = resized_dims['幅']
        res_h = resized_dims['高さ']
        res_d = resized_dims['奥行']

        # 加工前・加工後のサイズ計算
        resized_3sum = res_w + res_h + res_d
        resized_vol = res_w * res_h * res_d

        orig_3sum = best_box['box_w'] + best_box['box_h'] + best_box['box_d']
        orig_vol = best_box['volume']

        # ------------------------------------------
        # 🎉 1. 最適な箱基本情報
        # ------------------------------------------
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

        st.markdown("**📦 加工前の箱（元のサイズ）**")
        orig_col1, orig_col2, orig_col3 = st.columns(3)
        with orig_col1:
            st.markdown(f"外寸 (幅x高x奥)\n\n{best_box['box_w']:.1f} × {best_box['box_h']:.1f} × {best_box['box_d']:.1f} cm")
        with orig_col2:
            st.markdown(f"3辺合計\n\n{orig_3sum:.1f} cm")
        with orig_col3:
            st.markdown(f"容積\n\n{orig_vol/1000:.1f} L")

        st.markdown("**✂️ 1辺カット加工後のサイズ**")
        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
        with res_col1:
            st.markdown(f"加工後寸法\n\n{res_w:.1f} × {res_h:.1f} × {res_d:.1f} cm")
        with res_col2:
            st.markdown(f"加工後3辺合計\n\n{resized_3sum:.1f} cm\n\n↓ -{orig_3sum - resized_3sum:.1f} cm")
        with res_col3:
            st.markdown(f"加工後容積\n\n{resized_vol/1000:.1f} L\n\n↓ -{(orig_vol - resized_vol)/1000:.1f} L")
        with res_col4:
            st.markdown(f"梱包総重量\n\n{total_pack_weight:.2f} kg\n\n商品:{raw_items_weight:.2f}kg + 箱:{best_box['box_weight']:.2f}kg")

        st.write("---")

        # ------------------------------------------
        # 💰 2. リサイズ前後 送料一括比較一覧表
        # ------------------------------------------
        st.subheader("💰 リサイズ前後の送料比較一覧")

        comparison_rows = []
        for rule_title, m_info in shipping_masters.items():
            rule_type = m_info["type"]
            divisor = m_info.get("divisor", 5000.0)
            df_m = m_info["df"]
            custom_check_func = m_info.get("custom_check", None)

            # 1. 加工前（元のサイズ）での送料計算
            res_orig = calc_carrier_cost(
                df_shipping=df_m,
                total_3sum=orig_3sum,
                total_weight_kg=total_pack_weight,
                box_volume_cm3=orig_vol,
                rule_type=rule_type,
                divisor=divisor,
                box_dims=[best_box['box_w'], best_box['box_h'], best_box['box_d']],
                custom_check=custom_check_func
            )

            # 2. 加工後（リサイズサイズ）での送料計算
            res_res = calc_carrier_cost(
                df_shipping=df_m,
                total_3sum=resized_3sum,
                total_weight_kg=total_pack_weight,
                box_volume_cm3=resized_vol,
                rule_type=rule_type,
                divisor=divisor,
                box_dims=[res_w, res_h, res_d],
                custom_check=custom_check_func
            )

            for carrier_name in res_res.keys():
                cost_orig = res_orig[carrier_name]["cost"]
                cat_orig = res_orig[carrier_name]["cat"]
                
                cost_res = res_res[carrier_name]["cost"]
                cat_res = res_res[carrier_name]["cat"]

                val_orig = cost_orig if cost_orig > 0 else 9999999
                val_res = cost_res if cost_res > 0 else 9999999

                if val_orig < 9999999 and val_res < 9999999:
                    saving = val_orig - val_res
                else:
                    saving = 0

                comparison_rows.append({
                    "発送区分/ルール": rule_title,
                    "配送会社/サービス": carrier_name,
                    "加工前 区分": cat_orig,
                    "加工後 区分": cat_res,
                    "リサイズ前 送料": val_orig,
                    "リサイズ後 送料": val_res,
                    "削減額": saving
                })

        if comparison_rows:
            df_comp = pd.DataFrame(comparison_rows)
            df_comp_sorted = df_comp.sort_values(by="リサイズ後 送料")

            df_comp_display = pd.DataFrame()
            df_comp_display["発送区分/ルール"] = df_comp_sorted["発送区分/ルール"]
            df_comp_display["配送会社/サービス"] = df_comp_sorted["配送会社/サービス"]
            df_comp_display["加工前 区分"] = df_comp_sorted["加工前 区分"]
            df_comp_display["加工後 区分"] = df_comp_sorted["加工後 区分"]
            df_comp_display["リサイズ前 送料"] = df_comp_sorted["リサイズ前 送料"].apply(lambda x: f"¥{x:,}" if x < 9999999 else "規格外")
            df_comp_display["リサイズ後 送料"] = df_comp_sorted["リサイズ後 送料"].apply(lambda x: f"¥{x:,}" if x < 9999999 else "規格外")
            df_comp_display["リサイズによる削減額"] = df_comp_sorted["削減額"].apply(lambda x: f"🎉 ¥{x:,} お得！" if x > 0 else ("- " if x == 0 else f"¥{x:,}"))

            st.dataframe(df_comp_display, use_container_width=True, hide_index=True)

            cheapest = df_comp_sorted.iloc[0]
            if cheapest["リサイズ後 送料"] < 9999999:
                savings_text = f"（💡 リサイズで **¥{cheapest['削減額']:,}** 安くなりました！）" if cheapest['削減額'] > 0 else ""
                st.info(
                    f"🏆 **最安発送方法**: 【{cheapest['発送区分/ルール']} - {cheapest['配送会社/サービス']}】 ➔ **¥{cheapest['リサイズ後 送料']:,}** {savings_text}"
                )
            else:
                st.error("⚠️ すべての配送サービスで規格外（サイズ・重量オーバー）となっています。")

        # ------------------------------------------
        # ✂️ 3. 箱の現場加工指示
        # ------------------------------------------
        st.write("---")
        st.write("**✂️ 現場への箱加工（リサイズ）指示**")

        if target_edge['diff'] >= 1.0:
            st.warning(
                f"✂️ **【1辺カット加工指示】** 箱の **「{target_edge['name']}」** のみを **{target_edge['orig_val']:.1f} cm ➔ {target_edge['target_val']:.1f} cm** へ **{target_edge['diff']:.1f} cm** 切り詰めて梱包してください。（残り2辺はそのまま使用）"
            )
        else:
            st.success("✅ **加工不要**: 元の箱サイズでジャストフィットしています。")

        # 履歴追加
        st.session_state.history.insert(0, {
            "注文内容": order_str,
            "判定箱": f"{best_box['name']} ({target_edge['name']}カット)",
            "最安発送手段": f"{cheapest['配送会社/サービス']} (¥{cheapest['リサイズ後 送料']:,})" if cheapest['リサイズ後 送料'] < 9999999 else "なし",
            "梱包総重量": f"{total_pack_weight:.2f} kg"
        })
    else:
        st.error("⚠️ 選択した商品が入る箱が「箱マスタ」にありません。")
