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

    def calculate_min_bounding_box(items_list):
        """商品のリストから全パッキングパターンを算出し、最小の外包サイズとそれに適合する箱を返す"""
        # 同一商品が複数ある場合のグリッド(nx, ny, nz)パターン算出
        # 単一種類の商品まとめ買いに対応
        total_items = len(items_list)
        
        # 向きのバリエーション（全6パターン）
        def get_orientations(w, h, d):
            return list(set(itertools.permutations([w, h, d])))

        best_bounding_boxes = []

        # 商品個数に対する可能な分解（例: 4個 -> 1x1x4, 1x2x2, 2x2x1 など）
        factors = []
        for x in range(1, total_items + 1):
            for y in range(1, total_items + 1):
                for z in range(1, total_items + 1):
                    if x * y * z >= total_items:
                        factors.append((x, y, z))

        # 単一商品種の場合のブロック最適化
        if len(set([it['id'] for it in items_list])) == 1:
            item_spec = items_list[0]
            w, h, d = item_spec['w'], item_spec['h'], item_spec['d']
            orientations = get_orientations(w, h, d)

            for fx, fy, fz in factors:
                for ow, oh, od in orientations:
                    bounding_w = ow * fx
                    bounding_h = oh * fy
                    bounding_d = od * fz
                    best_bounding_boxes.append((bounding_w, bounding_h, bounding_d))
        else:
            # 複数種類混載時の簡易合成（各商品の方向ごとの合計最大値）
            # 基本は単純積み上げ・並べ
            sum_w = sum([it['w'] for it in items_list])
            max_h = max([it['h'] for it in items_list])
            max_d = max([it['d'] for it in items_list])
            best_bounding_boxes.append((sum_w, max_h, max_d))

        return best_bounding_boxes

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

        # 商品群の必要外装サイズの候補パターンを取得
        bounding_candidates = calculate_min_bounding_box(items_list)

        fitted_boxes = []

        for _, box in df_boxes.iterrows():
            b_name = str(box['箱名称'])
            bw = float(clean_decimal(box['幅(cm)']))
            bh = float(clean_decimal(box['高さ(cm)']))
            bd = float(clean_decimal(box['奥行(cm)']))
            b_weight = clean_decimal(box['箱重量(kg)'])

            box_dims_sorted = sorted([bw, bh, bd])
            box_volume = bw * bh * bd

            for cw, ch, cd in bounding_candidates:
                cand_dims_sorted = sorted([cw, ch, cd])
                # 各辺比較で完全に収まるか判定
                if (cand_dims_sorted[0] <= box_dims_sorted[0] and
                    cand_dims_sorted[1] <= box_dims_sorted[1] and
                    cand_dims_sorted[2] <= box_dims_sorted[2]):
                    
                    fitted_boxes.append({
                        'volume': box_volume,
                        'name': b_name,
                        'box_w': bw, 'box_h': bh, 'box_d': bd,
                        'box_weight': b_weight,
                        'actual_w': cw, 'actual_h': ch, 'actual_d': cd
                    })

        st.markdown("---")
        order_str = ", ".join(order_summary_list)

        if fitted_boxes:
            # 容積が最も小さい箱を選択
            fitted_boxes.sort(key=lambda x: x['volume'])
            best_box = fitted_boxes[0]

            total_pack_weight = raw_items_weight + best_box['box_weight']

            st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

            m_col1, m_col2 = st.columns(2)
            m_col1.metric("選択された箱の寸法", f"{best_box['box_w']} x {best_box['box_h']} x {best_box['box_d']} cm")
            m_col2.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {best_box['box_weight']:.2f} kg")

            st.write("---")
            st.write("**📦 選択商品の合算情報**")
            p_col1, p_col2 = st.columns(2)
            p_col1.info(f"**商品の必要最小寸法 (W × H × D):**\n\n**{best_box['actual_w']:.1f} × {best_box['actual_h']:.1f} × {best_box['actual_d']:.1f} cm**")
            p_col2.info(f"**商品のみの合計重量:**\n\n**{raw_items_weight:.2f} kg**")

            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": best_box['name'],
                "必要寸法(cm)": f"{best_box['actual_w']:.1f}x{best_box['actual_h']:.1f}x{best_box['actual_d']:.1f}",
                "梱包総重量": f"{total_pack_weight:.2f} kg (箱: {best_box['box_weight']:.2f}kg)"
            })
        else:
            st.error("⚠️ 選択した商品が入る箱が「箱マスタ」にありません。より大きいサイズの箱を登録してください。")
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": "適合なし (サイズオーバー)",
                "必要寸法(cm)": "-",
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
