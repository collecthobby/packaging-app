import streamlit as st
import pandas as pd
from py3dbp import Bin, Item, Packer
from streamlit_gsheets import GSheetsConnection

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム")

# --- Googleスプレッドシート連携設定 ---
# ★ご自身のスプレッドシートURLに書き換えてください★
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/13ijkSncdvliXRxUVKVl_xglaxPHTgOD8_hdQFXgE0pc/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    """スプレッドシートから最新マスタを取得"""
    df = conn.read(spreadsheet=SPREADSHEET_URL, ttl="0s")
    df = df.dropna(how="all")
    return df.set_index("商品ID")

try:
    df_master = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました。URLおよび共有設定（編集者権限）を確認してください。")
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
            conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
            st.sidebar.success(f"「{new_name}」を保存しました！")
            st.rerun()
        else:
            st.sidebar.error("商品IDと商品名は必須です。")

# --- メイン画面 ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📋 登録商品マスタ")
    st.dataframe(df_master, use_container_width=True)
    if st.button("🔄 最新データに更新"):
        st.rerun()

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
        # 梱包箱のバリエーション定義
        packer.add_bin(Bin('60サイズ箱', 25, 20, 15, 5.0))
        packer.add_bin(Bin('80サイズ箱', 35, 25, 20, 10.0))
        packer.add_bin(Bin('100サイズ箱', 45, 35, 20, 15.0))
        
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
            st.error("⚠️ 準備されている箱（60/80/100）には収まりませんでした。")
