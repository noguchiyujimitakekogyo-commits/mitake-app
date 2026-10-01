import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json
from datetime import datetime

# --- Firestoreの初期化（明示的キーマップ＆完全堅牢版） ---
if not firebase_admin._apps:
    try:
        # ローカル環境のファイルがある場合はそちらを最優先
        try:
            with open("serviceAccountKey.json", "r", encoding="utf-8") as f:
                key_dict = json.load(f)
        except Exception:
            # Streamlit Secretsから安全に取得（テーブル形式とフラット形式の両方に対応）
            if "firebase" in st.secrets:
                raw_secret = st.secrets["firebase"]
            else:
                raw_secret = st.secrets

            # 必須のキー項目を明示的にマッピングして作成する
            key_dict = {
                "type": "service_account",
                "project_id": str(raw_secret.get("project_id", "mitake-system")),
                "private_key_id": str(raw_secret.get("private_key_id", "1d46d61fc7d080b80f5ecbadd96c2a61a26f3efb")),
                "private_key": str(raw_secret.get("private_key", "")),
                "client_email": str(raw_secret.get("client_email", "firebase-adminsdk-fbsvc@mitake-system.iam.gserviceaccount.com")),
                "client_id": str(raw_secret.get("client_id", "111355823018768199603")),
                "auth_uri": str(raw_secret.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")),
                "token_uri": str(raw_secret.get("token_uri", "https://oauth2.googleapis.com/token")),
                "auth_provider_x509_cert_url": str(raw_secret.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs")),
                "client_x509_cert_url": str(raw_secret.get("client_x509_cert_url", "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40mitake-system.iam.gserviceaccount.com")),
                "universe_domain": str(raw_secret.get("universe_domain", "googleapis.com")),
            }

        # 秘密鍵（private_key）のフォーマットを徹底的にクリーンアップ
        if "private_key" in key_dict:
            pk = key_dict["private_key"].strip()
            while (pk.startswith('"') and pk.endswith('"')) or (pk.startswith("'") and pk.endswith("'")):
                pk = pk[1:-1].strip()
            pk = pk.replace("\\n", "\n")
            
            if "BEGIN PRIVATE KEY" in pk and "END PRIVATE KEY" in pk:
                body = pk.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
                body = "".join(body.split())
                chunks = [body[i:i+64] for i in range(0, len(body), 64)]
                pk = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(chunks) + "\n-----END PRIVATE KEY-----\n"
            key_dict["private_key"] = pk

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
    """DBからデータを取得しJSON文字列を返す"""
    docs = db.collection(collection_name).stream()
    backup_data = []
    for doc in docs:
        doc_dict = doc.to_dict()
        doc_dict["_doc_id"] = doc.id
        backup_data.append(convert_firestore_types(doc_dict))
    
    if not backup_data:
        return None
    return json.dumps(backup_data, ensure_ascii=False, indent=2)