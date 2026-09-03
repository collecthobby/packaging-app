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
    df_items = df_items.dropna(how="all").set_index("商品ID")
    
    url_boxes = get_sheet_url("箱マスタ")
    df_boxes = pd.read_csv(url_boxes)
    df_boxes = df_boxes.dropna(how="all")
    
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

# 右側：シミュレーション実行（複数商品選択対応）
with col_right:
    st.subheader("🛒 注文シミュレーション")
    
    selected_ids = st.multiselect(
        "商品を選択してください（複数選択可）", 
        options=df_master.index,
        format_func=lambda x: f"{x}: {df_master.loc[x, '商品名']}"
    )
    
    # 選択された商品ごとに数量を指定
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
        
        # 箱マスタ登録
        for _, box in df_boxes.iterrows():
            packer.add_bin(Bin(
                str(box['箱名称']), 
                clean_decimal(box['幅(cm)']), 
                clean_decimal(box['高さ(cm)']), 
                clean_decimal(box['奥行(cm)']), 
                clean_decimal(box['最大重量(kg)'])
            ))
        
        # 複数種類・指定数量の商品をPackerに追加
        total_items_count = 0
        order_summary_list = []
        for item_id, qty in item_quantities.items():
            row = df_master.loc[item_id]
            order_summary_list.append(f"{row['商品名']} × {qty}")
            for i in range(qty):
                packer.add_item(Item(
                    f"{row['商品名']}_{i+1}", 
                    clean_decimal(row['幅(cm)']), 
                    clean_decimal(row['高さ(cm)']), 
                    clean_decimal(row['奥行(cm)']), 
                    clean_decimal(row['重量(kg)'])
                ))
                total_items_count += 1
            
        packer.pack(bigger_first=True)
        
        # 全商品が収まった箱の中から「容積が最小の箱」を取得
        fitted_bins = []
        for b in packer.bins:
            if len(b.items) == total_items_count:
                volume = float(b.width) * float(b.height) * float(b.depth)
                fitted_bins.append((volume, b))
                
        st.markdown("---")
        order_str = ", ".join(order_summary_list)
        
        if fitted_bins:
            fitted_bins.sort(key=lambda x: x[0])
            best_bin = fitted_bins[0][1]
            
            # 結果表示（演出なし）
            st.success(f"### 🎉 最適な箱: 【{best_bin.name}】")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("箱の寸法", f"{best_bin.width} x {best_bin.height} x {best_bin.depth} cm")
            m_col2.metric("梱包総重量", f"{best_bin.get_total_weight():.2f} kg", f"上限 {best_bin.max_weight} kg")
            
            st.write("**【配置詳細】**")
            for item in best_bin.items:
                st.caption(f"・{item.name} -> 配置座標: {item.position}")
                
            # 履歴に追加
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": best_bin.name,
                "箱サイズ(cm)": f"{best_bin.width}x{best_bin.height}x{best_bin.depth}",
                "梱包重量": f"{best_bin.get_total_weight():.2f} kg"
            })
        else:
            st.error("⚠️ スプレッドシートに登録されているどの箱にも収まりませんでした。より大きい箱を「箱マスタ」に追加してください。")
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": "適合なし (サイズオーバー)",
                "箱サイズ(cm)": "-",
                "梱包重量": "-"
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
