import streamlit as st
import pandas as pd
import altair as alt
import os
import json
import re
import datetime

# 必要な裏方ツールの読み込み
from utils.ai_engine import call_jarvis_ai
from config import all_staff_list, YEAR_LIST, MONTH_LIST
from utils.data_parser import safe_num
from utils.andpad_parser import get_hours_from_andpad, ANDPAD_ACC_DIR

def render_dashboard(projects_db, parsed_andpad_data, global_target_year, global_target_month, ai_engine_option, GEMINI_API_KEY, get_staff_total_hours, get_staff_daily_breakdown):
    st.markdown('<div class="section-title">❖ 会社全体ダッシュボード ＆ 実績分析</div>', unsafe_allow_html=True)
    st.info(f"▪ 現在、左のサイドバーで **【{global_target_year}】** と **【{global_target_month}】** が選択されています。売上金額は実際の入金日（入金予定月）をベースに集計されています。")

    term_summary = {year: {"売上": 0.0, "利益": 0.0} for year in YEAR_LIST}
    monthly_data_dict = {m: {"売上": 0.0, "支払": 0.0} for m in MONTH_LIST}
    
    total_sales = total_budget = total_payment = 0
    dash_sales_a = dash_sales_b = dash_sales_c = dash_sales_d = 0
    dept_cost_a = dept_cost_b = dept_cost_c = dept_cost_d = dept_cost_req = 0
    
    contractor_costs_by_name = {}
    project_sales_rows = []

    cf_inflow = {m: 0.0 for m in MONTH_LIST}
    cf_outflow = {m: 0.0 for m in MONTH_LIST}
    contract_month_sales = {m: 0.0 for m in MONTH_LIST}
    contract_total_sales = 0.0

    dept_contract_monthly = {
        "内": {m: 0.0 for m in MONTH_LIST},
        "設": {m: 0.0 for m in MONTH_LIST},
        "電": {m: 0.0 for m in MONTH_LIST},
        "P": {m: 0.0 for m in MONTH_LIST},
    }

    valid_projects_for_ai = {}

    for p_name, p_data in projects_db.items():
        if not isinstance(p_data, dict) or p_name == "_SYSTEM_SETTINGS_": continue
        
        p_year = p_data.get("project_year", "57期")
        p_month = p_data.get("project_month", "9月")
        p_dept = p_data.get("project_dept", "内")
        c_name = p_data.get("client_name", "未設定")
        p_num = p_data.get("project_number", "")
        
        order_amt = safe_num(p_data.get("受注金額", 0))
        
        cost_a = sum(safe_num(x.get("協力業者支払")) for x in p_data.get("detail_a", []))
        cost_b = sum(safe_num(x.get("協力業者支払")) for x in p_data.get("detail_b", []))
        cost_c = sum(safe_num(x.get("協力業者支払")) for x in p_data.get("detail_c", []))
        cost_d = sum(safe_num(x.get("協力業者支払")) for x in p_data.get("detail_d", []))
        cost_req = sum(safe_num(x.get("協力業者支払")) for x in p_data.get("detail_request", []))
        p_cost_total = cost_a + cost_b + cost_c + cost_d + cost_req
        
        dep_sales_map = {m: 0.0 for m in MONTH_LIST}
        has_dep_schedule = False
        for i in range(1, 4):
            d_amt = safe_num(p_data.get(f"dep{i}_amt", 0))
            d_m = str(p_data.get(f"dep{i}_m", ""))
            if d_amt > 0 and d_m in MONTH_LIST:
                has_dep_schedule = True
                dep_sales_map[d_m] += d_amt

        p_sales_total = order_amt if order_amt > 0 else sum(safe_num(x.get("完了金額")) for cat in ["detail_a", "detail_b", "detail_c", "detail_d"] for x in p_data.get(cat, []))

        if not has_dep_schedule and p_sales_total > 0:
            if p_month in dep_sales_map:
                dep_sales_map[p_month] += p_sales_total
        
        if p_year in term_summary:
            term_summary[p_year]["売上"] += order_amt
            term_summary[p_year]["利益"] += (order_amt - p_cost_total)

        if p_year != global_target_year: continue
        
        contract_m = str(p_data.get("dep1_m", "未定"))
        if contract_m not in MONTH_LIST: contract_m = p_month
        if contract_m in contract_month_sales and order_amt > 0:
            contract_month_sales[contract_m] += order_amt
            contract_total_sales += order_amt
            target_dept = p_dept if p_dept in dept_contract_monthly else "内"
            dept_contract_monthly[target_dept][contract_m] += order_amt

        for i in range(1, 4):
            in_amt = safe_num(p_data.get(f"dep{i}_amt", 0))
            in_m = str(p_data.get(f"dep{i}_m", ""))
            if in_m in cf_inflow: cf_inflow[in_m] += in_amt
                
        for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"]:
            for item in p_data.get(cat, []):
                out_amt = safe_num(item.get("協力業者支払", 0))
                out_m = str(item.get("支払予定月", ""))
                if out_m not in MONTH_LIST: out_m = p_month
                if out_m in cf_outflow: cf_outflow[out_m] += out_amt

        grid_budget = sum(safe_num(x.get("実行予算", 0)) for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"] for x in p_data.get(cat, []))
        internal_budget = safe_num(p_data.get('summary_romuhi', 0)) + safe_num(p_data.get('summary_han_kan_hi', 0)) + safe_num(p_data.get('summary_eigyorieki', 0))
        total_budget += (grid_budget + internal_budget)
        
        for m in MONTH_LIST:
            monthly_data_dict[m]["支払"] += (p_cost_total if p_month == m else 0.0)
            monthly_data_dict[m]["売上"] += dep_sales_map[m]

        is_payment_month_match = (global_target_month == "通期（全月合計）") or (p_month == global_target_month)
        
        if global_target_month == "通期（全月合計）":
            m_sales_for_dash = sum(dep_sales_map.values())
            m_payment_for_dash = p_cost_total
        else:
            m_sales_for_dash = dep_sales_map.get(global_target_month, 0.0)
            m_payment_for_dash = p_cost_total if is_payment_month_match else 0.0
            
        total_sales += m_sales_for_dash
        total_payment += m_payment_for_dash

        if m_sales_for_dash > 0:
            if p_dept == "内":   dash_sales_a += m_sales_for_dash
            elif p_dept == "設": dash_sales_b += m_sales_for_dash
            elif p_dept == "電": dash_sales_c += m_sales_for_dash
            elif p_dept == "P":  dash_sales_d += m_sales_for_dash
            else:                dash_sales_a += m_sales_for_dash
            
        if m_payment_for_dash > 0:
            dept_cost_a += cost_a
            dept_cost_b += cost_b
            dept_cost_c += cost_c
            dept_cost_d += cost_d
            dept_cost_req += cost_req

        p_profit = p_sales_total - p_cost_total
        p_total_hours = 0.0
        aliases = p_data.get("aliases", [])
        ignored_keys = p_data.get("ignored_andpad_keys", [])
        for dept in ["staff_setsubi", "staff_naisou", "staff_denki", "staff_pm"]:
            for staff in p_data.get(dept, []):
                p_total_hours += get_hours_from_andpad(staff, p_name, p_num, aliases, ignored_keys)

        if is_payment_month_match or m_sales_for_dash > 0:
            for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"]:
                for item in p_data.get(cat, []):
                    g_name = str(item.get("業者・工種名", "")).strip()
                    c_val = safe_num(item.get("協力業者支払"))
                    if g_name and g_name.lower() != "none": 
                        contractor_costs_by_name[g_name] = contractor_costs_by_name.get(g_name, 0.0) + c_val

            project_sales_rows.append({
                "物件番号": p_num, "顧客名": c_name, "物件名": p_name, "月度": p_month,
                "売上高 合計 (円)": p_sales_total, "協力業者支払 実績合計 (円)": p_cost_total, "売上純利益 (円)": p_profit,
                "総投入工数 (h)": p_total_hours
            })
            
            valid_projects_for_ai[p_name] = {
                "顧客名": c_name, "担当部署": p_dept, "売上高": p_sales_total, "原価実績": p_cost_total, "純利益": p_profit, "投入工数": p_total_hours, "状況やメモ": p_data.get("eval_memo", "")
            }

    gross_profit = total_sales - total_payment
    profit_margin = (gross_profit / total_sales) * 100 if total_sales > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric(label="売上金額 (入金日ベース)", value=f"¥{total_sales:,.0f}")
    with col2: st.metric(label="支払実績 (対象期間)", value=f"¥{total_payment:,.0f}")
    with col3: st.metric(label="純利益額 (対象期間)", value=f"¥{gross_profit:,.0f}", delta="現在粗利額", delta_color="normal")
    with col4: st.metric(label="粗利率 (対象期間)", value=f"{profit_margin:.1f}%")
    with col5: st.metric(label="実行予算総額 (参考)", value=f"¥{total_budget:,.0f}")

    st.markdown('<div class="section-divider" style="margin-top:20px; margin-bottom:20px;"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"### 🌐 全能マスターAI (Master JARVIS) <small style='font-size:13px; color:#777;'>[稼働中: {ai_engine_option}]</small>", unsafe_allow_html=True)
        st.info("システム内の全物件データ、各部署の売上・予算、担当者ごとの稼働状況をすべて網羅しています。会社全体の戦略や各プロジェクトのリスクを自由に質問してください。")
        
        master_chat_key = "master_jarvis_chat"
        if master_chat_key not in st.session_state:
            st.session_state[master_chat_key] = []

        history = st.session_state[master_chat_key]
        for i in range(0, len(history), 2):
            q_msg = history[i]
            a_msg = history[i+1] if (i+1) < len(history) else None
            
            title_text = q_msg['content'][:40] + ("..." if len(q_msg['content'])>40 else "")
            
            with st.expander(f"👤 Q: {title_text}", expanded=False):
                st.markdown(f"**あなた:**\n{q_msg['content']}")
                st.markdown("---")
                if a_msg:
                    st.markdown(f"**🤖 Master JARVIS:**\n{a_msg['content']}")

        master_query = st.chat_input("例：利益率が一番低い物件を分析して / 今月の売上と支払いのバランスはどう？ / 残業オーバーが危ないメンバーを抽出して", key="master_chat_input")
        
        if master_query:
            st.session_state[master_chat_key].append({"role": "user", "content": master_query})
            with st.chat_message("user"):
                st.write(master_query)

            with st.chat_message("assistant"):
                with st.spinner("Master JARVISが全社データへアクセス・分析中..."):
                    obsidian_text = ""
                    try:
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        temp_dir = current_dir
                        desktop_path = None
                        
                        while temp_dir and temp_dir != os.path.dirname(temp_dir):
                            if os.path.basename(temp_dir) in ["デスクトップ", "Desktop"]:
                                desktop_path = temp_dir
                                break
                            temp_dir = os.path.dirname(temp_dir)
                            
                        if not desktop_path:
                            fallback_path = os.path.expanduser(r"~\OneDrive - 三岳工業 株式会社\デスクトップ")
                            if os.path.exists(fallback_path):
                                desktop_path = fallback_path
                            else:
                                fallback_desktop = os.path.expanduser(r"~\Desktop")
                                if os.path.exists(fallback_desktop):
                                    desktop_path = fallback_desktop
                                    
                        VAULT_BASE_PATH = None
                        try:
                            if desktop_path and os.path.exists(desktop_path):
                                potential_vault = os.path.join(desktop_path, "MITKE議事録")
                                if os.path.exists(potential_vault):
                                    VAULT_BASE_PATH = potential_vault
                                else:
                                    for d in os.listdir(desktop_path):
                                        dp = os.path.join(desktop_path, d)
                                        if os.path.isdir(dp) and d == "MITKE議事録":
                                            VAULT_BASE_PATH = dp
                                            break
                        except Exception:
                            VAULT_BASE_PATH = None
                        
                        if VAULT_BASE_PATH:
                            keywords = re.findall(r'[一-龠ァ-ヶa-zA-Z]{2,}', master_query)
                            stop_words = ["情報", "議事録", "データ", "内容", "詳細", "確認", "お願い", "について", "あります", "ほしい", "ください", "教えて", "マスター", "全体", "会社", "ダッシュボード"]
                            valid_keywords = [k for k in keywords if k not in stop_words]
                            
                            if valid_keywords:
                                found_contents = []
                                for root, dirs, files in os.walk(VAULT_BASE_PATH):
                                    if '.obsidian' in root: continue
                                    for f in files:
                                        if f.endswith(".md"):
                                            file_path = os.path.join(root, f)
                                            content = ""
                                            try:
                                                with open(file_path, "r", encoding="utf-8") as file_obj: 
                                                    content = file_obj.read()
                                            except: pass
                                            
                                            if content and any(k in content or k in f for k in valid_keywords):
                                                clean_content = re.sub(r'\s+', ' ', content)[:1000]
                                                found_contents.append(f"■ファイル名: {f}\n{clean_content}")
                                                if len(found_contents) >= 5: break
                                    if len(found_contents) >= 5: break
                        
                                if found_contents:
                                    obsidian_text = "\n\n=== 🔗 PC内から自動検索した関連議事録（最優先事項） ===\n" + "\n\n".join(found_contents)
                    except Exception as e:
                        obsidian_text = ""
                        pass

                    all_staff_hours_list = []
                    valid_projects = [(k, v) for k, v in projects_db.items() if isinstance(v, dict) and k != "_SYSTEM_SETTINGS_" and v.get("project_year") == global_target_year and (global_target_month == "通期（全月合計）" or v.get("project_month") == global_target_month)]
                    for staff in all_staff_list:
                        s_total = sum(get_hours_from_andpad(staff, p_name, p_data.get("project_number", ""), p_data.get("aliases", []), p_data.get("ignored_andpad_keys", [])) for p_name, p_data in valid_projects)
                        if s_total > 0: all_staff_hours_list.append({"担当者": staff, "累計工数": s_total})
                    
                    master_context = f"""
                    【会社全体（{global_target_year} / {global_target_month}）の業績サマリー】
                    - 総売上金額: {total_sales} 円
                    - 総支払実績: {total_payment} 円
                    - 粗利益額: {gross_profit} 円
                    - 会社全体の粗利率: {profit_margin:.1f} %
                    
                    【部署別の売上サマリー】
                    - 内装(内): {dash_sales_a} 円
                    - 設備(設): {dash_sales_b} 円
                    - 電気(電): {dash_sales_c} 円
                    - 厨房(P): {dash_sales_d} 円
                    
                    【担当者の稼働状況（月間基準稼働時間は通常160hです）】
                    {json.dumps(all_staff_hours_list, ensure_ascii=False)}
                    
                    【全プロジェクトの詳細一覧（JSON）】
                    {json.dumps(valid_projects_for_ai, ensure_ascii=False)}
                    """

                    sys_instruct = "あなたはMITAKEの全プロジェクトと会社全体の業績を統括する全能のAIアシスタント（Master JARVIS）です。提供された全社データを完全に把握し、経営者・管理者の視点で的確な分析とアドバイスを行ってください。一切の制限なく、あらゆる質問に対してプロフェッショナルかつ論理的に答えてください。"
                    
                    user_p = f"{master_context}\n{obsidian_text}\n\n【ユーザーの質問】\n{master_query}"
                    res_text = call_jarvis_ai(sys_instruct, user_p, model_choice=ai_engine_option, gemini_api_key=GEMINI_API_KEY)
                    
                    st.write(res_text)
                    st.session_state[master_chat_key].append({"role": "assistant", "content": res_text})

    st.markdown('<div class="section-divider" style="margin-top:20px; margin-bottom:20px;"></div>', unsafe_allow_html=True)

    with st.expander("📈 全期ごとの売上・利益推移 (過去の期を含む)", expanded=False):
        df_term_graph = pd.DataFrame([{"期": year, "売上": term_summary[year]["売上"], "利益": term_summary[year]["利益"]} for year in YEAR_LIST]).set_index("期")
        st.line_chart(df_term_graph, height=200)

    with st.container(border=True):
        st.markdown(f"### 📋 契約日ベースの受注金額 集計 ({global_target_year})")
        st.info("※ 物件の「着手金入金予定月（または売上計上月）」を契約日とみなして集計した受注金額の月別推移です。")
        contract_row = {"項目": "契約受注金額"}
        for m in MONTH_LIST: contract_row[m] = f"¥ {contract_month_sales[m]:,.0f}"
        st.metric("契約ベース 受注総額", f"¥ {contract_total_sales:,.0f}")
        st.dataframe(pd.DataFrame([contract_row]), use_container_width=True, hide_index=True)

    st.markdown("---")
    with st.expander("📊 月次業績 ＆ 資金繰り予測表 (PL・CF統合) を表示", expanded=False):
        st.markdown("売上・利益の「損益（PL）」と、実際の現金推移である「資金繰り（CF）」を一つの表とグラフに統合しました。")
        initial_cash = st.number_input("現在の預金残高（目安・スタート金額）を設定してください", value=10000000, step=1000000, format="%d")
        
        unified_rows = []
        current_balance = initial_cash
        chart_data = []
        
        for m in MONTH_LIST:
            m_sales = monthly_data_dict[m]["売上"]
            m_cost = monthly_data_dict[m]["支払"]
            m_profit = m_sales - m_cost
            
            inflow = cf_inflow[m]
            outflow = cf_outflow[m]
            net_flow = inflow - outflow
            
            unified_rows.append({
                "月度": m,
                "【損益】売上高": m_sales,
                "【損益】粗利益": m_profit,
                "【資金】月初残高": current_balance,
                "【資金】入金予定": inflow,
                "【資金】支払予定": outflow,
                "【資金】月末残高": current_balance + net_flow
            })
            
            chart_data.append({"月度": m, "種類": "入金", "金額": inflow})
            chart_data.append({"月度": m, "種類": "支払", "金額": -outflow})
            chart_data.append({"月度": m, "種類": "月末残高", "金額": current_balance + net_flow})
            
            current_balance += net_flow
            
        df_unified = pd.DataFrame(unified_rows)
        df_unified_disp = df_unified.copy()
        for col in df_unified.columns[1:]:
            df_unified_disp[col] = df_unified[col].apply(lambda x: f"¥ {x:,.0f}")
            
        st.dataframe(df_unified_disp, use_container_width=True, hide_index=True)
        
        df_chart = pd.DataFrame(chart_data)
        base = alt.Chart(df_chart).encode(x=alt.X('月度:N', sort=MONTH_LIST))
        bar_in = base.transform_filter(alt.datum.種類 == '入金').mark_bar(color='#48BB78', opacity=0.8, size=20).encode(y=alt.Y('金額:Q', title='金額 (円)'), xOffset=alt.value(-15), tooltip=['月度', '種類', '金額'])
        bar_out = base.transform_filter(alt.datum.種類 == '支払').mark_bar(color='#E53E3E', opacity=0.8, size=20).encode(y=alt.Y('金額:Q'), xOffset=alt.value(15), tooltip=['月度', '種類', '金額'])
        line_bal = base.transform_filter(alt.datum.種類 == '月末残高').mark_line(color='#3182CE', point=True, strokeWidth=3).encode(y=alt.Y('金額:Q'), tooltip=['月度', '種類', '金額'])
        
        st.markdown("###### 月別 キャッシュフロー＆残高推移グラフ")
        st.altair_chart((bar_in + bar_out + line_bal).properties(height=280), use_container_width=True)

    st.markdown("---")
    st.markdown("### ⌕ 個別顧客・商社協力業者の実績抽出")
    
    with st.container(border=True):
        st.markdown("#### 👤 現在のデータからの顧客別 自動集計")
        st.info("※ 対象の期は、左サイドバーの「共通フィルター」と連動しています。")
        
        all_clients = list(set([v.get("client_name", "未設定") for k, v in projects_db.items() if isinstance(v, dict) and k != "_SYSTEM_SETTINGS_"]))
        all_clients = sorted([c for c in all_clients if c != "未設定" and "合計" not in c and "修理" not in c and "スキップ" not in c])
        
        sel_client = st.selectbox("分析する顧客名を選択", ["(選択してください)"] + all_clients, key="client_anal_sel")
            
        if sel_client != "(選択してください)":
            client_sales = 0.0
            client_cost = 0.0
            month_sales = {m: 0.0 for m in MONTH_LIST}
            month_cost = {m: 0.0 for m in MONTH_LIST}
            target_projects = []
            client_proj_rows = []
            
            for p_name, p_data in projects_db.items():
                if not isinstance(p_data, dict) or p_name == "_SYSTEM_SETTINGS_": continue
                if p_data.get("client_name") == sel_client and p_data.get("project_year") == global_target_year:
                    target_projects.append(p_name)
                    p_month = p_data.get("project_month", "9月")
                    
                    val_a = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_a", []))
                    val_b = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_b", []))
                    val_c = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_c", []))
                    val_d = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_d", []))
                    order_amt = safe_num(p_data.get("受注金額", 0))
                    p_sales = order_amt if order_amt > 0 else (val_a + val_b + val_c + val_d)
                    
                    p_cost = 0.0
                    for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"]:
                        for item in p_data.get(cat, []): p_cost += safe_num(item.get("協力業者支払"))
                            
                    client_sales += p_sales
                    client_cost += p_cost
                    if p_month in month_sales:
                        month_sales[p_month] += p_sales
                        month_cost[p_month] += p_cost
                    
                    client_proj_rows.append({"物件名": p_name, "月度": p_month, "売上高(円)": p_sales, "原価(円)": p_cost, "粗利(円)": p_sales - p_cost})
                        
            client_profit = client_sales - client_cost
            client_margin = (client_profit / client_sales) if client_sales > 0 else 0.0
            
            st.markdown(f"##### {sel_client} - {global_target_year} 実績")
            st.markdown(f"<span style='font-size: 13px; font-weight: 600; color: #4A5568;'>対象物件数: {len(target_projects)}件 ({', '.join(target_projects)})</span>", unsafe_allow_html=True)
            
            cols = st.columns(3)
            cols[0].metric("純売上額", f"{client_sales:,.0f} 円")
            cols[1].metric("粗利額", f"{client_profit:,.0f} 円")
            cols[2].metric("粗利率", f"{client_margin*100:.1f} %")
            
            st.markdown("###### 月別推移（9月〜8月）")
            row_sales = {"項目": "売上"}
            row_profit = {"項目": "粗利"}
            row_margin = {"項目": "粗利率"}
            for m in MONTH_LIST:
                row_sales[m] = f"{month_sales[m]:,.0f}"
                m_profit = month_sales[m] - month_cost[m]
                row_profit[m] = f"{m_profit:,.0f}"
                m_margin = (m_profit / month_sales[m]) if month_sales[m] > 0 else 0.0
                row_margin[m] = f"{m_margin*100:.1f}%"
            st.dataframe(pd.DataFrame([row_sales, row_profit, row_margin]), use_container_width=True, hide_index=True)
            
            st.markdown("###### 物件別 明細")
            if client_proj_rows: st.dataframe(pd.DataFrame(client_proj_rows), use_container_width=True, hide_index=True)

    with st.container(border=True):
        st.markdown("#### 🏢 業者支払内訳の確認")
        all_contractor_names = sorted(list(set([str(x.get("業者・工種名", "")).strip() for k, v in projects_db.items() if isinstance(v, dict) and k != "_SYSTEM_SETTINGS_" for c in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"] for x in v.get(c, []) if str(x.get("業者・工種名", "")).strip() != ""])))
        selected_dash_contractor = st.selectbox("確認したい業者・工種名を選択してください", ["(未選択)"] + all_contractor_names, key="dash_contractor_sb_v_new")
        
        if selected_dash_contractor != "(未選択)":
            con_rows = []
            contractor_month_payment = {m: 0.0 for m in MONTH_LIST}
            for p_name, p_data in projects_db.items():
                if p_name == "_SYSTEM_SETTINGS_": continue
                if p_data.get("project_year") == global_target_year:
                    p_month = p_data.get("project_month", "9月")
                    for cat in ["detail_a", "detail_b", "detail_c", "detail_d", "detail_request"]:
                        for item in p_data.get(cat, []):
                            if str(item.get("業者・工種名", "")).strip() == selected_dash_contractor:
                                p_val = safe_num(item.get("協力業者支払", 0))
                                b_val = safe_num(item.get("実行予算", 0))
                                out_m = str(item.get("支払予定月", ""))
                                if out_m not in MONTH_LIST: out_m = p_month
                                con_rows.append({"物件名": p_name, "支払予定月": out_m, "実行予算(円)": b_val, "支払金額(円)": p_val})
                                if out_m in contractor_month_payment: contractor_month_payment[out_m] += p_val

            if con_rows:
                df_con_res = pd.DataFrame(con_rows)
                st.metric(f"【{global_target_year}】総支払額", f"¥{df_con_res['支払金額(円)'].sum():,.0f}")
                st.markdown("###### 月別推移（9月〜8月）")
                row_payment = {"項目": "支払金額"}
                for m in MONTH_LIST: row_payment[m] = f"{contractor_month_payment[m]:,.0f}"
                st.dataframe(pd.DataFrame([row_payment]), use_container_width=True, hide_index=True)
                st.markdown("###### 物件別 明細")
                st.dataframe(df_con_res, use_container_width=True, hide_index=True)
            else: st.info("今期はこの業者さんへの支払データが登録されていません。")

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    st.markdown("### 🏢 部署・担当者別 分析")

    st.markdown("#### ▪ カテゴリ別 売上構成比")
    df_pie = pd.DataFrame({"カテゴリ": ["内装", "設備", "電気", "厨房"], "売上": [dash_sales_a, dash_sales_b, dash_sales_c, dash_sales_d]})
    if df_pie["売上"].sum() == 0: 
        st.info("データがありません")
    else:
        pie_chart = alt.Chart(df_pie).mark_arc(innerRadius=30).encode(theta=alt.Theta(field="売上", type="quantitative"), color=alt.Color(field="カテゴリ", type="nominal"), tooltip=["カテゴリ", "売上"]).properties(height=250)
        st.altair_chart(pie_chart, use_container_width=True)
        
    st.markdown("#### ▪ 部署別 実績")
    sort_option = st.radio("表示順の変更:", ["デフォルト (固定)", "売上高が高い順", "利益が高い順"], horizontal=True, key="sort_opt_dept")
    df_dept_final = pd.DataFrame({
        "部署": ["第2管理部（内装）―内", "第1管理部（設備）―設", "第3管理部（電気）―電", "PM室（厨房等）―P", "未振分（AI読取）"],
        "売上高（円）": [dash_sales_a, dash_sales_b, dash_sales_c, dash_sales_d, 0],
        "商社協力業社支払実績（円）": [dept_cost_a, dept_cost_b, dept_cost_c, dept_cost_d, dept_cost_req],
    })
    df_dept_final["売上純利益（円）"] = df_dept_final["売上高（円）"] - df_dept_final["商社協力業社支払実績（円）"]
    if sort_option == "売上高が高い順": df_dept_final = df_dept_final.sort_values(by="売上高（円）", ascending=False)
    elif sort_option == "利益が高い順": df_dept_final = df_dept_final.sort_values(by="売上純利益（円）", ascending=False)
    st.dataframe(df_dept_final, use_container_width=True, hide_index=True)

    st.markdown("#### ▪ 部署別 契約日ベース受注金額（月別）")
    dept_contract_rows = []
    for d_key, d_name in [("内", "第2管理部（内装）―内"), ("設", "第1管理部（設備）―設"), ("電", "第3管理部（電気）―電"), ("P", "PM室（厨房等）―P")]:
        row = {"部署": d_name}
        d_total = 0.0
        for m in MONTH_LIST:
            val = dept_contract_monthly[d_key][m]
            row[m] = f"¥ {val:,.0f}"
            d_total += val
        row["合計"] = f"¥ {d_total:,.0f}"
        dept_contract_rows.append(row)
    st.dataframe(pd.DataFrame(dept_contract_rows), use_container_width=True, hide_index=True)

    st.markdown("#### ▪ 担当者別 就業時間・売上実績")
    
    col_staff1, col_staff2 = st.columns([1, 1])
    with col_staff1:
        selected_staff = st.selectbox("情報を確認したい担当者を選択してください", all_staff_list, key="staff_chk_sel")
    with col_staff2:
        target_hours_month = st.number_input("月間基準稼働時間 (h)", value=200, step=10, key="target_h_global", help="これを超えた担当者は赤く警告表示されます")
    
    staff_projects_rows = []
    total_staff_sales = total_staff_hours = 0
    for p_name, p_data in projects_db.items():
        if not isinstance(p_data, dict) or p_name == "_SYSTEM_SETTINGS_": continue
        if p_data.get("project_year", "57期") != global_target_year: continue
        p_month = p_data.get("project_month", "9月")
        if global_target_month != "通期（全月合計）" and p_month != global_target_month: continue
        
        is_member = any(selected_staff in p_data.get(dept, []) for dept in ["staff_setsubi", "staff_naisou", "staff_denki", "staff_pm"])
        staff_hours = get_hours_from_andpad(selected_staff, p_name, p_data.get("project_number", ""), p_data.get("aliases", []), p_data.get("ignored_andpad_keys", []))
        
        safe_sel, safe_rep = selected_staff.replace(" ", ""), str(p_data.get("sales_rep", "")).replace(" ", "")
        is_sales_rep = bool(safe_rep and safe_sel and (safe_sel in safe_rep or safe_rep in safe_sel or (len(safe_sel)>=2 and safe_sel[:2] in safe_rep)))
                
        if is_member or staff_hours > 0 or is_sales_rep:
            order_amount = safe_num(p_data.get("受注金額", 0))
            p_sales = order_amount if order_amount > 0 else sum(safe_num(x.get("完了金額")) for cat in ["detail_a", "detail_b", "detail_c", "detail_d"] for x in p_data.get(cat, []))
            staff_allocated_sales = p_sales if is_sales_rep else 0.0
            total_staff_sales += staff_allocated_sales
            total_staff_hours += staff_hours
            staff_projects_rows.append({"物件番号": p_data.get("project_number", ""), "物件名": p_name, "顧客名": p_data.get("client_name", "未設定"), "営業担当": "担当" if is_sales_rep else "-", "所属部署での登録枠": "✓ あり" if is_member else "✕ なし", "累計就業時間": f"{staff_hours:.1f} h", "担当売上高 (円)": staff_allocated_sales})
    
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("関与した物件数", f"{len(staff_projects_rows)} 件")
    if total_staff_hours > target_hours_month:
        sc2.markdown(f"<div style='margin-bottom: -15px;'><span style='font-size: 13px; color: #787774; font-weight: 500;'>総累計就業時間</span><br><span class='blink-text' style='font-size: 26px;'>{total_staff_hours:.1f} h</span><br><span style='color: #e53e3e; font-size: 13px; font-weight: bold;'>⚠ {total_staff_hours - target_hours_month:.1f}h オーバー</span></div>", unsafe_allow_html=True)
    else: sc2.metric("総累計就業時間", f"{total_staff_hours:.1f} h")
    sc3.metric("営業担当としての総売上", f"¥ {total_staff_sales:,.0f}")
    st.dataframe(pd.DataFrame(staff_projects_rows), use_container_width=True, hide_index=True, height=270, column_config={"担当売上高 (円)": st.column_config.NumberColumn("担当売上高 (円)", format="¥ %d")})

    with st.expander("👥 全メンバーの稼働状況一覧を表示 (残業・オーバーチェック)", expanded=True):
        col_title, col_btn = st.columns([4, 1])
        with col_btn:
            if st.button("🗑️ 稼働時間データをすべて消去", key="clear_andpad_data", help="取り込んだ稼働時間(ANDPAD)データをリセットします"):
                if "parsed_andpad_data" in st.session_state:
                    del st.session_state.parsed_andpad_data
                if os.path.exists(ANDPAD_ACC_DIR):
                    for filename in os.listdir(ANDPAD_ACC_DIR):
                        f_path = os.path.join(ANDPAD_ACC_DIR, filename)
                        try:
                            if os.path.isfile(f_path):
                                os.remove(f_path)
                        except Exception:
                            pass
                st.session_state.andpad_hours_cache = {}
                st.session_state.andpad_breakdown_cache = {}
                st.success("データを完全に消去しました。画面が更新されます。")
                st.rerun()

        all_staff_hours = []
        for staff in all_staff_list:
            s_total = get_staff_total_hours(staff, global_target_month)
            if s_total > 0: all_staff_hours.append({"name": staff, "hours": s_total})
            
        if not all_staff_hours:
            st.info("現在、集計された稼働時間データはありません。")
        else:
            all_staff_hours = sorted(all_staff_hours, key=lambda x: x["hours"], reverse=True)
            
            cols = st.columns(4)
            for i, sh in enumerate(all_staff_hours):
                col = cols[i % 4]
                h, name = sh["hours"], sh["name"]
                
                is_over = h > target_hours_month
                icon = "🔴" if is_over else "🟢"
                title = f"{icon} {name} : {h:.1f} h"
                
                with col:
                    with st.expander(title, expanded=False):
                        if is_over:
                            st.markdown(f"<span style='color:#e53e3e; font-weight:bold;'>⚠ +{h-target_hours_month:.1f}h オーバー</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<span style='color:#48BB78; font-weight:bold;'>✓ 正常稼働</span>", unsafe_allow_html=True)
                            
                        records = get_staff_daily_breakdown(name, global_target_month)
                        if records:
                            df_recs = pd.DataFrame(records)
                            st.dataframe(
                                df_recs, 
                                hide_index=True, 
                                use_container_width=True,
                                height=200,
                                column_config={
                                    "日付": st.column_config.TextColumn("日付", width="small"),
                                    "打刻名": st.column_config.TextColumn("打刻名", width="medium"),
                                    "工数(h)": st.column_config.NumberColumn("時間", format="%.1f")
                                }
                            )
                        else:
                            st.write("詳細データなし")

    st.markdown("---")
    with st.expander("▪ 物件別 総投入工数（就業時間）一覧を表示", expanded=False):
        df_proj_hours = pd.DataFrame(project_sales_rows)
        if not df_proj_hours.empty and "総投入工数 (h)" in df_proj_hours.columns:
            df_hours_filtered = df_proj_hours[df_proj_hours["総投入工数 (h)"] > 0].copy()
            if not df_hours_filtered.empty:
                df_hours_filtered = df_hours_filtered.sort_values(by="総投入工数 (h)", ascending=False)
                disp_df = df_hours_filtered[["顧客名", "物件名", "総投入工数 (h)"]].reset_index(drop=True)
                st.dataframe(disp_df, use_container_width=True, hide_index=True, column_config={"総投入工数 (h)": st.column_config.NumberColumn("総投入工数 (h)", format="%.1f h")})
            else: 
                st.info("対象期間において、計上されている就業時間データはありません。")
        else:
            st.info("対象期間において、計上されている就業時間データはありません。")