import os
import re
import datetime
import streamlit as str_st
import pandas as pd

ANDPAD_ACC_DIR = "uploaded_images/andpad_accumulated"
os.makedirs(ANDPAD_ACC_DIR, exist_ok=True)

def calc_hours_from_time_str(time_str):
    try:
        time_str = str(time_str).strip()
        if not time_str or time_str.lower() in ["nan", "nat", "none", ""]: 
            return 0.0
        try: 
            return float(time_str)
        except ValueError: 
            pass
        time_str = time_str.translate(str.maketrans('０１２３４５６７８９：〜～ー−', '0123456789:----'))
        time_str = time_str.replace("~", "-")
        time_str = re.sub(r'[^0-9:\-]', '', time_str)
        if not time_str: 
            return 0.0
        parts = time_str.split("-")
        if len(parts) == 2:
            start_t = datetime.datetime.strptime(parts[0].strip(), "%H:%M")
            end_t = datetime.datetime.strptime(parts[1].strip(), "%H:%M")
            diff = (end_t - start_t).total_seconds() / 3600.0
            break_time = 1.0 if diff >= 6.0 else 0.0
            return max(0.0, diff - break_time)
        return 0.0 
    except: 
        return 0.0 

def parse_single_andpad_excel(path):
    try:
        df = pd.read_excel(path, sheet_name='予定表', header=None)
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
                if current_staff not in parsed_data: 
                    parsed_data[current_staff] = []
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
    except: 
        return {}

def get_accumulated_files_tuple():
    if not os.path.exists(ANDPAD_ACC_DIR): 
        return ()
    files = sorted([os.path.join(ANDPAD_ACC_DIR, f) for f in os.listdir(ANDPAD_ACC_DIR) if f.endswith(('.xlsx', '.xls'))])
    return tuple((f, os.path.getmtime(f)) for f in files)

@str_st.cache_data(show_spinner=False)
def get_accumulated_andpad_dict(file_mtime_tuple):
    master_parsed = {}
    for path, _ in file_mtime_tuple:
        single_data = parse_single_andpad_excel(path)
        for staff, items in single_data.items():
            if staff not in master_parsed: 
                master_parsed[staff] = []
            master_parsed[staff].extend(items)
    return master_parsed

def extract_core_project_num(num_str):
    if not num_str: 
        return ""
    num_str = str(num_str).translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭNＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))
    num_str = re.sub(r'[ー‐−−_]', '-', num_str) 
    match = re.search(r'5\d[a-zA-Z]-\d-\d{4}', num_str)
    if match: 
        return match.group(0).upper()
    match_fallback = re.search(r'\d{2}[a-zA-Z]-\d-\d{4}', num_str)
    if match_fallback: 
        return match_fallback.group(0).upper()
    return str(num_str).strip()

def get_hours_from_andpad(staff_name, current_project, project_number="", aliases=None, ignored_keys=None, parsed_andpad_data=None):
    if not parsed_andpad_data: 
        return 0.0
    aliases = aliases or []
    ignored_keys = ignored_keys or []
    
    safe_staff = re.sub(r'\s+', '', str(staff_name))
    cp = re.sub(r'\s+', '', str(current_project))
    core_db_num = extract_core_project_num(project_number)
    safe_aliases = [re.sub(r'\s+', '', str(a)) for a in aliases if a]
    
    total = 0.0
    for excel_staff, items in parsed_andpad_data.items():
        is_staff_match = False
        if safe_staff in excel_staff or excel_staff in safe_staff: 
            is_staff_match = True
        elif len(safe_staff) >= 2 and safe_staff[:2] in excel_staff: 
            is_staff_match = True
        
        if is_staff_match:
            for item in items:
                if item.get("key") in ignored_keys: 
                    continue
                c_proj = item["proj"]
                raw_name = item["raw_name"]
                if not c_proj: 
                    continue
                is_match = False
                
                core_andpad_num = extract_core_project_num(raw_name)
                if core_db_num and core_andpad_num and core_db_num == core_andpad_num:
                    is_match = True
                elif not is_match:
                    if cp and (cp in c_proj): 
                        is_match = True
                    elif len(c_proj) >= 2 and (c_proj in cp): 
                        is_match = True
                    else:
                        for a in safe_aliases:
                            if a and a in c_proj: 
                                is_match = True
                                break
                                
                if is_match: 
                    total += item["hours"]
                
    return total

def get_andpad_breakdown(staff_name, current_project, project_number="", aliases=None, ignored_keys=None):
    parsed_andpad_data = str_st.session_state.get("parsed_andpad_data", {})
    if not parsed_andpad_data: 
        return 0.0, []
    
    aliases = aliases or []
    ignored_keys = ignored_keys or []
    
    cache_key = f"bd_{staff_name}_{current_project}_{project_number}_{','.join(aliases)}_{','.join(ignored_keys)}"
    
    # 💡 エラー防止: キャッシュ用の箱が未作成なら作る
    if "andpad_breakdown_cache" not in str_st.session_state:
        str_st.session_state.andpad_breakdown_cache = {}
        
    if cache_key in str_st.session_state.andpad_breakdown_cache:
        return str_st.session_state.andpad_breakdown_cache[cache_key]

    safe_staff = re.sub(r'\s+', '', str(staff_name))
    cp = re.sub(r'\s+', '', str(current_project))
    core_db_num = extract_core_project_num(project_number)
    safe_aliases = [re.sub(r'\s+', '', str(a)) for a in aliases if a]

    total = 0.0
    records = []
    for excel_staff, items in parsed_andpad_data.items():
        is_staff_match = False
        if safe_staff in excel_staff or excel_staff in safe_staff: 
            is_staff_match = True
        elif len(safe_staff) >= 2 and safe_staff[:2] in excel_staff: 
            is_staff_match = True

        if is_staff_match:
            for item in items:
                if item.get("key") in ignored_keys: 
                    continue
                c_proj = item["proj"]
                raw_name = item["raw_name"]
                if not c_proj: 
                    continue
                is_match = False

                core_andpad_num = extract_core_project_num(raw_name)
                if core_db_num and core_andpad_num and core_db_num == core_andpad_num:
                    is_match = True
                elif not is_match:
                    if cp and (cp in c_proj): 
                        is_match = True
                    elif len(c_proj) >= 2 and (c_proj in cp): 
                        is_match = True
                    else:
                        for a in safe_aliases:
                            if a and a in c_proj:
                                is_match = True
                                break

                if is_match:
                    total += item["hours"]
                    records.append({
                        "除外": False,
                        "key": item.get("key"),
                        "日付": item.get("date", "不明"),
                        "ANDPAD打刻名": raw_name,
                        "時間 (h)": item['hours']
                    })
                    
    str_st.session_state.andpad_breakdown_cache[cache_key] = (total, records)
    return total, records