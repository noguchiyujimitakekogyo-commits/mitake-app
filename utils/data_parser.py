import pandas as pd
import re
import os
import datetime
import streamlit as st

def backup_uploaded_file(file_bytes, original_filename, prefix="backup"):
    storage_dir = "storage_archive"
    os.makedirs(storage_dir, exist_ok=True)
    current_ymd = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = original_filename.split('.')[-1] if '.' in original_filename else 'xlsx'
    file_path = os.path.join(storage_dir, f"{prefix}_{current_ymd}.{ext}")
    with open(file_path, "wb") as f: f.write(file_bytes)
    return file_path

def safe_num(v):
    try:
        if v is not None and str(v).strip() != "":
            clean_v = str(v).translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            clean_v = re.sub(r'[^\d.-]', '', clean_v)
            if not clean_v: return 0.0
            return float(clean_v)
        else: return 0.0
    except: return 0.0

def safe_extract_float(val_str):
    try:
        clean = str(val_str).translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        clean = re.sub(r'[^\d.-]', '', clean)
        if clean and clean not in ['.', '-', '-.']: return float(clean)
        return 0.0
    except: return 0.0

def get_val(df, r, c, default=""):
    try:
        val = df.iat[r, c]
        return "" if pd.isna(val) else str(val).strip()
    except: return default

def extract_core_project_num(num_str):
    if not num_str: return ""
    num_str = str(num_str).translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))
    num_str = re.sub(r'[ー‐−−_]', '-', num_str) 
    match = re.search(r'5\d[a-zA-Z]-\d-\d{4}', num_str)
    if match: return match.group(0).upper()
    match_fallback = re.search(r'\d{2}[a-zA-Z]-\d-\d{4}', num_str)
    if match_fallback: return match_fallback.group(0).upper()
    return str(num_str).strip()

def calc_hours_from_time_str(time_str):
    try:
        time_str = str(time_str).strip()
        if not time_str or time_str.lower() in ["nan", "nat", "none", ""]: return 0.0
        try: return float(time_str)
        except ValueError: pass
        time_str = time_str.translate(str.maketrans('０１２３４５６７８９：〜～ー−', '0123456789:----'))
        time_str = time_str.replace("~", "-")
        time_str = re.sub(r'[^0-9:\-]', '', time_str)
        if not time_str: return 0.0
        parts = time_str.split("-")
        if len(parts) == 2:
            start_t = datetime.datetime.strptime(parts[0].strip(), "%H:%M")
            end_t = datetime.datetime.strptime(parts[1].strip(), "%H:%M")
            diff = (end_t - start_t).total_seconds() / 3600.0
            break_time = 1.0 if diff >= 6.0 else 0.0
            return max(0.0, diff - break_time)
        return 0.0 
    except: return 0.0 

def parse_single_andpad_excel(excel_file_path):
    try:
        df = pd.read_excel(excel_file_path, sheet_name='予定表', header=None)
        parsed_data = {}
        data_values = df.values 
        rows_count = len(data_values)
        current_staff = None
        dates_row = data_values[3][5:] if rows_count > 3 else []
        for i in range(4, rows_count):
            row = data_values[i]
            if pd.notna(row[2]) and str(row[2]) != '氏名':
                raw_staff_name = str(row[2])
                current_staff = re.sub(r'\s+', '', raw_staff_name) 
                if current_staff not in parsed_data: parsed_data[current_staff] = []
            if len(row) > 4 and str(row[4]) == '案件名' and current_staff:
                projects = row[5:]
                times = data_values[i+1][5:] if (i+1) < rows_count else []
                for col_idx, project in enumerate(projects):
                    if pd.notna(project):
                        p_str = re.sub(r'\s+', '', str(project)) 
                        raw_name = str(project).strip()
                        t_str = str(times[col_idx]) if col_idx < len(times) else ""
                        hours = calc_hours_from_time_str(t_str)
                        d_str = str(dates_row[col_idx]).strip() if col_idx < len(dates_row) and pd.notna(dates_row[col_idx]) else "不明"
                        if hours > 0:
                            rec_key = f"{current_staff}_{d_str}_{raw_name}_{t_str}"
                            parsed_data[current_staff].append({
                                "proj": p_str, "raw_name": raw_name, "hours": hours, "date": d_str, "key": rec_key
                            })
        return parsed_data
    except Exception as e:
        print(f"Excel Parse Error: {e}") 
        return {}

@st.cache_data(show_spinner=False)
def get_accumulated_andpad_dict(file_mtime_tuple):
    master_parsed = {}
    for path, _ in file_mtime_tuple:
        single_data = parse_single_andpad_excel(path)
        for staff, items in single_data.items():
            if staff not in master_parsed: master_parsed[staff] = []
            master_parsed[staff].extend(items)
            
    cleaned_master_parsed = {}
    ignore_words = ["休", "休日", "有給", "有休", "公休", "代休", "振休", "休業", "欠勤"]
    
    for staff, items in master_parsed.items():
        unique_items = {}
        for item in items:
            raw_name = str(item.get("raw_name", "")).strip()
            
            is_holiday = False
            if raw_name == "休" or any(w in raw_name for w in ignore_words):
                is_holiday = True
                
            if not is_holiday:
                rec_key = item.get("key")
                unique_items[rec_key] = item 
                
        cleaned_master_parsed[staff] = list(unique_items.values())
        
    return cleaned_master_parsed

def parse_sales_calc_data(df, mode="budget"):
    data = {}
    data["物件番号"] = get_val(df, 2, 3)
    data["顧客名"] = get_val(df, 3, 3)
    data["物件名"] = get_val(df, 7, 3)
    data["営業担当"] = ""
    for r in range(min(20, len(df))):
        for c in range(min(20, len(df.columns))):
            val = str(df.iat[r, c]).strip()
            if "営業担当" in val:
                for offset in range(1, 4):
                    if c + offset < len(df.columns):
                        v = str(df.iat[r, c+offset]).strip()
                        if v and v != "nan" and v != "営業担当":
                            data["営業担当"] = v
                            break
                if not data["営業担当"]:
                    for offset in range(1, 3):
                        if r + offset < len(df):
                            v = str(df.iat[r+offset, c]).strip()
                            if v and v != "nan" and v != "営業担当":
                                data["営業担当"] = v
                                break
    order_amt = 0
    for r in range(min(30, len(df))):
        for c in range(len(df.columns)):
            val = str(df.iat[r, c]).strip()
            if "本工事受注金額" in val or "受注合計" in val or "受注金額" in val:
                for offset_r in range(1, 4):
                    try:
                        amt = safe_extract_float(df.iat[r + offset_r, c])
                        if amt > 0: 
                            order_amt = amt; break
                    except: pass
                if order_amt == 0:
                    for offset_c in range(1, 4):
                        if c + offset_c < len(df.columns):
                            try:
                                amt = safe_extract_float(df.iat[r, c + offset_c])
                                if amt > 0: 
                                    order_amt = amt; break
                            except: pass
                if order_amt > 0: break
        if order_amt > 0: break
    if order_amt == 0:
        try: order_amt = safe_extract_float(df.iat[13, 18])
        except: pass
    data["受注金額"] = order_amt
    
    deposits_extracted = []
    month_val = "9月"
    for r in range(min(30, len(df))):
        for c in range(len(df.columns)):
            val = str(df.iat[r, c]).strip()
            if "受注・請求" in val or "出来高請求" in val:
                for col_idx in range(c+1, min(c+15, len(df.columns))):
                    try:
                        amt_val = safe_extract_float(df.iat[r, col_idx])
                        if amt_val > 0:
                            m_candidate = str(df.iat[r-1, col_idx]).strip()
                            if "月" in m_candidate:
                                month_val = m_candidate
                                deposits_extracted.append({"月度": m_candidate, "金額": amt_val})
                    except: pass
    
    data["月度"] = month_val
    data["入金スケジュール"] = deposits_extracted
    
    target_hours = 0.0
    for r in range(min(50, len(df))):
        for c in range(len(df.columns)):
            val = str(df.iat[r, c]).strip()
            if "目標工数" in val or "予定工数" in val:
                for offset_c in range(1, 4):
                    if c + offset_c < len(df.columns):
                        amt = safe_extract_float(df.iat[r, c + offset_c])
                        if amt > 0:
                            target_hours = amt; break
                if target_hours > 0: break
        if target_hours > 0: break
    data["目標工数"] = target_hours
    
    for r in range(len(df)):
        for c in range(min(5, len(df.columns))):
            val = str(df.iat[r, c]).strip()
            target_col = 18 if len(df.columns) > 18 else len(df.columns) - 1
            amt = safe_extract_float(get_val(df, r, target_col))
            
            if "工事原価合計" in val: data["工事原価合計"] = amt
            elif "売上総利益" in val: data["売上総利益"] = amt
            elif "売上粗利率" in val: data["売上粗利率"] = amt
            elif "販売管理費" in val: data["販売管理費"] = amt
            elif "c.営業利益" in val or ("営業利益" in val and "原価" not in val): data["営業利益"] = amt
            elif "原価＋営業利益" in val or "d.原価" in val: data["原価＋営業利益"] = amt
            elif "実行予算利益" in val: data["実行予算利益"] = amt
            elif "実行予算粗利率" in val: data["実行予算粗利率"] = amt
            elif "労務費" in val and "小計" in str(get_val(df, r, c+1)): data["労務費"] = amt
    
    data["分類1"] = ""; data["分類2"] = ""; data["元請_下請"] = ""
    materials = []; subcontracts = []; expenses = []
    current_category = None
    
    for i in range(14, len(df)):
        col1 = get_val(df, i, 1)
        budget = safe_extract_float(get_val(df, i, 18))
        if budget == 0: budget = safe_extract_float(get_val(df, i, 2))
        payment = safe_extract_float(get_val(df, i, 15))
        
        if mode == "payment": budget = 0.0
        elif mode == "budget": payment = 0.0
        
        if "材料費" in col1: current_category = materials; continue
        elif "外注費" in col1: current_category = subcontracts; continue
        elif "現場経費" in col1: current_category = expenses; continue
        elif "労務費" in col1: current_category = None; continue
            
        if current_category is not None:
            if col1 and col1.lower() not in ["nan", "0", "a", "b", "c", "d", "e", "f", "g", "h", "i", "小計", ""]:
                if budget > 0 or payment > 0:
                    current_category.append({"会社名": col1, "実行予算": budget, "支払金額": payment})
                    
    data["材料費リスト"] = materials
    data["外注費リスト"] = subcontracts
    data["現場経費リスト"] = expenses
    return data

def parse_payment_data(df):
    data = {
        "物件番号": "", "顧客名": "", "物件名": "【実績データから自動取得】", "営業担当": "",
        "受注金額": 0, "月度": "9月", "分類1": "", "分類2": "", "元請_下請": "",
        "材料費リスト": [], "外注費リスト": [], "現場経費リスト": []
    }
    for r in range(min(15, len(df))):
        for c in range(len(df.columns)):
            val = str(df.iat[r, c]).strip()
            if "得意先" in val and c + 1 < len(df.columns):
                data["顧客名"] = str(df.iat[r, c+1]).strip()
            if "請負金額" in val and c + 1 < len(df.columns):
                data["受注金額"] = safe_extract_float(df.iat[r, c+1])
            if "営業担当" in val and c + 1 < len(df.columns):
                v = str(df.iat[r, c+1]).strip()
                if v and v != "nan": data["営業担当"] = v
                
    try:
        val = str(df.iat[2, 0]).strip()
        if not val or val == "nan": val = str(df.iat[1, 0]).strip()
        if val and val != "nan":
            parts = val.split(" ", 1)
            if len(parts) > 1:
                data["物件番号"] = parts[0]
                data["物件名"] = parts[1]
            else: data["物件名"] = val
    except: pass

    found_table = False
    name_col, amt_col = 0, 3
    start_row = 15
    for r in range(min(30, len(df))):
        for c in range(len(df.columns)):
            if "仕入先" in str(df.iat[r, c]):
                found_table = True
                name_col = c
                start_row = r + 1
                for c2 in range(c, len(df.columns)):
                    if "原価累計" in str(df.iat[r, c2]) or "発注金額" in str(df.iat[r, c2]):
                        amt_col = c2
                break
        if found_table: break

    subcontracts = []
    if found_table:
        for r in range(start_row, len(df)):
            name = str(df.iat[r, name_col]).strip()
            if name and name not in ["nan", "合計", "***合計***"]:
                amt = safe_extract_float(df.iat[r, amt_col])
                if amt > 0: subcontracts.append({"会社名": name, "実行予算": 0.0, "支払金額": amt})
    
    data["外注費リスト"] = subcontracts
    return data

def get_default_project_data():
    return {
        "client_name": "未設定", "project_number": "", "project_year": "57期",  
        "project_month": "9月", "status": "進行中", "sales_rep": "", 
        "eval_memo": "", "budget_memo": "", "materials_memo": "", "meeting_memo": "", "calc_image": "",
        "estimate_memo": "", "estimate_file": "", "andpad_url": "", "obsidian_url": "",
        "受注金額": 0, "project_dept": "内", "bunrui_1": "", "bunrui_2": "", "motouke_shitauke": "",
        "dep1_amt": 0, "dep1_m": "未定", "dep2_amt": 0, "dep2_m": "未定", "dep3_amt": 0, "dep3_m": "未定",
        "summary_koji_genka": 0.0, "summary_uriage_sorieki": 0.0, "summary_uriage_soriritsu": 0.0,
        "summary_han_kan_hi": 0.0, "summary_eigyorieki": 0.0, "summary_genka_eigyorieki": 0.0,
        "summary_jikko_yosan_rieki": 0.0, "summary_jikko_yosan_riritsu": 0.0, "summary_romuhi": 0.0,
        "target_hours": 0.0, "progress_rate": 100.0, "aliases": [], "ignored_andpad_keys": [], 
        "detail_a": [], "detail_b": [], "detail_c": [], "detail_d": [], "detail_request": [], 
        "staff_setsubi": [], "staff_naisou": [], "staff_denki": [], "staff_pm": []
    }