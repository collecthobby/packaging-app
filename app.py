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
        max_edge_res = max(res_w, res_h, res_d)

        orig_3sum = best_box['box_w'] + best_box['box_h'] + best_box['box_d']
        orig_vol = best_box['volume']
        max_edge_orig = max(best_box['box_w'], best_box['box_h'], best_box['box_d'])

        # ------------------------------------------
        # 🎨 テキスト省略（…）を絶対に行わないスタイル調整
        # ------------------------------------------
        st.markdown(
            """
            <style>
            .size-box {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 10px;
                text-align: left;
                margin-bottom: 5px;
            }
            .size-title {
                font-size: 0.8rem;
                color: #6c757d;
                font-weight: 600;
                margin-bottom: 2px;
            }
            .size-num {
                font-size: 1.05rem;
                font-weight: bold;
                color: #1f2937;
                word-break: break-all;
                line-height: 1.2;
            }
            .size-delta {
                font-size: 0.75rem;
                color: #dc2626;
                margin-top: 2px;
            }
            .size-sub {
                font-size: 0.75rem;
                color: #16a34a;
                margin-top: 2px;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        # ------------------------------------------
        # 🎉 1. 最適な箱基本情報
        # ------------------------------------------
        st.success(f"### 🎉 最適な箱: 【{best_box['name']}】")

        # 【加工前の箱（元のサイズ）】
        st.markdown("**📦 加工前の箱（元のサイズ）**")
        orig_col1, orig_col2, orig_col3 = st.columns(3)
        with orig_col1:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">外寸 (幅x高x奥)</div>
                <div class="size-num">{best_box['box_w']:.1f} × {best_box['box_h']:.1f} × {best_box['box_d']:.1f} cm</div>
            </div>""", unsafe_allow_html=True)
        with orig_col2:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">3辺合計</div>
                <div class="size-num">{orig_3sum:.1f} cm</div>
            </div>""", unsafe_allow_html=True)
        with orig_col3:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">容積</div>
                <div class="size-num">{orig_vol/1000:.1f} L</div>
            </div>""", unsafe_allow_html=True)

        # 【1辺カット加工後のサイズ】
        st.markdown("**✂️ 1辺カット加工後のサイズ**")
        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
        with res_col1:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">加工後寸法</div>
                <div class="size-num">{res_w:.1f} × {res_h:.1f} × {res_d:.1f} cm</div>
            </div>""", unsafe_allow_html=True)
        with res_col2:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">加工後3辺合計</div>
                <div class="size-num">{resized_3sum:.1f} cm</div>
                <div class="size-delta">↓ -{orig_3sum - resized_3sum:.1f} cm</div>
            </div>""", unsafe_allow_html=True)
        with res_col3:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">加工後容積</div>
                <div class="size-num">{resized_vol/1000:.1f} L</div>
                <div class="size-delta">↓ -{(orig_vol - resized_vol)/1000:.1f} L</div>
            </div>""", unsafe_allow_html=True)
        with res_col4:
            st.markdown(f"""<div class="size-box">
                <div class="size-title">梱包総重量</div>
                <div class="size-num">{total_pack_weight:.2f} kg</div>
                <div class="size-sub">商品:{raw_items_weight:.2f}kg + 箱:{best_box['box_weight']:.2f}kg</div>
            </div>""", unsafe_allow_html=True)

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

            # 1. 加工前（元のサイズ）での送料計算
            res_orig = calc_carrier_cost(
                df_shipping=df_m,
                total_3sum=orig_3sum,
                total_weight_kg=total_pack_weight,
                box_volume_cm3=orig_vol,
                rule_type=rule_type,
                divisor=divisor,
                max_single_edge=max_edge_orig
            )

            # 2. 加工後（リサイズサイズ）での送料計算
            res_res = calc_carrier_cost(
                df_shipping=df_m,
                total_3sum=resized_3sum,
                total_weight_kg=total_pack_weight,
                box_volume_cm3=resized_vol,
                rule_type=rule_type,
                divisor=divisor,
                max_single_edge=max_edge_res
            )

            for carrier_name in res_res.keys():
                cost_orig = res_orig[carrier_name]["cost"]
                cost_res = res_res[carrier_name]["cost"]
                cat_res = res_res[carrier_name]["cat"]

                # 有効な金額（規格外以外）の処理
                val_orig = cost_orig if cost_orig > 0 else 9999999
                val_res = cost_res if cost_res > 0 else 9999999

                # 差額（お得額）の算出
                if val_orig < 9999999 and val_res < 9999999:
                    saving = val_orig - val_res
                else:
                    saving = 0

                comparison_rows.append({
                    "発送区分/ルール": rule_title,
                    "配送会社/サービス": carrier_name,
                    "加工後 区分": cat_res,
                    "リサイズ前 送料": val_orig,
                    "リサイズ後 送料": val_res,
                    "削減額": saving
                })

        if comparison_rows:
            df_comp = pd.DataFrame(comparison_rows)
            df_comp_sorted = df_comp.sort_values(by="リサイズ後 送料")

            # 表示用に金額フォーマットを調整
            df_comp_display = pd.DataFrame()
            df_comp_display["発送区分/ルール"] = df_comp_sorted["発送区分/ルール"]
            df_comp_display["配送会社/サービス"] = df_comp_sorted["配送会社/サービス"]
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
