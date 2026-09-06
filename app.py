# --- 判定処理部分の修正 ---
if st.button("🚀 推奨サイズを判定する", type="primary", use_container_width=True, disabled=not selected_ids):
    packer = Packer()
    box_weight_map = {}
    
    # 登録されている箱の情報を保持
    box_specs = {}
    for _, box in df_boxes.iterrows():
        b_name = str(box['箱名称'])
        bw = clean_decimal(box['幅(cm)'])
        bh = clean_decimal(box['高さ(cm)'])
        bd = clean_decimal(box['奥行(cm)'])
        b_weight = clean_decimal(box['箱重量(kg)'])
        
        box_weight_map[b_name] = b_weight
        box_specs[b_name] = (bw, bh, bd)
        
        packer.add_bin(Bin(
            b_name, 
            bw, bh, bd, 
            Decimal('999999')
        ))
    
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
        
    packer.pack(bigger_first=True)
    
    fitted_bins = []
    for b in packer.bins:
        # 全商品が格納できた箱のみを抽出
        if len(b.items) == total_items_count:
            # 実際に配置された商品の最小外包サイズを計算
            min_x = min([float(item.position[0]) for item in b.items])
            max_x = max([float(item.position[0]) + float(item.width) for item in b.items])
            min_y = min([float(item.position[1]) for item in b.items])
            max_y = max([float(item.position[1]) + float(item.height) for item in b.items])
            min_z = min([float(item.position[2]) for item in b.items])
            max_z = max([float(item.position[2]) + float(item.depth) for item in b.items])
            
            actual_w = max_x - min_x
            actual_h = max_y - min_y
            actual_d = max_z - min_z
            
            # 【追加ガード】商品の外寸（ソート済み）が箱の寸法（ソート済み）を収めているか検証
            item_dims = sorted([actual_w, actual_h, actual_d])
            box_dims = sorted([float(b.width), float(b.height), float(b.depth)])
            
            # 商品の最大辺 <= 箱の最大辺、中辺 <= 箱の中辺、最小辺 <= 箱の最小辺 でなければ除外
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
        
        # 1. 判定された箱のスペック
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
