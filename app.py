import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
from py3dbp import Bin, Item, Packer

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（全マスタ動的同期）")

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

# --- メイン画面 ---
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
    
    selected_id = st.selectbox(
        "商品を選択してください", 
        options=df_master.index,
        format_func=lambda x: f"{x}: {df_master.loc[x, '商品名']}"
    )
    quantity = st.number_input("数量", min_value=1, max_value=20, value=1)
    
    if st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True):
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
        
        row = df_master.loc[selected_id]
        
        # 商品登録
        for i in range(quantity):
            packer.add_item(Item(
                f"{row['商品名']}_{i+1}", 
                clean_decimal(row['幅(cm)']), 
                clean_decimal(row['高さ(cm)']), 
                clean_decimal(row['奥行(cm)']), 
                clean_decimal(row['重量(kg)'])
            ))
            
        packer.pack(bigger_first=True)
        
        # ★ 修正ポイント: 全商品が収まった箱の中から「容積が最小の箱」を検索
        fitted_bins = []
        for b in packer.bins:
            if len(b.items) == quantity:
                # 箱の容積 (幅 x 高さ x 奥行) を計算して保持
                volume = float(b.width) * float(b.height) * float(b.depth)
                fitted_bins.append((volume, b))
                
        st.markdown("---")
        if fitted_bins:
            # 容積が最も小さい箱を昇順ソートして取得
            fitted_bins.sort(key=lambda x: x[0])
            best_bin = fitted_bins[0][1]
            
            st.balloons()
            st.success(f"### 🎉 最適な箱: 【{best_bin.name}】")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("箱の寸法", f"{best_bin.width} x {best_bin.height} x {best_bin.depth} cm")
            m_col2.metric("梱包総重量", f"{best_bin.get_total_weight():.2f} kg", f"上限 {best_bin.max_weight} kg")
            
            st.write("**【配置詳細】**")
            for item in best_bin.items:
                st.caption(f"・{item.name} -> 配置座標: {item.position}")
        else:
            st.error("⚠️ スプレッドシートに登録されているどの箱にも収まりませんでした。より大きい箱を「箱マスタ」に追加してください。")
