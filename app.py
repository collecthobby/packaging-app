import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
from py3dbp import Bin, Item, Packer

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
    
    if st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True, disabled=not selected_ids):
        packer = Packer()
        box_weight_map = {}
        
        for _, box in df_boxes.iterrows():
            b_name = str(box['箱名称'])
            bw = clean_decimal(box['幅(cm)'])
            bh = clean_decimal(box['高さ(cm)'])
            bd = clean_decimal(box['奥行(cm)'])
            b_weight = clean_decimal(box['箱重量(kg)'])
            
            box_weight_map[b_name] = b_weight
            packer.add_bin(Bin(b_name, bw, bh, bd, Decimal('999999')))
        
        total_items_count = 0
        order_summary_list = []
        raw_items_weight = Decimal('0')
        
        for item_id, qty in item_quantities.items():
            row = df_master.loc[item_id]
            order_summary_list.append(f"{row['商品名']} × {qty}")
            i_weight = clean_decimal(row['重量(kg)'])
            
            for i in range(qty):
                packer.add_item(Item(
                    f"{row['商品名']}_{i+1}", 
                    clean_decimal(row['幅(cm)']), 
                    clean_decimal(row['高さ(cm)']), 
                    clean_decimal(row['奥行(cm)']), 
                    i_weight
                ))
                raw_items_weight += i_weight
                total_items_count += 1
            
        packer.pack(
            bigger_first=True,
　　　　　　 distribute_items=True
        )
        
        fitted_bins = []
        for b in packer.bins:
            if len(b.items) == total_items_count:
                min_x = min([float(item.position[0]) for item in b.items])
                max_x = max([float(item.position[0]) + float(item.width) for item in b.items])
                min_y = min([float(item.position[1]) for item in b.items])
                max_y = max([float(item.position[1]) + float(item.height) for item in b.items])
                min_z = min([float(item.position[2]) for item in b.items])
                max_z = max([float(item.position[2]) + float(item.depth) for item in b.items])
                
                actual_w = max_x - min_x
                actual_h = max_y - min_y
                actual_d = max_z - min_z
                
                # 箱の各辺と商品の各辺を比較し、入りきらない箱を除外する厳密チェック
                item_dims = sorted([actual_w, actual_h, actual_d])
                box_dims = sorted([float(b.width), float(b.height), float(b.depth)])
                
                if item_dims[0] <= box_dims[0] and item_dims[1] <= box_dims[1] and item_dims[2] <= box_dims[2]:
                    volume = float(b.width) * float(b.height) * float(b.depth)
                    fitted_bins.append((volume, b, actual_w, actual_h, actual_d))
                
        st.markdown("---")
        order_str = ", ".join(order_summary_list)
        
        if fitted_bins:
            fitted_bins.sort(key=lambda x: x[0])
            best_tuple = fitted_bins[0]
            best_bin = best_tuple[1]
            actual_w, actual_h, actual_d = best_tuple[2], best_tuple[3], best_tuple[4]
            
            box_self_weight = box_weight_map.get(best_bin.name, Decimal('0'))
            total_pack_weight = raw_items_weight + box_self_weight
            
            st.success(f"### 🎉 最適な箱: 【{best_bin.name}】")
            
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("選択された箱の寸法", f"{best_bin.width} x {best_bin.height} x {best_bin.depth} cm")
            m_col2.metric("梱包総重量 (商品+箱)", f"{total_pack_weight:.2f} kg", f"内 箱自重: {box_self_weight:.2f} kg")
            
            st.write("---")
            st.write("**📦 選択商品の合算情報**")
            p_col1, p_col2 = st.columns(2)
            p_col1.info(f"**商品の必要最小寸法 (W × H × D):**\n\n**{actual_w:.1f} × {actual_h:.1f} × {actual_d:.1f} cm**")
            p_col2.info(f"**商品のみの合計重量:**\n\n**{raw_items_weight:.2f} kg**")
            
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": best_bin.name,
                "必要寸法(cm)": f"{actual_w:.1f}x{actual_h:.1f}x{actual_d:.1f}",
                "梱包総重量": f"{total_pack_weight:.2f} kg (箱: {box_self_weight:.2f}kg)"
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
