import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
from py3dbp import Bin, Item, Packer
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

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

def plot_3d_packing(bin_obj):
    """箱とアイテムの配置を正確に3D描画する決定版関数"""
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection='3d')
    
    # py3dbpの箱寸法: Width(X), Depth(Y), Height(Z)
    bw = float(bin_obj.width)
    bd = float(bin_obj.depth)
    bh = float(bin_obj.height)
    
    # 1. 箱の外枠を描画 (ワイヤーフレーム: 点線)
    x_box = [0, bw, bw, 0, 0, 0, bw, bw, 0, 0]
    y_box = [0, 0, bd, bd, 0, 0, 0, bd, bd, 0]
    z_box = [0, 0, 0, 0, 0, bh, bh, bh, bh, bh]
    
    ax.plot(x_box, y_box, z_box, color='black', linestyle='--', linewidth=1.5)
    ax.plot([bw, bw], [0, 0], [0, bh], color='black', linestyle='--')
    ax.plot([bw, bw], [bd, bd], [0, bh], color='black', linestyle='--')
    ax.plot([0, 0], [bd, bd], [0, bh], color='black', linestyle='--')
    
    # 2. カラーパレット
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
    
    # 3. アイテムの描画
    for idx, item in enumerate(bin_obj.items):
        pos = [float(p) for p in item.position]
        
        # py3dbpの配置決定後の正確な寸法を取得
        # get_dimension() は [width, height, depth] を返すため、
        # Matplotlibの軸 (X=Width, Y=Depth, Z=Height) に正確に割り当てる
        dim = [float(d) for d in item.get_dimension()]
        w = dim[0]  # Width  (X軸)
        h = dim[1]  # Height (Z軸)
        d = dim[2]  # Depth  (Y軸)
        
        color = colors[idx % len(colors)]
        
        # 8頂点座標 (X: pos[0], Y: pos[1], Z: pos[2])
        x0, x1 = pos[0], pos[0] + w
        y0, y1 = pos[1], pos[1] + d
        z0, z1 = pos[2], pos[2] + h
        
        # 6面の作成
        verts = [
            [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], # 底面
            [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], # 上面
            [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], # 前面
            [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], # 背面
            [[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]], # 左面
            [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]]  # 右面
        ]
        
        poly = Poly3DCollection(verts, alpha=0.7, facecolor=color, edgecolor='black', linewidth=1)
        ax.add_collection3d(poly)
    
    # 4. 軸設定
    ax.set_xlabel('Width [X] (cm)')
    ax.set_ylabel('Depth [Y] (cm)')
    ax.set_zlabel('Height [Z] (cm)')
    
    # アスペクト比を揃えて箱全体を表示
    max_dim = max(bw, bd, bh)
    ax.set_xlim([0, max_dim])
    ax.set_ylim([0, max_dim])
    ax.set_zlim([0, max_dim])
    
    return fig

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
        
        # 箱マスタ登録
        for _, box in df_boxes.iterrows():
            packer.add_bin(Bin(
                str(box['箱名称']), 
                clean_decimal(box['幅(cm)']), 
                clean_decimal(box['高さ(cm)']), 
                clean_decimal(box['奥行(cm)']), 
                Decimal('100000')  # ★ 無限大に設定して重量判定を除外
            ))
        
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
            
            st.success(f"### 🎉 最適な箱: 【{best_bin.name}】")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("箱の寸法", f"{best_bin.width} x {best_bin.height} x {best_bin.depth} cm")
            m_col2.metric("梱包総重量", f"{best_bin.get_total_weight():.2f} kg", f"上限 {best_bin.max_weight} kg")
            
            # --- 3D配置図の表示 ---
            st.write("**【3D配置図】**")
            fig = plot_3d_packing(best_bin)
            st.pyplot(fig)
            
            st.write("**【配置座標詳細】**")
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
