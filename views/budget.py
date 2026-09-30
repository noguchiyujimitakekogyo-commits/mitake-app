import streamlit as st
import pandas as pd
import altair as alt
import base64
import os
import re
import datetime
from utils.db_client import db  

# 必要な裏方ツールの読み込み
from utils.db_client import db, save_project_to_db
from utils.data_parser import safe_num
from utils.andpad_parser import get_andpad_breakdown, get_hours_from_andpad
from utils.ai_engine import call_jarvis_ai
from config import all_staff_list, YEAR_LIST, MONTH_LIST

def render_budget(projects_db, df_contractor_master, ai_engine_option, GEMINI_API_KEY):
    st.markdown('<div class="section-title">◲ 物件別予算管理・詳細編集</div>', unsafe_allow_html=True)
    search_query = st.text_input("⌕ 物件名、顧客名、または物件番号で絞り込み検索", key="proj_search")

    active_projects = []
    archived_projects = []

    for k, v in projects_db.items():
        if isinstance(v, dict) and k != "_SYSTEM_SETTINGS_":
            if search_query:
                search_target = f"{k} {v.get('client_name', '')} {v.get('project_number', '')}".lower()
                if search_query.lower() not in search_target:
                    continue
            if v.get("status") == "アーカイブ（完了）":
                archived_projects.append(k)
            else:
                active_projects.append(k)

    view_mode = st.radio("表示する物件のステータスを選択", ["進行中の物件", "完了済み物件（アーカイブ）"], horizontal=True)

    budget_selected_project = None
    if view_mode == "進行中の物件": 
        if active_projects: budget_selected_project = st.selectbox("確認・編集する進行中物件を選択", active_projects, key="select_proj_active")
        else: st.info("該当する進行中の物件が見つかりません。")
    else: 
        if archived_projects: budget_selected_project = st.selectbox("確認・編集する完了済み物件を選択", archived_projects, key="select_proj_archived")
        else: st.info("該当する完了済み物件が見つかりません。")

    if budget_selected_project:
        st.markdown("---")
        cur_data = projects_db[budget_selected_project]
        
        def calc_category_totals(detail_list):
            if not detail_list: return 0.0, 0.0
            b_total = sum(safe_num(x.get("実行予算", 0)) for x in detail_list)
            p_total = sum(safe_num(x.get("協力業者支払", 0)) for x in detail_list)
            return b_total, p_total

        b_a, p_a = calc_category_totals(cur_data.get("detail_a", []))
        b_b, p_b = calc_category_totals(cur_data.get("detail_b", []))
        b_c, p_c = calc_category_totals(cur_data.get("detail_c", []))
        b_d, p_d = calc_category_totals(cur_data.get("detail_d", []))
        b_req, p_req = calc_category_totals(cur_data.get("detail_request", []))
        
        action_col1, action_col2 = st.columns([3, 1])
        with action_col1: st.subheader(f"選択中: {budget_selected_project}")
        with action_col2: st.button("✓ 変更を保存する", type="primary", use_container_width=True, key=f"save_top_{budget_selected_project}")

        with st.expander("📌 ステータス変更・削除", expanded=False):
            current_status = projects_db[budget_selected_project].get("status", "進行中")
            if current_status != "アーカイブ（完了）":
                if st.button("アーカイブとして保管する", key=f"btn_archive_{budget_selected_project}"):
                    projects_db[budget_selected_project]["status"] = "アーカイブ（完了）"
                    save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
                    st.success("物件を完了済みへ移動しました！")
                    st.rerun()
            else:
                if st.button("⟲ 進行中に戻す", key=f"btn_unarchive_{budget_selected_project}"):
                    projects_db[budget_selected_project]["status"] = "進行中"
                    save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
                    st.success("進行中に戻しました！")
                    st.rerun()
            st.markdown("---")
            if st.button("✕ 完全に削除する", type="primary", key=f"btn_delete_{budget_selected_project}"):
                if budget_selected_project in projects_db:
                    del projects_db[budget_selected_project]
                    db.collection("projects").document(budget_selected_project).delete()
                st.success("物件を完全に削除しました！")
                st.rerun()

        with st.expander("📝 基本情報（入出金・契約見積を含む）を開く", expanded=True):
            st.markdown("#### 🏢 プロジェクト基本情報")
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                in_client = st.text_input("👤 顧客名", value=cur_data.get("client_name", "未設定"), key=f"c_{budget_selected_project}")
                in_proj_num = st.text_input("🏷 物件番号", value=cur_data.get("project_number", ""), key=f"n_{budget_selected_project}")
                in_sales_rep = st.text_input("👔 営業担当", value=cur_data.get("sales_rep", ""), key=f"r_{budget_selected_project}")
                
            with col_b2:
                in_order_amount = st.number_input("💰 受注金額 (税抜)", value=int(cur_data.get("受注金額", 0)), key=f"o_{budget_selected_project}")
                in_target_hours = st.number_input("⏱ 目標工数 (h)", value=float(cur_data.get("target_hours", 0.0)), key=f"t_{budget_selected_project}")
                saved_dept = cur_data.get("project_dept", "内")
                if saved_dept not in ["内", "設", "電", "P"]: saved_dept = "内"
                in_project_dept = st.selectbox("🏢 担当系統", ["内", "設", "電", "P"], index=["内", "設", "電", "P"].index(saved_dept), key=f"d_{budget_selected_project}")
                
            with col_b3:
                c3_1, c3_2 = st.columns(2)
                with c3_1: in_year = st.selectbox("📅 期", YEAR_LIST, index=YEAR_LIST.index(cur_data.get("project_year", "57期")) if cur_data.get("project_year", "57期") in YEAR_LIST else 4, key=f"y_{budget_selected_project}")
                with c3_2: in_month = st.selectbox("📅 月度", MONTH_LIST, index=MONTH_LIST.index(cur_data.get("project_month", "9月")) if cur_data.get("project_month", "9月") in MONTH_LIST else 8, key=f"m_{budget_selected_project}")
                
                c3_3, c3_4 = st.columns(2)
                with c3_3: in_bunrui1 = st.text_input("分類1", value=cur_data.get("bunrui_1", ""), key=f"b1_{budget_selected_project}")
                with c3_4: in_bunrui2 = st.text_input("分類2", value=cur_data.get("bunrui_2", ""), key=f"b2_{budget_selected_project}")
                in_motouke = st.text_input("元請/下請", value=cur_data.get("motouke_shitauke", ""), key=f"mo_{budget_selected_project}")

            st.markdown("<hr style='margin:10px 0;'><div style='font-size: 14px; font-weight: bold; color: #37352F; margin-bottom: 8px;'>💰 入金スケジュール（着手・中間・完了）</div>", unsafe_allow_html=True)
            dep_cols = st.columns(3)
            with dep_cols[0]:
                st.markdown("<span style='font-size:13px;'>**■ 着手金**</span>", unsafe_allow_html=True)
                in_dep1_m = st.selectbox("入金予定月", ["未定"] + MONTH_LIST, index=(["未定"] + MONTH_LIST).index(cur_data.get("dep1_m", "未定")) if cur_data.get("dep1_m", "未定") in ["未定"] + MONTH_LIST else 0, key=f"d1_m_{budget_selected_project}")
                in_dep1_amt = st.number_input("金額 (税抜)", value=int(cur_data.get("dep1_amt", 0)), step=100000, key=f"d1_a_{budget_selected_project}")
            with dep_cols[1]:
                st.markdown("<span style='font-size:13px;'>**■ 中間金**</span>", unsafe_allow_html=True)
                in_dep2_m = st.selectbox("入金予定月", ["未定"] + MONTH_LIST, index=(["未定"] + MONTH_LIST).index(cur_data.get("dep2_m", "未定")) if cur_data.get("dep2_m", "未定") in ["未定"] + MONTH_LIST else 0, key=f"d2_m_{budget_selected_project}")
                in_dep2_amt = st.number_input("金額 (税抜)", value=int(cur_data.get("dep2_amt", 0)), step=100000, key=f"d2_a_{budget_selected_project}")
            with dep_cols[2]:
                st.markdown("<span style='font-size:13px;'>**■ 完了金**</span>", unsafe_allow_html=True)
                in_dep3_m = st.selectbox("入金予定月", ["未定"] + MONTH_LIST, index=(["未定"] + MONTH_LIST).index(cur_data.get("dep3_m", "未定")) if cur_data.get("dep3_m", "未定") in ["未定"] + MONTH_LIST else 0, key=f"d3_m_{budget_selected_project}")
                in_dep3_amt = st.number_input("金額 (税抜)", value=int(cur_data.get("dep3_amt", 0)), step=100000, key=f"d3_a_{budget_selected_project}")
            
            inflow_sum = in_dep1_amt + in_dep2_amt + in_dep3_amt
            if inflow_sum != in_order_amount and in_order_amount > 0:
                st.markdown(f"<div style='font-size: 12px; color: #e53e3e; margin-top: 5px;'>⚠ 入金予定の合計 (¥{inflow_sum:,.0f}) が受注金額と一致していません。差額: ¥{in_order_amount - inflow_sum:,.0f}</div>", unsafe_allow_html=True)
            elif inflow_sum == in_order_amount and in_order_amount > 0:
                st.markdown(f"<div style='font-size: 12px; color: #48BB78; margin-top: 5px;'>✓ 入金予定と受注金額が一致しています。</div>", unsafe_allow_html=True)

            st.markdown("---")
            url_col1, url_col2 = st.columns([4, 1])
            with url_col1: in_andpad_url = st.text_input("↗ ANDPAD 物件URL", value=cur_data.get("andpad_url", ""), placeholder="https://andpad.jp/...", key=f"and_url_{budget_selected_project}")
            with url_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if in_andpad_url: st.link_button("↗ ANDPADを開く", in_andpad_url, use_container_width=True)
                else: st.button("↗ ANDPADを開く", disabled=True, use_container_width=True, key=f"and_btn_{budget_selected_project}")

            st.markdown("---")
            st.markdown("#### 🏢 契約見積情報")
            in_estimate_memo = st.text_area("＜見積内容・金額メモ＞", value=cur_data.get("estimate_memo", ""), height=80, key=f"em_{budget_selected_project}")
            
            saved_est_file = cur_data.get("estimate_file", "")
            if saved_est_file and os.path.exists(saved_est_file):
                st.success(f"添付済み: {os.path.basename(saved_est_file)}")
                col_dl, col_view = st.columns([1, 4])
                with col_dl:
                    with open(saved_est_file, "rb") as f:
                        st.download_button("↓ ダウンロード", f, file_name=os.path.basename(saved_est_file), key=f"dl_{budget_selected_project}", use_container_width=True)
                with col_view:
                    if saved_est_file.lower().endswith('.pdf'):
                        with open(saved_est_file, "rb") as f:
                            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="250" style="border: none;"></iframe>'
                        st.markdown(pdf_display, unsafe_allow_html=True)
            new_est_file = st.file_uploader("新しい見積書をアップロード（上書きされます）", type=["pdf", "xlsx", "xls", "csv", "png", "jpg"], key=f"up_{budget_selected_project}")

        # ==========================================
        # 📊 営業計算書 計画サマリー変数準備
        # ==========================================
        p_order = in_order_amount
        p_genka = safe_num(cur_data.get('summary_koji_genka', 0))
        p_romu = safe_num(cur_data.get('summary_romuhi', 0))
        p_sogieki = safe_num(cur_data.get('summary_uriage_sorieki', 0))
        p_hankan = safe_num(cur_data.get('summary_han_kan_hi', 0))
        p_eigyo = safe_num(cur_data.get('summary_eigyorieki', 0))
        p_jikko = safe_num(cur_data.get('summary_jikko_yosan_rieki', 0))

        # ==========================================
        # 📄 営業計算書（ドキュメントプレビュー ＆ 保管）
        # ==========================================
        with st.container(border=True):
            st.markdown("#### 📄 営業計算書（ドキュメントプレビュー ＆ 保管）")
            
            with st.expander("📊 営業計算書 計画サマリー（AI/自動取込）を開く", expanded=False):
                sum_col1, sum_col2 = st.columns([1.5, 1])
                with sum_col1:
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        st.markdown("<div class='formula-box'><b>【1】受注金額</b> = ベースとなる請負金額</div>", unsafe_allow_html=True)
                        st.metric("受注金額", f"¥{p_order:,.0f}")
                        st.markdown("<div class='formula-box'><b>【2】工事原価合計</b> = 材料費 + 外注費 + 現場経費 + 労務費</div>", unsafe_allow_html=True)
                        st.metric("工事原価合計 (うち労務費)", f"¥{p_genka:,.0f}", delta=f"内 労務費: ¥{p_romu:,.0f}", delta_color="off")
                        st.markdown("<div class='formula-box'><b>【3】売上総利益</b> = 受注金額【1】 - 工事原価合計【2】</div>", unsafe_allow_html=True)
                        soriritsu = cur_data.get('summary_uriage_soriritsu', 0)
                        soriritsu_disp = soriritsu * 100 if 0 < soriritsu < 1 else soriritsu
                        st.metric("売上総利益 (粗利率)", f"¥{p_sogieki:,.0f}", delta=f"粗利率: {soriritsu_disp:.1f}%", delta_color="off")
                    with col_f2:
                        st.markdown("<div class='formula-box'><b>【4】販売管理費</b> = 会社の運営に必要な経費</div>", unsafe_allow_html=True)
                        st.metric("販売管理費", f"¥{p_hankan:,.0f}")
                        st.markdown("<div class='formula-box'><b>【5】営業利益</b> = 売上総利益【3】 - 販管費【4】</div>", unsafe_allow_html=True)
                        st.metric("営業利益", f"¥{p_eigyo:,.0f}")
                        st.markdown("<div class='formula-box'><b>【6】実行予算利益</b> = 売上総利益【3】 - (販管費【4】+営業利益【5】)</div>", unsafe_allow_html=True)
                        jikko_riritsu = cur_data.get('summary_jikko_yosan_riritsu', 0)
                        jikko_riritsu_disp = jikko_riritsu * 100 if 0 < jikko_riritsu < 1 else jikko_riritsu
                        st.metric("実行予算利益 (予算粗利率)", f"¥{p_jikko:,.0f}", delta=f"予算粗利率: {jikko_riritsu_disp:.1f}%", delta_color="off")

                with sum_col2:
                    if p_order > 0:
                        st.markdown("##### 受注金額の内訳構成比")
                        df_summary_chart = pd.DataFrame([{"内訳": "工事原価", "金額": p_genka, "割合": (p_genka/p_order*100)}, {"内訳": "販売管理費", "金額": p_hankan, "割合": (p_hankan/p_order*100)}, {"内訳": "営業利益", "金額": p_eigyo, "割合": (p_eigyo/p_order*100)}])
                        chart_summary = alt.Chart(df_summary_chart).mark_arc(innerRadius=60).encode(theta=alt.Theta(field="金額", type="quantitative"), color=alt.Color('内訳:N', scale=alt.Scale(domain=['工事原価', '販売管理費', '営業利益'], range=['#e53e3e', '#d69e2e', '#3182ce'])), tooltip=['内訳', '金額', '割合']).properties(height=280)
                        st.altair_chart(chart_summary, use_container_width=True)

            saved_img = cur_data.get("calc_image", "")
            if saved_img and os.path.exists(saved_img):
                ext_lower = saved_img.lower()
                if ext_lower.endswith(('.xlsx', '.xls', '.csv')):
                    st.success(f"保管済みExcelデータ: {os.path.basename(saved_img)}")
                    with open(saved_img, "rb") as f: st.download_button("↓ Excel/CSVをダウンロード", f, file_name=os.path.basename(saved_img), key=f"dl_xl_{budget_selected_project}")
                elif ext_lower.endswith('.pdf'):
                    st.success(f"保管済みPDF: {os.path.basename(saved_img)}")
                    with open(saved_img, "rb") as f: base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="450" type="application/pdf"></iframe>', unsafe_allow_html=True)
                else:
                    try: st.image(saved_img, use_container_width=True)
                    except Exception as e:
                        st.warning("画像形式が認識できませんでした。")
                        with open(saved_img, "rb") as f: st.download_button("↓ ファイルをダウンロード", f, file_name=os.path.basename(saved_img), key=f"dl_img_{budget_selected_project}")
            else: st.info("現在、この物件に保管されている営業計算書プレビューデータはありません。")

        # ==========================================
        # 📊 総合収支 ＆ 予実・進捗管理 (統合レイアウト)
        # ==========================================
        with st.container(border=True):
            st.markdown("#### 📊 総合収支 ＆ 予実・進捗管理")
            
            grid_payment_sum = p_a + p_b + p_c + p_d + p_req
            actual_genka = grid_payment_sum  
            actual_sogieki = p_order - actual_genka   
            actual_jikko = actual_sogieki - p_hankan - p_eigyo 

            st.markdown("##### ⏱ 出来高・進捗 ＆ 工数管理")
            prog_ratio = 1.0
            v_dekidaka = p_order * prog_ratio
            v_deki_minus_genka = v_dekidaka - actual_genka
            
            total_actual_hours = 0.0
            aliases = cur_data.get("aliases", [])
            ignored_keys = cur_data.get("ignored_andpad_keys", [])
            for dept in ["staff_setsubi", "staff_naisou", "staff_denki", "staff_pm"]:
                for s in cur_data.get(dept, []):
                    total_actual_hours += get_hours_from_andpad(s, budget_selected_project, in_proj_num, aliases, ignored_keys)
                    
            target_h = float(cur_data.get("target_hours", 0.0))
            diff_h = target_h - total_actual_hours
            
            d_col1, d_col2, d_col3 = st.columns(3)
            d_col1.metric("完了基準 売上", f"¥{v_dekidaka:,.0f}")
            if v_deki_minus_genka < 0: d_col2.metric("売上－実績原価", f"¥{v_deki_minus_genka:,.0f}", delta="原価超過ペース", delta_color="inverse")
            else: d_col2.metric("売上－実績原価", f"¥{v_deki_minus_genka:,.0f}", delta="正常ペース", delta_color="normal")
            
            if target_h > 0:
                h_rate = (total_actual_hours / target_h) * 100
                if total_actual_hours > target_h: d_col3.metric("総投入工数 (実績)", f"{total_actual_hours:.1f} h", delta=f"⚠ 予定 {target_h:.1f}h 越え", delta_color="inverse")
                else: d_col3.metric("総投入工数 (実績)", f"{total_actual_hours:.1f} h", delta=f"残 {diff_h:.1f}h (消化 {h_rate:.1f}%)", delta_color="normal")
            else:
                d_col3.metric("総投入工数 (実績)", f"{total_actual_hours:.1f} h", "目標工数未設定")

            st.markdown("<hr style='margin: 15px 0;'>", unsafe_allow_html=True)
            st.markdown("##### 📉 プロジェクト収支 ＆ 予実比較")
            st.info("※ 「実績 (現在)」の工事原価は、下部の仕入先別原価（詳細項目）で登録された金額のみを集計しています。")
            
            col_tbl, col_cht = st.columns([1.3, 1])
            with col_tbl:
                compare_rows = [
                    {"項目": "1. 受注金額", "計画 (予算)": p_order, "実績 (現在)": p_order},
                    {"項目": "2. 工事原価", "計画 (予算)": p_genka, "実績 (現在)": actual_genka},
                    {"項目": "3. 売上総利益", "計画 (予算)": p_sogieki, "実績 (現在)": actual_sogieki},
                    {"項目": "4. 販売管理費", "計画 (予算)": p_hankan, "実績 (現在)": p_hankan},
                    {"項目": "5. 営業利益", "計画 (予算)": p_eigyo, "実績 (現在)": (actual_sogieki - p_hankan)},
                    {"項目": "6. 実行予算利益", "計画 (予算)": p_jikko, "実績 (現在)": actual_jikko}
                ]
                df_comp = pd.DataFrame(compare_rows)
                disp_rows = []
                for row in compare_rows:
                    item, plan, act = row["項目"], row["計画 (予算)"], row["実績 (現在)"]
                    diff = act - plan
                    plan_str, act_str = f"¥ {plan:,.0f}", f"¥ {act:,.0f}"
                    
                    if item in ["2. 工事原価", "4. 販売管理費"]: diff_str = f"¥ {diff:,.0f}" if diff == 0 else (f"✕ ¥ {diff:,.0f} (超過)" if diff > 0 else f"〇 ¥ {diff:,.0f} (削減)")
                    else: diff_str = f"¥ {diff:,.0f}" if diff == 0 else (f"〇 ¥ {diff:,.0f} (上振れ)" if diff > 0 else f"✕ ¥ {diff:,.0f} (下振れ)")
                    
                    if item in ["3. 売上総利益", "6. 実行予算利益"]:
                        plan_rate = (plan / p_order * 100) if p_order > 0 else 0
                        act_rate = (act / p_order * 100) if p_order > 0 else 0
                        plan_str += f" ({plan_rate:.1f}%)"
                        act_str += f" ({act_rate:.1f}%)"
                        
                    disp_rows.append({"指標 (6項目)": item, "計画 (予算)": plan_str, "実績 (現在)": act_str, "差額 (実績 - 予算)": diff_str})
                st.dataframe(pd.DataFrame(disp_rows), use_container_width=True, hide_index=True)
                
            with col_cht:
                df_chart = df_comp.melt("項目", var_name="種類", value_name="金額")
                sort_order = ["1. 受注金額", "2. 工事原価", "3. 売上総利益", "4. 販売管理費", "5. 営業利益", "6. 実行予算利益"]
                chart = alt.Chart(df_chart).mark_bar().encode(
                    x=alt.X('項目:N', sort=sort_order, title=None, axis=alt.Axis(labelAngle=-20, labelFontSize=10)),
                    y=alt.Y('金額:Q', title="金額 (円)"),
                    xOffset='種類:N',
                    color=alt.Color('種類:N', scale=alt.Scale(domain=['計画 (予算)', '実績 (現在)'], range=['#90cdf4', '#2b6cb0']), legend=alt.Legend(orient='top', title=None)),
                    tooltip=['項目', '種類', '金額']
                ).properties(height=250)
                st.altair_chart(chart, use_container_width=True)

        with st.container(border=True):
            st.markdown("#### 👥 現場投入メンバー（工数・就業時間）")
            col_st1, col_st2, col_st3, col_st4 = st.columns(4)
            
            def render_staff_col(dept_key, title, col):
                with col:
                    st.markdown(f"**{title}**")
                    in_staff = st.multiselect("担当メンバー選択", all_staff_list, default=cur_data.get(dept_key, []), key=f"sf_{dept_key}_{budget_selected_project}")
                    for s in in_staff:
                        h, recs = get_andpad_breakdown(s, budget_selected_project, in_proj_num, aliases, ignored_keys)
                        if recs:
                            with st.expander(f"{s} : {h:.1f} h"):
                                df_recs = pd.DataFrame(recs)
                                if "key" not in df_recs.columns:
                                    df_recs["key"] = [f"key_{i}" for i in range(len(df_recs))]
                                if "除外" not in df_recs.columns:
                                    df_recs["除外"] = False

                                edited = st.data_editor(
                                    df_recs,
                                    column_config={
                                        "除外": st.column_config.CheckboxColumn("除外", default=False),
                                        "key": None,
                                        "日付": st.column_config.TextColumn("日付", disabled=True),
                                        "ANDPAD打刻名": st.column_config.TextColumn("打刻名", disabled=True),
                                        "時間 (h)": st.column_config.NumberColumn("時間 (h)", disabled=True)
                                    },
                                    hide_index=True,
                                    key=f"reced_{s}_{budget_selected_project}"
                                )
                                keys_to_del = edited[edited["除外"] == True]["key"].tolist()
                                if keys_to_del:
                                    if st.button(f"✕ 除外を確定", key=f"del_{s}_{budget_selected_project}"):
                                        if "ignored_andpad_keys" not in projects_db[budget_selected_project]:
                                            projects_db[budget_selected_project]["ignored_andpad_keys"] = []
                                        projects_db[budget_selected_project]["ignored_andpad_keys"].extend(keys_to_del)
                                        save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
                                        st.rerun()
                        else: st.write(f"・{s}: `{h:.1f} h`")
                return in_staff

            in_staff_setsubi = render_staff_col("staff_setsubi", "第1管理部（設備）", col_st1)
            in_staff_naisou = render_staff_col("staff_naisou", "第2管理部（内装）", col_st2)
            in_staff_denki = render_staff_col("staff_denki", "第3管理部（電気）", col_st3)
            in_staff_pm = render_staff_col("staff_pm", "PM室（厨房等）", col_st4)

        # ==========================================
        # 🛠 工事カテゴリ別内訳管理 (全幅)
        # ==========================================
        with st.container(border=True):
            st.markdown("#### 🛠 工事カテゴリ別内訳管理")
            st.info("※ 各業者の「支払予定月」を設定すると、ダッシュボードのキャッシュフローに自動反映されます。")
            df_vs = pd.DataFrame([
                {"カテゴリ": "内装(内)", "予算": b_a, "実績": p_a},
                {"カテゴリ": "設備(設)", "予算": b_b, "実績": p_b},
                {"カテゴリ": "電気(電)", "予算": b_c, "実績": p_c},
                {"カテゴリ": "厨房(P)", "予算": b_d, "実績": p_d},
                {"カテゴリ": "依頼業社", "予算": b_req, "実績": p_req},
            ])
            cat_budget = alt.Chart(df_vs).mark_bar(color='#E2E8F0', size=30).encode(
                x=alt.X('カテゴリ:N', sort=["内装(内)", "設備(設)", "電気(電)", "厨房(P)", "依頼業社"], title=None),
                y=alt.Y('予算:Q', title="金額 (円)"),
                tooltip=[alt.Tooltip('カテゴリ:N'), alt.Tooltip('予算:Q', format=',.0f')]
            )
            cat_actual = alt.Chart(df_vs).mark_bar(size=15).encode(
                x=alt.X('カテゴリ:N', sort=["内装(内)", "設備(設)", "電気(電)", "厨房(P)", "依頼業社"]),
                y=alt.Y('実績:Q'),
                color=alt.condition(alt.datum['実績'] > alt.datum['予算'], alt.value('#e53e3e'), alt.value('#3182ce')),
                tooltip=[alt.Tooltip('カテゴリ:N'), alt.Tooltip('実績:Q', format=',.0f')]
            )
            st.altair_chart((cat_budget + cat_actual).properties(height=250), use_container_width=True)
            
            contractor_names = [str(n).strip() for n in df_contractor_master["業者・工種名"].tolist() if str(n).strip() != "" and str(n).strip().lower() != "nan"]
            used_names = []
            for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"]:
                for item in cur_data.get(cat, []):
                    n = str(item.get("業者・工種名", "")).strip()
                    if n and n not in contractor_names and n not in used_names: used_names.append(n)
            
            contractor_options = [""] + sorted(list(set(contractor_names + used_names)))
            
            g_conf = {
                "工種名": st.column_config.TextColumn("読取り種類", disabled=False, width="medium"), 
                "業者管理番号": None,  
                "業者・工種名": st.column_config.SelectboxColumn("業者・工種名", options=contractor_options, width="large"),
                "実行予算": st.column_config.NumberColumn("実行予算 (青)", width="medium"),
                "支払予定月": st.column_config.SelectboxColumn("支払予定月", options=["未定"] + MONTH_LIST, default="未定", width="small"),
                "協力業者支払": st.column_config.NumberColumn("協力業者支払 (赤/実績)", width="medium"),
                "完了金額": None
            }
            
            if "update_key" not in st.session_state: st.session_state.update_key = 0
            u_key = st.session_state.update_key
            
            def clean_req_df(data_list):
                df = pd.DataFrame(data_list)
                if df.empty: return pd.DataFrame(columns=["移動先", "工種名", "業者・工種名", "実行予算", "支払予定月", "協力業者支払", "完了金額"])
                df = df.drop(columns=["業者管理番号", "顧客管理番号"], errors='ignore')
                df = df.fillna({"移動先": "-", "工種名": "", "業者・工種名": "", "実行予算": 0, "支払予定月": "未定", "協力業者支払": 0, "完了金額": 0})
                if "支払予定月" not in df.columns: df["支払予定月"] = "未定"
                for col in ["実行予算", "協力業者支払", "完了金額"]:
                    if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                return df
                
            def clean_df(data_list):
                df = pd.DataFrame(data_list)
                if df.empty: return pd.DataFrame(columns=["工種名", "業者・工種名", "実行予算", "支払予定月", "協力業者支払", "完了金額"])
                df = df.drop(columns=["業者管理番号", "顧客管理番号"], errors='ignore')
                df = df.fillna({"工種名": "", "業者・工種名": "", "実行予算": 0, "支払予定月": "未定", "協力業者支払": 0, "完了金額": 0})
                if "支払予定月" not in df.columns: df["支払予定月"] = "未定"
                for col in ["実行予算", "協力業者支払", "完了金額"]:
                    if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                return df

            st.markdown("##### 詳細項目を展開して編集")
            with st.expander("▶ 依頼業社", expanded=True):
                req_conf = {
                    "移動先": st.column_config.SelectboxColumn("移動先", options=["-", "内", "設", "電", "P"], default="-", width="small"),
                    "工種名": st.column_config.TextColumn("読取り種類", width="medium"),
                    "業者・工種名": st.column_config.SelectboxColumn("業者・工種名", options=contractor_options, width="large"),
                    "実行予算": st.column_config.NumberColumn("実行予算 (青)", width="medium"),
                    "支払予定月": st.column_config.SelectboxColumn("支払予定月", options=["未定"] + MONTH_LIST, default="未定", width="small"),
                    "協力業者支払": st.column_config.NumberColumn("協力業者支払 (赤/実績)", width="medium"),
                    "完了金額": None
                }
                df_req = clean_req_df(cur_data.get("detail_request", []))
                ed_req = st.data_editor(df_req, column_config=req_conf, num_rows="dynamic", key=f"ed_r_{budget_selected_project}_{u_key}_v_sidebar", use_container_width=True, hide_index=True)
                if st.button("✕ 依頼業社をクリア", key=f"cr_{budget_selected_project}"):
                    projects_db[budget_selected_project]["detail_request"] = []
                    save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
                    st.rerun()
                    
            with st.expander("▶ 内 (内装)", expanded=False):
                ed_a = st.data_editor(clean_df(cur_data.get("detail_a", [])), use_container_width=True, hide_index=True, column_config=g_conf, key=f"ed_a_{budget_selected_project}_{u_key}_v_sidebar", num_rows="dynamic")
                if st.button("✕ 内装をクリア", key=f"ca_{budget_selected_project}"):
                    projects_db[budget_selected_project]["detail_a"] = []
                    save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
                    st.rerun()

            with st.expander("▶ 設 (設備)", expanded=False):
                ed_b = st.data_editor(clean_df(cur_data.get("detail_b", [])), use_container_width=True, hide_index=True, column_config=g_conf, key=f"ed_b_{budget_selected_project}_{u_key}_v_sidebar", num_rows="dynamic")

            with st.expander("▶ 電 (電気)", expanded=False):
                ed_c = st.data_editor(clean_df(cur_data.get("detail_c", [])), use_container_width=True, hide_index=True, column_config=g_conf, key=f"ed_c_{budget_selected_project}_{u_key}_v_sidebar", num_rows="dynamic")

            with st.expander("▶ P (厨房)", expanded=False):
                ed_d = st.data_editor(clean_df(cur_data.get("detail_d", [])), use_container_width=True, hide_index=True, column_config=g_conf, key=f"ed_d_{budget_selected_project}_{u_key}_v_sidebar", num_rows="dynamic")

        # ==========================================
        # 📑 メモ & 過去の議事録
        # ==========================================
        with st.container(border=True):
            st.markdown("#### 📑 メモ")
            st.markdown("#### 📝 過去の会議議事録")

            current_project = budget_selected_project
            minutes_list = []

            try:
                # Firestoreからこの物件に紐づく議事録を検索して取得
                minutes_ref = (
                    db.collection("minutes")
                    .where("project_name", "==", current_project)
                    .stream()
                )
                minutes_list = [doc.to_dict() for doc in minutes_ref]
                
                # 日付の新しい順に並び替える
                minutes_list.sort(key=lambda x: x.get("meeting_date", ""), reverse=True)

                if minutes_list:
                    st.success(f"この物件の過去の打ち合わせ記録が {len(minutes_list)} 件あります。")
                    for minute in minutes_list:
                        date_str = minute.get("meeting_date", "日付不明")
                        with st.expander(f"📅 {date_str} の議事録（AI要約）"):
                            st.markdown(minute.get("summary", "要約データなし"))
                            with st.popover("当時の生テキスト・メモを確認"):
                                st.text(minute.get("raw_text", ""))
                else:
                    st.info("この物件に紐づく過去の議事録はまだありません。")

            except Exception as e:
                st.error(f"議事録の読み込みに失敗しました: {e}")

            # 議事録以外の、物件固有のちょっとしたメモを残す欄は残しておく
            st.markdown("---")
            in_eval = st.text_area("＜現場での評価＞", value=cur_data.get("eval_memo", ""), key=f"ev_{budget_selected_project}")
            in_budg = st.text_area("＜予算経緯＞", value=cur_data.get("budget_memo", ""), height=100, key=f"bm_{budget_selected_project}")
            in_materials = st.text_area("＜建材・仕様の記録メモ＞", value=cur_data.get("materials_memo", ""), key=f"matm_{budget_selected_project}")

        # ==========================================
        # 🤖 プロジェクト専属AIアシスタント (JARVIS機能)
        # ==========================================
        with st.container(border=True):
            st.markdown(f"#### 🤖 プロジェクト専属AI (JARVIS) <small style='font-size:13px; color:#777;'>[稼働中: {ai_engine_option}]</small>", unsafe_allow_html=True)
            st.info("この物件の「基本情報」「予算」「議事録・メモ」をすべて記憶しています。制限なくあらゆる指示や質問が可能です。")
            
            chat_key = f"chat_history_{budget_selected_project}"
            if chat_key not in st.session_state:
                st.session_state[chat_key] = []
                
            history = st.session_state[chat_key]
            for i in range(0, len(history), 2):
                q_msg = history[i]
                a_msg = history[i+1] if (i+1) < len(history) else None
                title_text = q_msg['content'][:40] + ("..." if len(q_msg['content'])>40 else "")
                is_latest = (i >= len(history) - 2)
                with st.expander(f" 👤 Q: {title_text}", expanded=is_latest):
                    st.markdown(f"**あなた:**\n{q_msg['content']}")
                    st.markdown("---")
                    if a_msg:
                        st.markdown(f"**🤖 JARVIS:**\n{a_msg['content']}")
            
            user_query = st.chat_input("例：過去の議事録から次のToDoを抽出して / お客様への案内メールを書いて", key=f"chat_input_{budget_selected_project}")
            
            if user_query:
                st.session_state[chat_key].append({"role": "user", "content": user_query})
                with st.chat_message("user"):
                    st.write(user_query)
                    
                with st.chat_message("assistant"):
                    with st.spinner("JARVISが物件データと議事録を解析中..."):
                        
                        # 先ほどFirestoreから取得した minutes_list をテキスト化してAIに渡す
                        minutes_text = ""
                        if minutes_list:
                            minutes_text = "\n\n=== 🔗 物件の過去の議事録 ===\n"
                            for m in minutes_list:
                                minutes_text += f"📅 {m.get('meeting_date', '')}\n{m.get('summary', '')}\n\n"

                        context = f"""=== 現在開いている物件情報 ===
【物件名】{budget_selected_project}
【顧客】{in_client}
【予算/実績】予算:{b_a+b_b+b_c+b_d} 実績:{p_a+p_b+p_c+p_d}

{minutes_text if minutes_text else "過去の議事録データなし"}
"""
                        sys_prompt = "あなたは優秀なプロジェクト専属AI（JARVIS）です。\n【絶対厳守ルール】\n「🔗 物件の過去の議事録」にテキストが含まれている場合、そのデータを最優先して必ず質問に答えてください。\nデータが渡されているのに「情報がありません」と答えることは絶対に許されません。提供されたテキストの中から該当する回答を出力してください。"

                        ai_reply = call_jarvis_ai(sys_prompt, f"{context}\n\nユーザーの質問: {user_query}", model_choice=ai_engine_option, gemini_api_key=GEMINI_API_KEY) 

                        final_res = f"**【システム解析レポート】**\n\n---\n{ai_reply}"
                        
                        st.session_state[chat_key].append({"role": "assistant", "content": final_res})
                    st.rerun()

        # ----- 変更内容の保存処理 -----
        if st.button(f"✓ 【{budget_selected_project}】 の変更を保存", use_container_width=True, type="primary", key=f"save_bottom_{budget_selected_project}") or st.session_state.get(f"save_top_{budget_selected_project}", False):
            projects_db[budget_selected_project]["client_name"] = in_client
            projects_db[budget_selected_project]["project_number"] = in_proj_num
            projects_db[budget_selected_project]["project_year"] = in_year
            projects_db[budget_selected_project]["project_month"] = in_month
            projects_db[budget_selected_project]["bunrui_1"] = in_bunrui1
            projects_db[budget_selected_project]["bunrui_2"] = in_bunrui2
            projects_db[budget_selected_project]["motouke_shitauke"] = in_motouke
            projects_db[budget_selected_project]["受注金額"] = in_order_amount
            projects_db[budget_selected_project]["target_hours"] = in_target_hours 
            projects_db[budget_selected_project]["progress_rate"] = cur_data.get("progress_rate", 100.0) 
            projects_db[budget_selected_project]["project_dept"] = in_project_dept
            projects_db[budget_selected_project]["sales_rep"] = in_sales_rep 
            projects_db[budget_selected_project]["eval_memo"] = in_eval
            projects_db[budget_selected_project]["budget_memo"] = in_budg
            projects_db[budget_selected_project]["materials_memo"] = in_materials
            projects_db[budget_selected_project]["andpad_url"] = in_andpad_url
            projects_db[budget_selected_project]["estimate_memo"] = in_estimate_memo
            
            projects_db[budget_selected_project]["dep1_amt"] = in_dep1_amt
            projects_db[budget_selected_project]["dep1_m"] = in_dep1_m
            projects_db[budget_selected_project]["dep2_amt"] = in_dep2_amt
            projects_db[budget_selected_project]["dep2_m"] = in_dep2_m
            projects_db[budget_selected_project]["dep3_amt"] = in_dep3_amt
            projects_db[budget_selected_project]["dep3_m"] = in_dep3_m

            def map_contractor_id(records):
                for r in records:
                    c_name = r.get("業者・工種名", "")
                    if c_name:
                        m = df_contractor_master[df_contractor_master["業者・工種名"] == c_name]
                        if not m.empty: r["業者管理番号"] = m.iloc[0]["業者管理番号"]
                        else: r["業者管理番号"] = ""
                    else: r["業者管理番号"] = ""
                return records

            projects_db[budget_selected_project]["detail_a"] = map_contractor_id(ed_a.to_dict('records'))
            projects_db[budget_selected_project]["detail_b"] = map_contractor_id(ed_b.to_dict('records'))
            projects_db[budget_selected_project]["detail_c"] = map_contractor_id(ed_c.to_dict('records'))
            projects_db[budget_selected_project]["detail_d"] = map_contractor_id(ed_d.to_dict('records'))
            
            ed_req_mapped = map_contractor_id(ed_req.to_dict('records'))
            new_req = []
            for row in ed_req_mapped:
                dest = row.get("移動先", "-")
                if not row.get("工種名") and not row.get("業者管理番号") and not row.get("業者・工種名"): continue
                if dest == "-": new_req.append(row)
                else:
                    row["移動先"] = "-"
                    if dest == "内": projects_db[budget_selected_project]["detail_a"].append(row)
                    elif dest == "設": projects_db[budget_selected_project]["detail_b"].append(row)
                    elif dest == "電": projects_db[budget_selected_project]["detail_c"].append(row)
                    elif dest == "P": projects_db[budget_selected_project]["detail_d"].append(row)
            
            projects_db[budget_selected_project]["detail_request"] = new_req
            projects_db[budget_selected_project]["staff_setsubi"] = in_staff_setsubi
            projects_db[budget_selected_project]["staff_naisou"] = in_staff_naisou
            projects_db[budget_selected_project]["staff_denki"] = in_staff_denki
            projects_db[budget_selected_project]["staff_pm"] = in_staff_pm

            save_project_to_db(budget_selected_project, projects_db[budget_selected_project])
            st.success("保存完了！全体の売上集計へ反映されました。")
            st.session_state.update_key += 1
            st.rerun()