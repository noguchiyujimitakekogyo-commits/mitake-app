import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json
from datetime import datetime

# --- Firestoreの初期化（鍵のゴミ自動排除・完全無敵版） ---
if not firebase_admin._apps:
    try:
        fb = st.secrets["firebase"]
        
        # 1. 改行文字のエスケープを正常な改行に復元
        raw_key = fb["private_key"].replace("\\n", "\n")
        
        # 2. 鍵の前後に付着した見えないゴミ（extra dataエラーの原因）を物理的に切り落とす
        start_idx = raw_key.find("-----BEGIN PRIVATE KEY-----")
        end_idx = raw_key.find("-----END PRIVATE KEY-----")
        
        if start_idx != -1 and end_idx != -1:
            # 純粋な鍵ブロックのみを抽出（余分な空白や引用符を完全に排除）
            fixed_private_key = raw_key[start_idx : end_idx + len("-----END PRIVATE KEY-----")]
        else:
            fixed_private_key = raw_key

        key_dict = {
            "type": "service_account",
            "project_id": fb.get("project_id", "mitake-system"),
            "private_key_id": fb.get("private_key_id", ""),
            "private_key": fixed_private_key,
            "client_email": fb.get("client_email", "firebase-adminsdk-fbsvc@mitake-system.iam.gserviceaccount.com"),
            "client_id": fb.get("client_id", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40mitake-system.iam.gserviceaccount.com",
            "universe_domain": "googleapis.com"
        }

        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase初期化エラー: {e}")
        raise e

db = firestore.client()

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

def load_projects():
    year_to_term = {"2022年": "53期", "2023年": "54期", "2024年": "55期", "2025年": "56期", "2026年": "57期", "2027年": "58期", "2028年": "59期", "2029年": "60期", "2030年": "61期"}
    valid_data = {}
    try:
        docs = db.collection("projects").stream()
        for doc in docs:
            p_name = doc.id
            p_data = doc.to_dict()
            if not isinstance(p_data, dict): continue
            if "project_number" not in p_data: p_data["project_number"] = ""
            if "client_name" not in p_data: p_data["client_name"] = "未設定"
            if "project_month" not in p_data: p_data["project_month"] = "9月"
            if "status" not in p_data: p_data["status"] = "進行中"
            if "sales_rep" not in p_data: p_data["sales_rep"] = "" 
            if "受注金額" not in p_data: p_data["受注金額"] = 0
            if "target_hours" not in p_data: p_data["target_hours"] = 0.0 
            if "progress_rate" not in p_data: p_data["progress_rate"] = 100.0
            if "aliases" not in p_data: p_data["aliases"] = []
            if "ignored_andpad_keys" not in p_data: p_data["ignored_andpad_keys"] = []
            if "meeting_memo" not in p_data: p_data["meeting_memo"] = ""
            if "andpad_url" not in p_data: p_data["andpad_url"] = "" 
            if "obsidian_url" not in p_data: p_data["obsidian_url"] = ""
            if "estimate_memo" not in p_data: p_data["estimate_memo"] = "" 
            if "estimate_file" not in p_data: p_data["estimate_file"] = "" 
            if "project_year" not in p_data: p_data["project_year"] = "57期"
            elif p_data["project_year"] in year_to_term: p_data["project_year"] = year_to_term[p_data["project_year"]]
            valid_data[p_name] = p_data
    except Exception as e: print(f"Firestore読み込みエラー: {e}")
    if not valid_data: valid_data = {"テスト物件": get_default_project_data()}
    return valid_data

def save_project_to_db(p_name, p_data):
    db.collection("projects").document(p_name).set(p_data)

def convert_firestore_types(data):
    if isinstance(data, dict):
        return {k: convert_firestore_types(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_firestore_types(i) for i in data]
    elif hasattr(data, "timestamp"):
        return data.isoformat()
    else:
        return data

def get_backup_json(db, collection_name):
    docs = db.collection(collection_name).stream()
    backup_data = []
    for doc in docs:
        doc_dict = doc.to_dict()
        doc_dict["_doc_id"] = doc.id
        backup_data.append(convert_firestore_types(doc_dict))
    
    if not backup_data:
        return None
    return json.dumps(backup_data, ensure_ascii=False, indent=2)