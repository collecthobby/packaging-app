import streamlit as st
import pandas as pd
from py3dbp import Bin, Item, Packer
from streamlit_gsheets import GSheetsConnection

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（全マスタ動的同期）")

# --- Googleスプレッドシート連携設定 ---
# ★ご自身のスプレッドシートURLに書き換えてください★
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/13ijkSncdvliXRxUVKVl_xglaxPHTgOD8_hdQFXgE0pc/edit?gid=0#gid=0"

conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    """スプレッドシートから各シートのデータを取得"""
    # ttl=0 で毎回最新データを取得、worksheetを指定
    df_items = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="商品マスタ", ttl=0)
    df_items = df_items.dropna(how="all").set_index("商品ID")
    
    df_boxes = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="箱マスタ", ttl=0)
    df_boxes = df_boxes.dropna(how="all")
    
    return df_items, df_boxes

try:
    df_master, df_boxes = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました。シート名（商品マスタ / 箱マスタ）や共有設定を確認してください。")
    st.stop()

# --- サイドバー：新商品の追加フォーム ---
st.sidebar.header("➕ 商品マスタの追加")
with st.sidebar.form("add_item_form", clear_on_submit=True):
    new_id = st.text_input("商品ID (例: ITEM004)")
    new_name = st.text_input("商品名")
    col_a, col_b = st.columns(2)
    with col_a:
        new_w = st.number_input("幅(cm)", min_value=0.1, value=10.0, step=0.5)
        new_h = st.number_input("高さ(cm)", min_value=0.1, value=10.0, step=0.5)
    with col_b:
        new_d = st.number_input("奥行(cm)", min_value=0.1, value=10.0, step=0.5)
        new_wt = st.number_input("重量(kg)", min_value=0.01, value=0.5, step=0.1)
    
    submit_button = st.form_submit_button("スプレッドシートに保存")
    
    if submit_button:
        if new_id and new_name:
            new_data = pd.DataFrame([{
                "商品ID": new_id,
                "商品名": new_name,
                "幅(cm)": new_w,
                "高さ(cm)": new_h,
                "奥行(cm)": new_d,
                "重量(kg)": new_wt
            }])
            updated_df = pd.concat([df_master.reset_index(), new_data], ignore_index=True)
            # worksheet="商品マスタ" を指定して保存
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="商品マスタ", data=updated_df)
            st.sidebar.success(f"「{new_name}」を保存しました！")
            st.rerun()
        else:
            st.sidebar.error("商品IDと商品名は必須です。")

# --- メイン画面 ---
col_left, col_right = st.columns([1, 1])

# 左側：マスタ確認（タブ切り替え）
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
        
        # ★ スプレッドシートの「箱マスタ」から動的に箱を登録
        for _, box in df_boxes.iterrows():
            packer.add_bin(Bin(
                str(box['箱名称']), 
                float(box['幅(cm)']), 
                float(box['高さ(cm)']), 
                float(box['奥行(cm)']), 
                float(box['最大重量(kg)'])
            ))
        
        row = df_master.loc[selected_id]
        
        for i in range(quantity):
            packer.add_item(Item(
                f"{row['商品名']}_{i+1}", 
                float(row['幅(cm)']), 
                float(row['高さ(cm)']), 
                float(row['奥行(cm)']), 
                float(row['重量(kg)'])
            ))
            
        packer.pack(bigger_first=True)
        
        best_bin = None
        for b in packer.bins:
            if len(b.items) == quantity:
                best_bin = b
                break
                
        st.markdown("---")
        if best_bin:
            st.balloons()
            st.success(f"### 🎉 最適な箱: 【{best_bin.name}】")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("箱の寸法", f"{best_bin.width}x{best_bin.height}x{best_bin.depth} cm")
            m_col2.metric("梱包総重量", f"{best_bin.get_total_weight():.2f} kg", f"上限 {best_bin.max_weight} kg")
            
            st.write("**【配置詳細】**")
            for item in best_bin.items:
                st.caption(f"・{item.name} -> 配置座標: {item.position}")
        else:
            st.error("⚠️ スプレッドシートに登録されているどの箱にも収まりませんでした。より大きい箱を「箱マスタ」に追加してください。")
