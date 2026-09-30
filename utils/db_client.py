import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json
from datetime import datetime

# --- Firestoreの初期化（秘密鍵完全クリーンアップ版） ---
if not firebase_admin._apps:
    try:
        # Secrets全体を辞書として安全に取得
        key_dict = dict(st.secrets)
        
        # ローカル環境のファイルがある場合はそちらを優先
        try:
            with open("serviceAccountKey.json", "r", encoding="utf-8") as f:
                key_dict = json.load(f)
        except Exception:
            pass

        # 秘密鍵（private_key）のフォーマットを徹底的に自動クリーンアップする
        if "private_key" in key_dict:
            pk = str(key_dict["private_key"]).strip()
            
            # 前後の不要なダブルクォートやシングルクォートを完全に削ぎ落とす
            while (pk.startswith('"') and pk.endswith('"')) or (pk.startswith("'") and pk.endswith("'")):
                pk = pk[1:-1].strip()
                
            # リテラルの "\\n" または実態の改行を安全に整える
            pk = pk.replace("\\n", "\n")
            
            # BEGIN と END の間を正しい改行構成に再構築
            if "BEGIN PRIVATE KEY" in pk and "END PRIVATE KEY" in pk:
                # 中身の文字列を取り出して綺麗に並べ直す
                body = pk.replace("-----BEGIN PRIVATE KEY-----", "")
                body = body.replace("-----END PRIVATE KEY-----", "")
                # 空白や改行をすべて一度除去
                body = "".join(body.split())
                # 64文字ごとに綺麗に改行を入れる（標準的なPEM形式）
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