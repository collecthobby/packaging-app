import streamlit as st
import pandas as pd
from urllib.parse import quote
from decimal import Decimal
import re
from py3dbp import Bin, Item, Packer
import plotly.graph_objects as go

# 画面基本設定
st.set_page_config(page_title="梱包サイズ最適化システム", page_icon="📦", layout="wide")
st.title("📦 梱包サイズ最適化システム（全マスタ動的同期）")

if "history" not in st.session_state:
    st.session_state.history = []

SHEET_ID = "13ijkSncdvliXRxUVKVl_xglaxPHTgOD8_hdQFXgE0pc"

def clean_decimal(val) -> Decimal:
    if pd.isna(val):
        return Decimal('0')
    val_str = str(val).strip()
    val_str = val_str.translate(str.maketrans('０１２３４５６７８９．', '0123456789.'))
    val_str = val_str.replace(',', '')
    val_str = re.sub(r'[^0-9.]', '', val_str)
    return Decimal(val_str) if val_str else Decimal('0')

def get_sheet_url(sheet_name: str) -> str:
    encoded_name = quote(sheet_name)
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_name}"

def load_data():
    df_items = pd.read_csv(get_sheet_url("商品マスタ")).dropna(how="all").set_index("商品ID")
    df_boxes = pd.read_csv(get_sheet_url("箱マスタ")).dropna(how="all")
    return df_items, df_boxes

def plot_3d_packing_plotly(bin_obj):
    """Plotlyを使用したインタラクティブな3Dパッキング表示"""
    bw = float(bin_obj.width)
    bh = float(bin_obj.height)
    bd = float(bin_obj.depth)

    fig = go.Figure()

    # 1. 箱の外枠（ワイヤーフレーム）
    # 頂点定義
    x_box = [0, bw, bw, 0, 0, 0, bw, bw, 0, 0, 0, 0, bw, bw, bw, bw]
    y_box = [0, 0, bd, bd, 0, 0, 0, bd, bd, 0, 0, bd, bd, 0, 0, bd]
    z_box = [0, 0, 0, 0, 0, bh, bh, bh, bh, bh, 0, 0, 0, 0, bh, bh]

    fig.add_trace(go.Scatter3d(
        x=x_box, y=y_box, z=z_box,
        mode='lines',
        line=dict(color='black', width=4, dash='dash'),
        name='箱の外枠'
    ))

    # 2. 商品ブロック描画
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']

    for idx, item in enumerate(bin_obj.items):
        pos = [float(p) for p in item.position]
        w = float(item.width)
        h = float(item.height)
        d = float(item.depth)

        x0, x1 = pos[0], pos[0] + w
        y0, y1 = pos[1], pos[1] + d
        z0, z1 = pos[2], pos[2] + h

        # 3D メッシュ（直方体）の作成
        fig.add_trace(go.Mesh3d(
            x=[x0, x1, x1, x0, x0, x1, x1, x0],
            y=[y0, y0, y1, y1, y0, y0, y1, y1],
            z=[z0, z0, z0, z0, z1, z1, z1, z1],
            i=[7, 0, 0, 0, 4, 4, 2, 6, 4, 0, 3, 7],
            j=[3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3],
            k=[0, 7, 5, 3, 6, 7, 1, 1, 1, 5, 2, 2],
            opacity=0.7,
            color=colors[idx % len(colors)],
            name=f"{item.name}"
        ))

    # レイアウト調整
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='幅 [X] (cm)', range=[0, max(bw, bd, bh)]),
            yaxis=dict(title='奥行 [Y] (cm)', range=[0, max(bw, bd, bh)]),
            zaxis=dict(title='高さ [Z] (cm)', range=[0, max(bw, bd, bh)]),
            aspectmode='cube'
        ),
        margin=dict(r=0, l=0, b=0, t=0),
        height=600
    )

    return fig

try:
    df_master, df_boxes = load_data()
except Exception as e:
    st.error("⚠️ スプレッドシートの読み込みに失敗しました。")
    st.exception(e)
    st.stop()

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📋 登録マスタ情報")
    tab1, tab2 = st.tabs(["📦 商品マスタ", "📐 箱マスタ"])
    with tab1:
        st.dataframe(df_master, use_container_width=True)
    with tab2:
        st.dataframe(df_boxes, use_container_width=True)
    if st.button("🔄 最新データに更新"):
        st.rerun()

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
        
        # 箱の登録
        for _, box in df_boxes.iterrows():
            packer.add_bin(Bin(
                str(box['箱名称']), 
                clean_decimal(box['幅(cm)']), 
                clean_decimal(box['高さ(cm)']), 
                clean_decimal(box['奥行(cm)']), 
                Decimal('100000')
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
            
            st.write("**【3D配置図】（ドラッグで360度回転できます）**")
            fig = plot_3d_packing_plotly(best_bin)
            st.plotly_chart(fig, use_container_width=True)
            
            st.write("**【配置詳細】**")
            for item in best_bin.items:
                st.caption(f"・{item.name} -> 配置座標: {item.position}")
                
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": best_bin.name,
                "箱サイズ(cm)": f"{best_bin.width}x{best_bin.height}x{best_bin.depth}",
                "梱包重量": f"{best_bin.get_total_weight():.2f} kg"
            })
        else:
            st.error("⚠️ どの箱にも収まりませんでした。")
            st.session_state.history.insert(0, {
                "注文内容": order_str,
                "判定結果": "適合なし (サイズオーバー)",
                "箱サイズ(cm)": "-",
                "梱包重量": "-"
            })

st.markdown("---")
st.subheader("📜 判定履歴")
if st.session_state.history:
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
    if st.button("🗑️ 履歴をクリア"):
        st.session_state.history = []
        st.rerun()
else:
    st.info("まだ判定履歴はありません。")
