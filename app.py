import streamlit as st
import pandas as pd
import base64
import os
import json
import re
 
# 画面をワイドに使う設定（※必ずst.writeなどより上に書く必要があります）
st.set_page_config(layout="wide", page_title="MITAKE 社内管理アプリ")
 
# 文字サイズを小さくし、上下の余白を詰めるデザイン設定
st.markdown("""
<style>
    /* 全体の文字サイズを小さくする */
    html, body, [class*="css"]  {
        font-size: 14px !important;
    }
    /* 画面上下の余白を極力なくして1画面に収める */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
</style>
""", unsafe_allow_html=True)
 
# ==========================================
# 🔑 APIキーの設定
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    GEMINI_API_KEY = "YOUR_KEY_HERE"

# AIライブラリの読み込み
try:
    import google.generativeai as genai
    from PIL import Image
    if GEMINI_API_KEY != "YOUR_KEY_HERE":
        genai.configure(api_key=GEMINI_API_KEY)
except ImportError:
    st.error("⚠️ AI機能を使うためのライブラリが不足しています。")



# ==========================================
# ⚡ 爆速化のための記憶（キャッシュ）設定
# ==========================================
@st.cache_data(ttl=600) # スプレッドシートのデータを10分間記憶する
def load_csv_data(url):
    try:
        return pd.read_csv(url)
    except:
        return pd.DataFrame()

@st.cache_data # エクセルデータを記憶する
def load_excel_data(path):
    try:
        return pd.read_excel(path, sheet_name=0, header=None)
    except:
        return pd.DataFrame()

st.title("MITAKE 社内管理アプリ")
 
# ==========================================
# 💡 全社員マスター
# ==========================================
all_staff_list = [
    "野口 裕二", "中澤 大輝", "石川 翔一", "吉田 香", "小田 猛",
    "福島 翔", "阿部 充希", "佐藤 悠介", "島田 悠吾", "大町 竜久",
    "坂本 俊秀", "今 詩織", "宮本 裕一", "佐々木 一", "菊岡 宇弘",
    "目黒 透", "其田 正広", "臼井 和広", "中川 聖太", "遠藤 浩史",
    "太田 尚希", "備前 雄太郎", "下村 凛", "黒川 孝之", "尾家 明夫",
    "木村 明美", "渡辺 隆行"
]
 
# ==========================================
# 💡 ジャンル・年度(期数)・月度マスター
# ==========================================
CATEGORY_LIST = ["未設定", "カフェ", "アパレル", "レストラン", "住宅", "茶室", "飲食(その他)", "その他"]
YEAR_LIST = ["53期", "54期", "55期", "56期", "57期", "58期", "59期", "60期", "61期"]
MONTH_LIST = ["9月", "10月", "11月", "12月", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月"]
 
# ==========================================
# 💡 工種の完全フルセット
# ==========================================
FULL_DETAIL_A = [{"工種名": n, "業者管理番号": "", "業者・工種名": "", "実行予算": 0, "協力業者支払": 0, "完了金額": 0} for n in ["仮設", "防水", "左官", "軽鉄・ボード工事", "タイル工事", "ガラス工事", "金属工事", "金属建具工事", "木製建具工事", "家具工事", "木工事", "塗装工事", "内装工事", "看板工事", "雑工事"]]
FULL_DETAIL_B = [{"工種名": n, "業者管理番号": "", "業者・工種名": "", "実行予算": 0, "協力業者支払": 0, "完了金額": 0} for n in ["給排水", "衛生", "ガス", "スプリンクラー", "給排気", "空調設備", "自動消火設備", "防災"]]
FULL_DETAIL_C = [{"工種名": n, "業者管理番号": "", "業者・工種名": "", "実行予算": 0, "協力業者支払": 0, "完了金額": 0} for n in ["電気設備", "路電工事"]]
FULL_DETAIL_D = [{"工種名": n, "業者管理番号": "", "業者・工種名": "", "実行予算": 0, "協力業者支払": 0, "完了金額": 0} for n in ["厨房機器本体", "搬入設置費", "配管接続工事"]]
 
def merge_details(full_template, current_data):
    if not current_data:
        return [item.copy() for item in full_template]
    cur_dict = {item["工種名"]: item for item in current_data}
    merged = []
    for f_item in full_template:
        if f_item["工種名"] in cur_dict:
            item = cur_dict[f_item["工種名"]]
            if "業者管理番号" not in item: item["業者管理番号"] = ""
            if "業者・工種名" not in item: item["業者・工種名"] = item.get("業者名", "")
            if "協力業者支払" not in item: item["協力業者支払"] = 0
            if "完了金額" not in item: item["完了金額"] = 0
            if "実行予算" not in item: item["実行予算"] = 0
            merged.append(item)
        else:
            merged.append(f_item.copy())
    return merged
 
# ==========================================
# 💡 50行業者マスタ管理
# ==========================================
file_contractor = "data_contractor.csv"
if os.path.exists(file_contractor):
    try:
        df_contractor_master = pd.read_csv(file_contractor)
        if "業者管理番号" not in df_contractor_master.columns or len(df_contractor_master) < 50:
            raise Exception("Old Format")
        df_contractor_master["区分"] = df_contractor_master["区分"].replace({"A": "内", "B": "設", "C": "電", "D": "P"})
    except:
        df_contractor_master = pd.DataFrame({"区分": [""] * 50, "業者管理番号": [f"業{i:03d}" for i in range(1, 51)], "業者・工種名": [""] * 50})
        df_contractor_master.to_csv(file_contractor, index=False)
else:
    df_contractor_master = pd.DataFrame({"区分": [""] * 50, "業者管理番号": [f"業{i:03d}" for i in range(1, 51)], "業者・工種名": [""] * 50})
    df_contractor_master.to_csv(file_contractor, index=False)
 
# ==========================================
# 💡 物件データ管理
# ==========================================
PROJECTS_FILE = "projects_data.json"
DEFAULT_PROJECT_DATA = {
    "client_id": "", "client_name": "未設定", "project_number": "", "project_year": "57期",  
    "project_month": "9月", "category": "未設定", "status": "進行中",        
    "form_url": "", "sheet_url": "", "eval_memo": "", "budget_memo": "", "materials_memo": "",
    "calc_image": "",
    "detail_a": [item.copy() for item in FULL_DETAIL_A], "detail_b": [item.copy() for item in FULL_DETAIL_B],
    "detail_c": [item.copy() for item in FULL_DETAIL_C], "detail_d": [item.copy() for item in FULL_DETAIL_D],
    "staff_setsubi": ["野口 裕二", "中澤 大輝", "石川 翔一", "宮本 裕一", "佐々木 一", "菊岡 宇弘"],
    "staff_naisou": ["吉田 香", "小田 猛", "福島 翔", "目黒 透", "其田 正広", "臼井 和広"],
    "staff_denki": ["阿部 充希", "佐藤 悠介", "島田 悠吾", "中川 聖太", "遠藤 浩史", "太田 尚希"],
    "staff_pm": ["大町 竜久", "坂本 俊秀", "今 詩織", "備前 雄太郎", "下村 凛", "黒川 孝之", "尾家 明夫", "木村 明美", "渡辺 隆行"]
}
 
def load_projects():
    year_to_term = {"2022年": "53期", "2023年": "54期", "2024年": "55期", "2025年": "56期", "2026年": "57期", "2027年": "58期", "2028年": "59期", "2029年": "60期", "2030年": "61期"}
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict): raise ValueError("JSON is corrupted")
               
                valid_data = {}
                for p_name, p_data in data.items():
                    if not isinstance(p_data, dict): continue
                    if "client_id" not in p_data: p_data["client_id"] = ""
                    if "project_number" not in p_data: p_data["project_number"] = ""
                    if "client_name" not in p_data: p_data["client_name"] = "未設定"
                    if "project_month" not in p_data: p_data["project_month"] = "9月"
                    if "category" not in p_data: p_data["category"] = "未設定"
                    if "status" not in p_data: p_data["status"] = "進行中"
                    if "materials_memo" not in p_data: p_data["materials_memo"] = ""
                    if "form_url" not in p_data: p_data["form_url"] = ""
                    if "sheet_url" not in p_data: p_data["sheet_url"] = ""
                    if "calc_image" not in p_data: p_data["calc_image"] = ""
                    if "project_year" not in p_data: p_data["project_year"] = "57期"
                    elif p_data["project_year"] in year_to_term: p_data["project_year"] = year_to_term[p_data["project_year"]]
                    valid_data[p_name] = p_data
                return valid_data
        except Exception:
            pass
 
    initial_data = {"渋谷カフェA": DEFAULT_PROJECT_DATA.copy()}
    initial_data["渋谷カフェA"]["client_id"] = "顧001"
    initial_data["渋谷カフェA"]["client_name"] = "株式会社OMC"
    initial_data["渋谷カフェA"]["project_number"] = "物001"
    initial_data["渋谷カフェA"]["project_year"] = "57期"
    initial_data["渋谷カフェA"]["project_month"] = "9月"
    initial_data["渋谷カフェA"]["category"] = "カフェ"
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(initial_data, f, ensure_ascii=False, indent=4)
    return initial_data
 
def save_projects(data):
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
 
projects_db = load_projects()
 
# ==========================================
# 💡 自己修復お掃除機能（バグの原因を一掃）
# ==========================================
keys_to_delete = []
for k, v in projects_db.items():
    if not isinstance(v, dict): continue
    c_name = str(v.get("client_name", ""))
    p_month = str(v.get("project_month", ""))
    if "合計" in c_name or p_month == "通期合計":
        keys_to_delete.append(k)
 
if keys_to_delete:
    for k in keys_to_delete:
        del projects_db[k]
    save_projects(projects_db)
 
def safe_num(v):
    try:
        if v is not None and str(v).strip() != "": return float(v)
        else: return 0.0
    except: return 0.0
 
def get_hours_for_staff(df, staff_name, current_project):
    if df is None or df.empty: return "0.0 h"
    df.columns = [c.strip() for c in df.columns]
    target_col = "質問1：担当者名"
    if target_col not in df.columns:
        for col in df.columns:
            if "担当者" in col:
                target_col = col
                break
    if target_col not in df.columns or "打刻区分" not in df.columns or "物件名" not in df.columns: return "0.0 h"
    df_filtered = df[(df[target_col] == staff_name) & (df["物件名"] == current_project)]
    df_filtered = df_filtered.sort_values(by="Timestamp")
    total = 0.0
    st_time = None
    for _, row in df_filtered.iterrows():
        try:
            c_time = pd.to_datetime(row["Timestamp"])
            status = str(row["打刻区分"]).strip()
            if status == "出勤": st_time = c_time
            elif status == "退勤" and st_time is not None:
                total += (c_time - st_time).total_seconds() / 3600.0
                st_time = None
        except: pass
    return f"{total:.1f} h"
 
# ==========================================
# 💡 タブ作成
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📊 会社全体・部署別", "🏗️ 物件別予算管理", "📸 AI 書類自動処理", "📈 顧客別 実績・分析"])
 
# --- タブ1 ---
with tab1:
    # === 📊 全期ごとの売上・利益推移グラフ ===
    st.subheader("📈 全期ごとの売上・利益推移")
    term_summary = {year: {"売上": 0.0, "利益": 0.0} for year in YEAR_LIST}
    for p_name, p_data in projects_db.items():
        if not isinstance(p_data, dict): continue
        p_year = p_data.get("project_year", "57期")
        if p_year in term_summary:
            p_sales = sum(safe_num(x.get("完了金額")) for c in ["detail_a", "detail_b", "detail_c", "detail_d"] for x in p_data.get(c, []))
            p_cost = sum(safe_num(x.get("協力業者支払")) for c in ["detail_a", "detail_b", "detail_c", "detail_d"] for x in p_data.get(c, []))
            term_summary[p_year]["売上"] += p_sales
            term_summary[p_year]["利益"] += (p_sales - p_cost)
 
    df_term_graph = pd.DataFrame([
        {"期": year, "売上": term_summary[year]["売上"], "利益": term_summary[year]["利益"]}
        for year in YEAR_LIST
    ]).set_index("期")
    st.bar_chart(df_term_graph)
    st.markdown("---")
 
    summary_placeholder = st.container()
    st.markdown("---")
   
    target_year = st.selectbox("📂 集計する期を選択（タブ2の登録データと連動）", YEAR_LIST, index=YEAR_LIST.index("57期"))
   
    sales_a = sales_b = sales_c = sales_d = 0
    contractor_costs = {f"業{i:03d}": 0.0 for i in range(1, 51)}
    project_sales_rows = []
   
    monthly_data_dict = {m: {"売上": 0.0, "支払": 0.0} for m in MONTH_LIST}
 
    for p_name, p_data in projects_db.items():
        if not isinstance(p_data, dict): continue
        if p_data.get("project_year", "57期") != target_year: continue
           
        c_id = p_data.get("client_id", "")
        c_name = p_data.get("client_name", "未設定")
        p_num = p_data.get("project_number", "")
        p_month = p_data.get("project_month", "9月")
        s_url = p_data.get("sheet_url", "")
       
        p_total_hours = 0.0
        if s_url:
            try:
                if "/d/" in s_url:
                    csv_url = s_url.split("/edit")[0] + "/export?format=csv"
                    if "gid=" in s_url:
                        gid = s_url.split("gid=")[1].split("&")[0]
                        csv_url += f"&gid={gid}"
                    df_att = load_csv_data(csv_url) # ⚡ ここをキャッシュ化！
                    for dept in ["staff_setsubi", "staff_naisou", "staff_denki", "staff_pm"]:
                        for staff in p_data.get(dept, []):
                            h_str = get_hours_for_staff(df_att, staff, p_name)
                            p_total_hours += float(h_str.replace(" h", ""))
            except:
                pass
       
        val_a = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_a", []))
        val_b = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_b", []))
        val_c = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_c", []))
        val_d = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_d", []))
 
        sales_a += val_a; sales_b += val_b; sales_c += val_c; sales_d += val_d
        p_sales_total = val_a + val_b + val_c + val_d
        p_cost_total = 0.0
       
        for cat in ["detail_a", "detail_b", "detail_c", "detail_d"]:
            for item in p_data.get(cat, []):
                g_num = item.get("業者管理番号", "")
                c_val = safe_num(item.get("協力業者支払"))
                p_cost_total += c_val
                if g_num in contractor_costs: contractor_costs[g_num] += c_val
 
        p_profit = p_sales_total - p_cost_total
       
        if p_month in monthly_data_dict:
            monthly_data_dict[p_month]["売上"] += p_sales_total
            monthly_data_dict[p_month]["支払"] += p_cost_total
       
        project_sales_rows.append({
            "物件番号": p_num, "顧客管理番号": c_id, "顧客名": c_name, "物件名": p_name,
            "売上高 合計 (円)": p_sales_total, "協力業者支払 合計 (円)": p_cost_total, "売上純利益 (円)": p_profit,
            "総投入工数 (h)": p_total_hours
        })
 
    monthly_rows = []
    for m_str in MONTH_LIST:
        m_sales = monthly_data_dict[m_str]["売上"]
        m_cost = monthly_data_dict[m_str]["支払"]
        m_profit = m_sales - m_cost
        monthly_rows.append({"月度": m_str, "顧客売上高 (円)": m_sales, "商社・協力業者支払 (円)": m_cost, "売上純利益 (円)": m_profit})
   
    df_monthly_calc = pd.DataFrame(monthly_rows)
 
    sales_grid_rows = []
    for i in range(300):
        if i < len(project_sales_rows): sales_grid_rows.append(project_sales_rows[i])
        else: sales_grid_rows.append({"物件番号": "", "顧客管理番号": "", "顧客名": "", "物件名": "", "売上高 合計 (円)": 0.0, "協力業者支払 合計 (円)": 0.0, "売上純利益 (円)": 0.0, "総投入工数 (h)": 0.0})
    df_project_sales = pd.DataFrame(sales_grid_rows)
 
    df_contractor_display = df_contractor_master.copy()
    df_contractor_display["支払金額 (円)"] = df_contractor_display["業者管理番号"].map(contractor_costs)
 
    cost_a = cost_b = cost_c = cost_d = 0
    for _, row in df_contractor_display.iterrows():
        c_amt = safe_num(row["支払金額 (円)"])
        if row["区分"] == "内": cost_a += c_amt
        elif row["区分"] == "設": cost_b += c_amt
        elif row["区分"] == "電": cost_c += c_amt
        elif row["区分"] == "P": cost_d += c_amt
 
    st.subheader(f"📅 【{target_year}】 顧客、商社、協力業者支払 月次集計表 (6行スクロール表示)")
    st.dataframe(df_monthly_calc, use_container_width=True, hide_index=True, height=250)
 
    st.markdown("---")
    st.subheader(f"👥 【{target_year}】 部署別実績")
    sort_option = st.radio("表示順の変更:", ["デフォルト (固定)", "売上高が高い順", "利益が高い順"], horizontal=True)
 
    df_dept_final = pd.DataFrame({
        "部署": ["第2管理部（内装）―内", "第1管理部（設備）―設", "第3管理部（電気）―電", "PM室（厨房等）―P"],
        "売上高（円）": [sales_a, sales_b, sales_c, sales_d],
        "商社協力業社支払（円）": [cost_a, cost_b, cost_c, cost_d],
    })
    df_dept_final["売上純利益（円）"] = df_dept_final["売上高（円）"] - df_dept_final["商社協力業社支払（円）"]
 
    if sort_option == "売上高が高い順": df_dept_final = df_dept_final.sort_values(by="売上高（円）", ascending=False)
    elif sort_option == "利益が高い順": df_dept_final = df_dept_final.sort_values(by="売上純利益（円）", ascending=False)
    st.dataframe(df_dept_final, use_container_width=True, hide_index=True)
   
    st.markdown("---")
    st.subheader(f"📊 【{target_year}】 物件（顧客）別 売上・利益集計表")
    st.dataframe(df_project_sales, use_container_width=True, hide_index=True, height=400)
 
    st.markdown("---")
    st.subheader(f"📅 【{target_year}】 商社、協力業社支払集計表")
   
    with st.expander("➕ 新しい業者を登録する（※登録後は修正できません）"):
        empty_rows = df_contractor_master[df_contractor_master["業者・工種名"] == ""]
        if not empty_rows.empty:
            next_idx = empty_rows.index[0]
            next_id = df_contractor_master.loc[next_idx, "業者管理番号"]
            st.write(f"**新規登録枠:** {next_id}")
            new_kbn = st.selectbox("区分", ["内", "設", "電", "P"])
            new_name = st.text_input("業者・工種名")
            if st.button("この内容で完全固定登録する"):
                if new_name.strip() != "":
                    df_contractor_master.loc[next_idx, "区分"] = new_kbn
                    df_contractor_master.loc[next_idx, "業者・工種名"] = new_name.strip()
                    df_contractor_master.to_csv(file_contractor, index=False)
                    st.success(f"{next_id} として登録しました！")
                    st.rerun()
                else: st.error("業者・工種名を入力してください。")
        else: st.info("登録枠（50件）がすべて埋まっています。")
 
    st.dataframe(
        df_contractor_display, use_container_width=True, hide_index=True, height=400,
        column_config={
            "区分": st.column_config.TextColumn("区分"), "業者管理番号": st.column_config.TextColumn("業者管理番号"),
            "業者・工種名": st.column_config.TextColumn("業者・工種名"), "支払金額 (円)": st.column_config.NumberColumn("支払金額 (円)")
        }
    )
 
    st.markdown("---")
    st.subheader(f"👤 【{target_year}】 担当者別 携わっている物件・就業時間一覧")
    selected_staff = st.selectbox("👨‍💼 情報を確認したい担当者を選択してください", all_staff_list)
   
    staff_projects_rows = []
    for p_name, p_data in projects_db.items():
        if not isinstance(p_data, dict): continue
        if p_data.get("project_year", "57期") != target_year: continue
       
        is_member = False
        for dept in ["staff_setsubi", "staff_naisou", "staff_denki", "staff_pm"]:
            if selected_staff in p_data.get(dept, []):
                is_member = True
                break
               
        s_url = p_data.get("sheet_url", "")
        staff_hours = 0.0
       
        if s_url:
            try:
                if "/d/" in s_url:
                    csv_url = s_url.split("/edit")[0] + "/export?format=csv"
                    if "gid=" in s_url:
                        gid = s_url.split("gid=")[1].split("&")[0]
                        csv_url += f"&gid={gid}"
                    df_att = load_csv_data(csv_url) # ⚡ ここをキャッシュ化！
                    h_str = get_hours_for_staff(df_att, selected_staff, p_name)
                    staff_hours = float(h_str.replace(" h", ""))
            except:
                pass
               
        if is_member or staff_hours > 0:
            staff_projects_rows.append({
                "物件番号": p_data.get("project_number", ""),
                "物件名": p_name,
                "顧客名": p_data.get("client_name", "未設定"),
                "所属部署での登録枠": "✅ メンバー登録あり" if is_member else "❌ 登録なし（打刻実績のみ）",
                "その物件での累計就業時間": f"{staff_hours:.1f} h"
            })
           
    staff_display_rows = []
    for i in range(300):
        if i < len(staff_projects_rows):
            staff_display_rows.append(staff_projects_rows[i])
        else:
            staff_display_rows.append({
                "物件番号": "", "物件名": "", "顧客名": "",
                "所属部署での登録枠": "", "その物件での累計就業時間": ""
            })
           
    st.dataframe(pd.DataFrame(staff_display_rows), use_container_width=True, hide_index=True, height=400)
   
    calc_sales = df_dept_final["売上高（円）"].sum()
    calc_cost = df_dept_final["商社協力業社支払（円）"].sum()
    calc_profit = calc_sales - calc_cost
    calc_rate = (calc_profit / calc_sales) * 100 if calc_sales > 0 else 0.0
 
    with summary_placeholder:
        st.header(f"【{target_year}】 会社全体 売上サマリー")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("売上金額", f"{calc_sales:,.0f} 円")
        col2.metric("支払金額", f"{calc_cost:,.0f} 円")
        col3.metric("売上純利益", f"{calc_profit:,.0f} 円")
        col4.metric("粗利率", f"{calc_rate:.1f} %")
 
# --- タブ2 ---
with tab2:
    st.header("🏗️ 物件別予算管理")
   
    active_projects = [k for k, v in projects_db.items() if isinstance(v, dict) and v.get("status") != "アーカイブ（完了）"]
    archived_projects = [k for k, v in projects_db.items() if isinstance(v, dict) and v.get("status") == "アーカイブ（完了）"]
   
    col_sel, col_new, col_del = st.columns([2, 1, 1])
   
    with col_sel:
        if not projects_db:
            st.warning("現在登録されている物件がありません。「新しい物件を登録する」から追加してください。")
            selected_project = None
        else:
            view_mode = st.radio("表示モード:", ["進行中の物件", "アーカイブ（過去の完了物件）"], horizontal=True)
            display_list = active_projects if view_mode == "進行中の物件" else archived_projects
            if not display_list:
                st.info(f"{view_mode}は現在ありません。")
                selected_project = None
            else:
                selected_project = st.selectbox("📂 管理・編集する物件を選択", display_list)
       
    with col_new:
        with st.expander("➕ 新しい物件を登録する"):
            n_proj_num = st.text_input("物件番号（例: 物001）")
            n_client_id = st.text_input("顧客管理番号（例: 顧001）※登録後変更不可")
            n_client = st.text_input("顧客名（会社名）※登録後変更不可")
            n_proj = st.text_input("新規物件名")
            n_year = st.selectbox("対象の期", YEAR_LIST, index=YEAR_LIST.index("57期"))
            n_cat = st.selectbox("ジャンル", CATEGORY_LIST)
           
            if st.button("登録する"):
                if n_proj and n_proj not in projects_db:
                    new_item = DEFAULT_PROJECT_DATA.copy()
                    new_item["client_id"] = n_client_id; new_item["client_name"] = n_client if n_client else "未設定"
                    new_item["project_number"] = n_proj_num; new_item["project_year"] = n_year
                    new_item["project_month"] = "9月"; new_item["category"] = n_cat
                    new_item["status"] = "進行中"
                    projects_db[n_proj] = new_item
                    save_projects(projects_db)
                    st.success("登録完了！")
                    st.rerun()
 
    with col_del:
        if selected_project:
            with st.expander("🗑️ 物件の削除・アーカイブ"):
                st.write(f"選択中: **{selected_project}**")
                if projects_db[selected_project].get("status") != "アーカイブ（完了）":
                    if st.button("📦 完了済みとしてアーカイブ（非表示）にする"):
                        projects_db[selected_project]["status"] = "アーカイブ（完了）"
                        save_projects(projects_db)
                        st.success("アーカイブしました！")
                        st.rerun()
                else:
                    if st.button("🔙 進行中に戻す"):
                        projects_db[selected_project]["status"] = "進行中"
                        save_projects(projects_db)
                        st.success("進行中に戻しました！")
                        st.rerun()
                st.markdown("---")
                if st.button("🚨 完全に削除する", type="primary"):
                    del projects_db[selected_project]
                    save_projects(projects_db)
                    st.success("物件を完全に削除しました！")
                    st.rerun()
 
    st.markdown("---")
   
    if selected_project:
        cur_data = projects_db[selected_project]
        cur_data["detail_a"] = merge_details(FULL_DETAIL_A, cur_data.get("detail_a", []))
        cur_data["detail_b"] = merge_details(FULL_DETAIL_B, cur_data.get("detail_b", []))
        cur_data["detail_c"] = merge_details(FULL_DETAIL_C, cur_data.get("detail_c", []))
        cur_data["detail_d"] = merge_details(FULL_DETAIL_D, cur_data.get("detail_d", []))
       
        st.subheader("📱 基本情報")
        m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns([1, 1.5, 1, 1, 1, 1])
        with m_col1: in_client_id = st.text_input("🆔 顧客管理番号", value=cur_data.get("client_id", ""))
        with m_col2: in_client = st.text_input("🏢 顧客名", value=cur_data.get("client_name", "未設定"))
        with m_col3: in_proj_num = st.text_input("📁 物件番号", value=cur_data.get("project_number", ""))
        with m_col4: in_year = st.selectbox("📅 対象の期", YEAR_LIST, index=YEAR_LIST.index(cur_data.get("project_year", "57期")) if cur_data.get("project_year", "57期") in YEAR_LIST else 4)
       
        safe_month = cur_data.get("project_month", "9月")
        if safe_month not in MONTH_LIST: safe_month = "9月"
        with m_col5: in_month = st.selectbox("📅 対象月度", MONTH_LIST, index=MONTH_LIST.index(safe_month))
       
        with m_col6: in_cat = st.selectbox("🏷️ ジャンル", CATEGORY_LIST, index=CATEGORY_LIST.index(cur_data.get("category", "未設定")) if cur_data.get("category", "未設定") in CATEGORY_LIST else 0)
       
        url_col1, url_col2 = st.columns(2)
        with url_col1:
            in_form_url = st.text_input("🔗 👥 QRコード勤怠打刻 GoogleフォームURL", value=cur_data.get("form_url", ""))
            if in_form_url:
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={in_form_url}"
                st.image(qr_url, caption="📱 現場打刻用QRコード", width=150)
        with url_col2: in_sheet_url = st.text_input("🔗 📑 勤怠集計データ GoogleスプレッドシートURL", value=cur_data.get("sheet_url", ""))
 
        st.markdown("---")
        bottom_left, bottom_right = st.columns([1, 1.8])
       
        with bottom_left:
            st.markdown("### 📄 営業計算書メモ")
            in_eval = st.text_area("＜現場での評価＞", value=cur_data.get("eval_memo", ""))
            in_budg = st.text_area("＜予算経緯＞", value=cur_data.get("budget_memo", ""))
            in_materials = st.text_area("＜建材・仕様の記録メモ＞", value=cur_data.get("materials_memo", ""))
           
        with bottom_right:
            st.markdown("### 🛠️ 工事カテゴリ別内訳")
            s_A, s_B, s_C, s_D = st.tabs(["内 (内装)", "設 (設備)", "電 (電気)", "P (厨房)"])
            g_conf = {"工種名": st.column_config.TextColumn(disabled=True), "業者管理番号": st.column_config.SelectboxColumn(options=[f"業{i:03d}" for i in range(1, 51)])}
            with s_A: ed_a = st.data_editor(pd.DataFrame(cur_data["detail_a"]), use_container_width=True, hide_index=True, column_config=g_conf, key="ea")
            with s_B: ed_b = st.data_editor(pd.DataFrame(cur_data["detail_b"]), use_container_width=True, hide_index=True, column_config=g_conf, key="eb")
            with s_C: ed_c = st.data_editor(pd.DataFrame(cur_data["detail_c"]), use_container_width=True, hide_index=True, column_config=g_conf, key="ec")
            with s_D: ed_d = st.data_editor(pd.DataFrame(cur_data["detail_d"]), use_container_width=True, hide_index=True, column_config=g_conf, key="ed")
 
        st.markdown("---")
        st.subheader("🖼️ 営業計算書（画像プレビュー）")
        calc_img_col1, calc_img_col2 = st.columns([1, 1])
       
        with calc_img_col1:
            saved_img = cur_data.get("calc_image", "")
            if saved_img and os.path.exists(saved_img):
                st.image(saved_img, use_container_width=True)
            else:
                st.info("現在、この物件に登録されている営業計算書の画像はありません。")
               
        with calc_img_col2:
            new_img = st.file_uploader("📷 新しい営業計算書をアップロード（※一番下の保存ボタンで確定します）", type=["png", "jpg", "jpeg"])
 
        st.markdown("---")
        st.subheader("👥 現場投入工数（就業時間）")
        df_attendance = None
        if in_sheet_url:
            try:
                if "/d/" in in_sheet_url:
                    csv_url = in_sheet_url.split("/edit")[0] + "/export?format=csv"
                    if "gid=" in in_sheet_url:
                        gid = in_sheet_url.split("gid=")[1].split("&")[0]
                        csv_url += f"&gid={gid}"
                    df_attendance = load_csv_data(csv_url) # ⚡ ここをキャッシュ化！
            except:
                st.warning("⚠️ 勤怠スプレッドシートの自動読み取りが出来ませんでした。共有設定を確認してください。")
 
        col_st1, col_st2, col_st3, col_st4 = st.columns(4)
        with col_st1:
            st.markdown("**第1管理部（設備）- 設**")
            in_staff_setsubi = st.multiselect("担当メンバー選択", all_staff_list, default=cur_data.get("staff_setsubi", []), key=f"sel_setsubi_{selected_project}")
            for s in in_staff_setsubi:
                h = get_hours_for_staff(df_attendance, s, selected_project)
                st.write(f"・{s}: `{h}`")
        with col_st2:
            st.markdown("**第2管理部（内装）- 内**")
            in_staff_naisou = st.multiselect("担当メンバー選択", all_staff_list, default=cur_data.get("staff_naisou", []), key=f"sel_naisou_{selected_project}")
            for s in in_staff_naisou:
                h = get_hours_for_staff(df_attendance, s, selected_project)
                st.write(f"・{s}: `{h}`")
        with col_st3:
            st.markdown("**第3管理部（電気）- 電**")
            in_staff_denki = st.multiselect("担当メンバー選択", all_staff_list, default=cur_data.get("staff_denki", []), key=f"sel_denki_{selected_project}")
            for s in in_staff_denki:
                h = get_hours_for_staff(df_attendance, s, selected_project)
                st.write(f"・{s}: `{h}`")
        with col_st4:
            st.markdown("**PM室（厨房等）- P**")
            in_staff_pm = st.multiselect("担当メンバー選択", all_staff_list, default=cur_data.get("staff_pm", []), key=f"sel_pm_{selected_project}")
            for s in in_staff_pm:
                h = get_hours_for_staff(df_attendance, s, selected_project)
                st.write(f"・{s}: `{h}`")
 
        st.markdown("---")
        if st.button(f"💾 【{selected_project}】 を保存", use_container_width=True, type="primary"):
            projects_db[selected_project]["client_id"] = in_client_id; projects_db[selected_project]["client_name"] = in_client
            projects_db[selected_project]["project_number"] = in_proj_num; projects_db[selected_project]["project_year"] = in_year
            projects_db[selected_project]["project_month"] = in_month; projects_db[selected_project]["category"] = in_cat
            projects_db[selected_project]["form_url"] = in_form_url; projects_db[selected_project]["sheet_url"] = in_sheet_url
            projects_db[selected_project]["eval_memo"] = in_eval; projects_db[selected_project]["budget_memo"] = in_budg
            projects_db[selected_project]["materials_memo"] = in_materials
            projects_db[selected_project]["detail_a"] = ed_a.to_dict('records'); projects_db[selected_project]["detail_b"] = ed_b.to_dict('records')
            projects_db[selected_project]["detail_c"] = ed_c.to_dict('records'); projects_db[selected_project]["detail_d"] = ed_d.to_dict('records')
           
            projects_db[selected_project]["staff_setsubi"] = in_staff_setsubi
            projects_db[selected_project]["staff_naisou"] = in_staff_naisou
            projects_db[selected_project]["staff_denki"] = in_staff_denki
            projects_db[selected_project]["staff_pm"] = in_staff_pm
 
            if new_img is not None:
                os.makedirs("uploaded_images", exist_ok=True)
                safe_name = "".join([c for c in selected_project if c.isalnum() or c in " _-"])
                img_path = f"uploaded_images/{safe_name}_calc.png"
                with open(img_path, "wb") as f:
                    f.write(new_img.getbuffer())
                projects_db[selected_project]["calc_image"] = img_path
               
            save_projects(projects_db)
            st.success("保存完了！設定、QRコード、および営業計算書画像がロックされました。")
            st.rerun()
 
# ==========================================
# --- タブ3：AI書類自動振り分け ---
# ==========================================
with tab3:
    st.header("📸 AI 書類自動振り分け（大革命版）")
    st.markdown("スマホのカメラで撮影するか、画像ファイルをアップロードするだけで、AIが自動で数値を読み取り、データベースに振り分けます。")
    st.info("💡 手書きの文字も読み取ります。**赤枠で囲んだ部分**の情報を最優先で抽出します。")
 
    if "ai_result" not in st.session_state:
        st.session_state.ai_result = None
 
    col_doc, col_input = st.columns(2)
    with col_doc:
        doc_type = st.radio("📄 読み込む書類の種類", ["営業計算書（新規物件登録）", "発注書", "請求書・見積書・領収書"])
    with col_input:
        input_type = st.radio("📷 画像の入力方法", ["ファイルから選ぶ", "カメラで撮影する"])
 
    image_file = None
    if input_type == "ファイルから選ぶ":
        image_file = st.file_uploader("画像（jpg, png）を選択してください", type=["jpg", "jpeg", "png"])
    else:
        image_file = st.camera_input("書類を撮影してください")
 
    if image_file is not None:
        img = Image.open(image_file).convert('RGB')
        st.image(img, caption="読み込み対象の画像", width=400)
       
        if st.button("✨ AIで情報を自動抽出する", type="primary", use_container_width=True):
            if GEMINI_API_KEY == "ここに取得したAPIキーを貼り付けてください":
                st.error("⚠️ コードの上部にある `GEMINI_API_KEY` が設定されていません。先ほど取得したキーを貼り付けてください。")
            else:
                with st.spinner('AIが画像を解析中...（数十秒かかる場合があります）'):
                    try:
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        prompt_base = f"""
                        あなたはプロの建築・内装業の優秀な経理アシスタントAIです。
                        添付された画像は「{doc_type}」です。画像から以下の項目を正確に抽出して、JSON形式で出力してください。
                       
                        【重要ルール】
                        1. 手書きの文字も丁寧に読み取ってください。
                        2. 赤枠や赤線で囲まれた文字や数字がある場合は、それを「絶対に最優先」で抽出してください。
                        3. 出力は必ず以下のJSONフォーマットのみにしてください。説明文などは一切含めないでください。
                        """
                       
                        if doc_type == "営業計算書（新規物件登録）":
                            prompt = prompt_base + """
                            {
                                "物件番号": "抽出した物件番号(例: 56T-2-3005など)",
                                "顧客名": "抽出した契約先の会社名",
                                "物件名": "抽出した現場名",
                                "受注金額": 123456,
                                "分類": "抽出した分類(例: 外食産業、内装工事など 黒丸がついているもの)"
                            }
                            ※金額は「本工事受注金額」の数字のみを数値(カンマなし)で入れてください。
                            """
                        elif doc_type == "発注書":
                            prompt = prompt_base + """
                            {
                                "物件名": "抽出した物件名",
                                "顧客名": "抽出した顧客名",
                                "金額": 123456
                            }
                            ※金額は「税抜振込金額」の数字のみを数値(カンマなし)で入れてください。
                            """
                        else:
                            prompt = prompt_base + """
                            {
                                "物件名": "抽出した物件名",
                                "業者名": "抽出した業者名",
                                "金額": 123456
                            }
                            ※金額は「税抜支払金額」の数字のみを数値(カンマなし)で入れてください。
                            """
                       
                        response = model.generate_content([prompt, img])
                        res_text = response.text
                        json_str = re.search(r'\{.*\}', res_text, re.DOTALL)
                        if json_str:
                            extracted_data = json.loads(json_str.group())
                            st.session_state.ai_result = extracted_data
                            st.success("🎉 AIの読み取りが完了しました！")
                        else:
                            st.error("読み取りフォーマットが不正です。もう一度お試しください。")
                           
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
 
    if st.session_state.ai_result:
        st.markdown("### 📝 AI 抽出結果の確認と反映")
        data = st.session_state.ai_result
        st.write("AIが読み取ったデータ:")
        st.json(data)
        st.info("👇 以下の項目を確認・修正して反映ボタンを押してください。")
       
        project_names = list(projects_db.keys())
       
        if doc_type == "営業計算書（新規物件登録）":
            confirm_proj = st.text_input("新規物件名", value=data.get("物件名", ""), key="ai_proj_name")
            confirm_client = st.text_input("顧客名", value=data.get("顧客名", ""), key="ai_client_name")
            confirm_num = st.text_input("物件番号", value=data.get("物件番号", ""), key="ai_proj_num")
           
            guessed_term = "57期"
            if confirm_num and confirm_num[:2].isdigit():
                term_str = confirm_num[:2] + "期"
                if term_str in YEAR_LIST:
                    guessed_term = term_str
                   
            confirm_year = st.selectbox("対象の期", YEAR_LIST, index=YEAR_LIST.index(guessed_term), key="ai_proj_year")
           
            ai_cat = data.get("分類", "")
            guessed_cat = "未設定"
            if "外食" in ai_cat or "カフェ" in ai_cat: guessed_cat = "飲食(その他)"
            if "アパレル" in ai_cat: guessed_cat = "アパレル"
            confirm_cat = st.selectbox("ジャンル", CATEGORY_LIST, index=CATEGORY_LIST.index(guessed_cat) if guessed_cat in CATEGORY_LIST else 0, key="ai_proj_cat")
           
            if st.button("🚀 この営業計算書から新規物件を自動作成する", type="primary"):
                if confirm_proj and confirm_proj not in projects_db:
                    new_item = DEFAULT_PROJECT_DATA.copy()
                    new_item["client_name"] = confirm_client
                    new_item["project_number"] = confirm_num
                    new_item["project_year"] = confirm_year
                    new_item["category"] = confirm_cat
                    order_amt = data.get("受注金額", 0)
                    new_item["budget_memo"] = f"AI自動読取による初期データ\n本工事受注金額: {order_amt:,} 円"
                   
                    projects_db[confirm_proj] = new_item
                    save_projects(projects_db)
                    st.success(f"🎉 大成功！ 新規物件「{confirm_proj}」を全自動でデータベースに登録しました！タブ2で確認してください。")
                    st.session_state.ai_result = None
                elif confirm_proj in projects_db:
                    st.error("その物件名はすでに登録されています。別の名前をご入力ください。")
                else:
                    st.error("物件名を入力してください。")

        elif doc_type == "発注書":
            selected_proj = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names)
            confirm_client = st.text_input("顧客名", value=data.get("顧客名", ""))
            confirm_amount = st.number_input("税抜振込金額", value=int(data.get("金額", 0)))
           
            if st.button("🚀 この発注データを物件に反映する"):
                if selected_proj != "(選択してください)":
                    projects_db[selected_proj]["client_name"] = confirm_client
                    save_projects(projects_db)
                    st.success(f"✅ {selected_proj} の顧客名データを更新しました！")
                    st.session_state.ai_result = None
                else:
                    st.error("物件名を選択してください。")
                   
        else: # 請求書・見積書
            selected_proj = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names)
            contractor_names = df_contractor_master["業者・工種名"].tolist()
            contractor_ids = df_contractor_master["業者管理番号"].tolist()
            ai_contractor = data.get("業者名", "")
           
            c_col1, c_col2, c_col3 = st.columns(3)
            with c_col1:
                sel_contractor_idx = st.selectbox("紐付ける業者（AI抽出: " + ai_contractor + "）", range(len(contractor_names)), format_func=lambda i: f"{contractor_ids[i]}: {contractor_names[i]}")
                actual_gyo_id = contractor_ids[sel_contractor_idx]
            with c_col2:
                all_koshu = [x["工種名"] for x in FULL_DETAIL_A + FULL_DETAIL_B + FULL_DETAIL_C + FULL_DETAIL_D]
                sel_koshu = st.selectbox("紐付ける工種", all_koshu)
            with c_col3:
                confirm_amount = st.number_input("税抜支払金額", value=int(data.get("金額", 0)))
           
            if st.button("🚀 この支払データを物件に反映する", type="primary"):
                if selected_proj != "(選択してください)":
                    found = False
                    for cat in ["detail_a", "detail_b", "detail_c", "detail_d"]:
                        for item in projects_db[selected_proj][cat]:
                            if item["工種名"] == sel_koshu:
                                item["業者管理番号"] = actual_gyo_id
                                item["協力業者支払"] += confirm_amount
                                found = True
                                break
                        if found: break
                       
                    if found:
                        save_projects(projects_db)
                        st.success(f"🎉 大成功！ {selected_proj} の {sel_koshu} ({actual_gyo_id}) に {confirm_amount:,} 円の支払データを全自動で反映しました！")
                        st.session_state.ai_result = None
                        st.rerun()
                    else:
                        st.error("エラー：工種が見つかりませんでした。")
                else:
                    st.error("物件名を選択してください。")
 
# ==========================================
# --- タブ4：顧客別 実績・分析 ---
# ==========================================
with tab4:
    st.header("📈 主要顧客別 実績・分析")
    st.markdown("日々の物件データからの「自動集計」と、過去のエクセルデータの「取込・確認・自動振り分け」を行います。")
   
    t4_sub1, t4_sub2 = st.tabs(["📊 現在・未来の自動集計 (57期〜)", "📁 過去実績データの取込・自動振り分け (〜56期)"])
   
    with t4_sub1:
        st.subheader("現在入力されているデータからの顧客別 自動集計")
       
        all_clients = sorted(list(set([v.get("client_name", "未設定") for v in projects_db.values() if isinstance(v, dict)])))
        all_clients = [c for c in all_clients if c != "未設定" and "合計" not in c and "修理" not in c and "スキップ" not in c]
       
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            sel_client = st.selectbox("分析する顧客名を選択", ["(選択してください)"] + all_clients)
        with col_c2:
            sel_year = st.selectbox("対象の期を選択（自動集計用）", YEAR_LIST, index=YEAR_LIST.index("57期"))
           
        if sel_client != "(選択してください)":
            client_sales = 0.0
            client_cost = 0.0
            month_sales = {m: 0.0 for m in MONTH_LIST}
            month_cost = {m: 0.0 for m in MONTH_LIST}
            target_projects = []
           
            for p_name, p_data in projects_db.items():
                if not isinstance(p_data, dict): continue
                if p_data.get("client_name") == sel_client and p_data.get("project_year") == sel_year:
                    target_projects.append(p_name)
                    p_month = p_data.get("project_month", "9月")
                   
                    val_a = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_a", []))
                    val_b = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_b", []))
                    val_c = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_c", []))
                    val_d = sum(safe_num(x.get("完了金額")) for x in p_data.get("detail_d", []))
                    p_sales = val_a + val_b + val_c + val_d
                   
                    p_cost = 0.0
                    for cat in ["detail_a", "detail_b", "detail_c", "detail_d"]:
                        for item in p_data.get(cat, []):
                            p_cost += safe_num(item.get("協力業者支払"))
                           
                    client_sales += p_sales
                    client_cost += p_cost
                    if p_month in month_sales:
                        month_sales[p_month] += p_sales
                        month_cost[p_month] += p_cost
                       
            client_profit = client_sales - client_cost
            client_margin = (client_profit / client_sales) if client_sales > 0 else 0.0
           
            st.markdown(f"### 🏢 {sel_client} - {sel_year} 実績")
            st.write(f"**対象物件数:** {len(target_projects)}件 ({', '.join(target_projects)})")
           
            st.markdown("#### 📅 期 総合計")
            cols = st.columns(3)
            cols[0].metric("純売上額", f"{client_sales:,.0f} 円")
            cols[1].metric("粗利額", f"{client_profit:,.0f} 円")
            cols[2].metric("粗利率", f"{client_margin*100:.1f} %")
           
            row_sales = {"項目": "売上"}
            row_profit = {"項目": "粗利"}
            row_margin = {"項目": "粗利率"}
           
            for m in MONTH_LIST:
                row_sales[m] = f"{month_sales[m]:,.0f}"
                m_profit = month_sales[m] - month_cost[m]
                row_profit[m] = f"{m_profit:,.0f}"
                m_margin = (m_profit / month_sales[m]) if month_sales[m] > 0 else 0.0
                row_margin[m] = f"{m_margin*100:.1f}%"
               
            df_client_months = pd.DataFrame([row_sales, row_profit, row_margin])
            st.markdown("#### 📆 月別推移（9月〜8月）")
            st.info("※「その他」など、月別データが存在せず年間合計のみの顧客は、代表して「9月」の列に1年分の数字がまとめて表示されます。")
            st.dataframe(df_client_months, use_container_width=True, hide_index=True)
 
    with t4_sub2:
        st.subheader("📁 過去のExcelデータのアップロード・自動振り分け")
       
        st.info("※もし間違ったデータを取り込んでしまった場合は、下のボタンで一度リセットできます。")
        if st.button("🗑️ 【やり直し用】取り込んだ過去のデータをすべてリセット（消去）する", type="secondary"):
            keys_to_delete = [k for k in projects_db.keys() if str(k).startswith("【過去実績】")]
            if keys_to_delete:
                for k in keys_to_delete:
                    del projects_db[k]
                save_projects(projects_db)
                st.success(f"🧹 {len(keys_to_delete)}件の過去データをリセットしました。もう一度下のボタンから取り込んでください！")
                st.rerun()
            else:
                st.info("削除する過去データはありませんでした。")
               
        st.markdown("---")
        past_file = st.file_uploader("エクセルファイル (.xlsx) を選択してください", type=["xlsx"])
        PAST_EXCEL_PATH = "uploaded_images/past_sales_data.xlsx"
       
        if past_file is not None:
            os.makedirs("uploaded_images", exist_ok=True)
            with open(PAST_EXCEL_PATH, "wb") as f:
                f.write(past_file.getbuffer())
            st.success("✅ 過去の売上データをアプリ内に保存しました！")
           
        if os.path.exists(PAST_EXCEL_PATH):
            try:
                df_past = load_excel_data(PAST_EXCEL_PATH) # ⚡ ここもキャッシュ化！
                st.markdown("**保存されている過去データ（プレビュー）**")
                df_past_display = df_past.fillna("").astype(str)
                st.dataframe(df_past_display, use_container_width=True, height=250)
               
                st.markdown("---")
                if st.button("🚀 このExcelから全顧客の【過去実績（月別推移）】を全自動で抽出してデータベースに登録する", type="primary"):
                    add_count = 0
                    current_client = "未設定"
                   
                    month_cols = {
                        "9月": (16, 17), "10月": (19, 20), "11月": (22, 23), "12月": (25, 26),
                        "1月": (28, 29), "2月": (31, 32), "3月": (34, 35), "4月": (37, 38),
                        "5月": (40, 41), "6月": (43, 44), "7月": (46, 47), "8月": (49, 50)
                    }
                   
                    for i in range(len(df_past)):
                        col_A_val = str(df_past.iloc[i, 0]).strip()
                        if col_A_val != "nan" and col_A_val != "":
                            if "合計" in col_A_val or "修理" in col_A_val:
                                current_client = "スキップ"
                            else:
                                current_client = col_A_val
                               
                        col_B_val = str(df_past.iloc[i, 1]).strip()
                        match = re.search(r'(\d{2}期)', col_B_val)
                       
                        if match and current_client != "未設定" and current_client != "スキップ":
                            term_str = match.group(1)
                            data_row = i + 1
                           
                            if data_row >= len(df_past): continue
                           
                            month_data_found = False
                           
                            for m_name, (col_sales, col_profit) in month_cols.items():
                                if col_profit >= len(df_past.columns): continue
                               
                                try:
                                    sales_val = float(str(df_past.iloc[data_row, col_sales]).replace(',', '').strip())
                                    profit_val = float(str(df_past.iloc[data_row, col_profit]).replace(',', '').strip())
                                except:
                                    continue
                                   
                                if pd.isna(sales_val) or sales_val == 0:
                                    continue
                                   
                                month_data_found = True
                                cost_val = sales_val - profit_val
                                proj_name = f"【過去実績】{current_client}_{term_str}_{m_name}"
                               
                                if proj_name not in projects_db:
                                    new_item = DEFAULT_PROJECT_DATA.copy()
                                    new_item["client_name"] = current_client
                                    new_item["project_number"] = f"過去{term_str}"
                                    new_item["project_year"] = term_str
                                    new_item["project_month"] = m_name
                                    new_item["category"] = "飲食(その他)"
                                    new_item["status"] = "アーカイブ（完了）"
                                    new_item["budget_memo"] = f"過去のExcelデータからの月別自動取り込み ({current_client})"
                                    new_item["detail_a"] = [item.copy() for item in FULL_DETAIL_A]
                                    new_item["detail_b"] = [item.copy() for item in FULL_DETAIL_B]
                                    new_item["detail_c"] = [item.copy() for item in FULL_DETAIL_C]
                                    new_item["detail_d"] = [item.copy() for item in FULL_DETAIL_D]
                                   
                                    for item in new_item["detail_a"]:
                                        if item["工種名"] == "内装工事":
                                            item["完了金額"] = sales_val
                                            item["協力業者支払"] = cost_val
                                            item["業者管理番号"] = "業001"
                                            break
                                    projects_db[proj_name] = new_item
                                    add_count += 1
                                   
                            if not month_data_found:
                                try:
                                    total_sales = float(str(df_past.iloc[i, 4]).replace(',', '').strip())
                                    total_profit = float(str(df_past.iloc[i, 5]).replace(',', '').strip())
                                except:
                                    continue
                                   
                                if not pd.isna(total_sales) and total_sales != 0:
                                    cost_val = total_sales - total_profit
                                    proj_name = f"【過去実績】{current_client}_{term_str}_通期"
                                   
                                    if proj_name not in projects_db:
                                        new_item = DEFAULT_PROJECT_DATA.copy()
                                        new_item["client_name"] = current_client
                                        new_item["project_number"] = f"過去{term_str}"
                                        new_item["project_year"] = term_str
                                        new_item["project_month"] = "9月"
                                        new_item["category"] = "飲食(その他)"
                                        new_item["status"] = "アーカイブ（完了）"
                                        new_item["budget_memo"] = f"過去Excel（月別なし）からの年間合計取り込み ({current_client})"
                                        new_item["detail_a"] = [item.copy() for item in FULL_DETAIL_A]
                                        new_item["detail_b"] = [item.copy() for item in FULL_DETAIL_B]
                                        new_item["detail_c"] = [item.copy() for item in FULL_DETAIL_C]
                                        new_item["detail_d"] = [item.copy() for item in FULL_DETAIL_D]
                                       
                                        for item in new_item["detail_a"]:
                                            if item["工種名"] == "内装工事":
                                                item["完了金額"] = total_sales
                                                item["協力業者支払"] = cost_val
                                                item["業者管理番号"] = "業001"
                                                break
                                        projects_db[proj_name] = new_item
                                        add_count += 1
                                   
                    if add_count > 0:
                        save_projects(projects_db)
                        st.success(f"🎉 大成功！ {add_count}件の過去データをデータベースに登録しました！")
                        st.info("💡 「タブ1」に戻って、集計する期を「53期」などに変更してみてください。複数の顧客の数字が反映されています！")
                    else:
                        st.info("新しく登録できるデータは見つかりませんでした。")
                       
            except Exception as e:
                st.error(f"Excelの読み込みに失敗しました: {e}") 

