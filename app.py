import streamlit as st

st.set_page_config(page_title="MITAKE 管理システム", layout="wide")

import pandas as pd
import altair as alt
import base64
import os
import json
import re
import datetime
import urllib.parse
import shutil

from views.dashboard import render_dashboard
from views.budget import render_budget
from views.ai_merge import render_ai_merge
from utils.data_parser import (
    backup_uploaded_file, safe_num, safe_extract_float, get_val, 
    extract_core_project_num, calc_hours_from_time_str, 
    parse_single_andpad_excel, get_accumulated_andpad_dict, 
    parse_sales_calc_data, parse_payment_data, get_default_project_data
)

# --- 自作モジュールのインポート ---
from utils.ai_engine import call_jarvis_ai
from utils.db_client import db, load_projects, save_project_to_db
from utils.andpad_parser import (
    ANDPAD_ACC_DIR, 
    get_accumulated_files_tuple, 
    get_hours_from_andpad,
    get_andpad_breakdown
)

# 🔽 AI・画像処理用ライブラリ
import google.generativeai as genai
from PIL import Image, ImageEnhance

# 🔽 ローカルAI (Ollama)
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from config import all_staff_list, CATEGORY_LIST, YEAR_LIST, MONTH_LIST, FULL_DETAIL_A, FULL_DETAIL_B, FULL_DETAIL_C, FULL_DETAIL_D

# --- Gemini APIの設定 ---
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
else:
    GEMINI_API_KEY = "YOUR_API_KEY"

# ==========================================
# 💡 【デザイン】ウルトラ・ミニマルCSS ＆ 点滅エフェクト
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #FFFFFF; }
    html, body, [class*="css"] { 
        font-size: 14px !important; 
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important; 
        color: #37352f !important;
        overflow-x: hidden !important; 
    }
    
    .block-container { 
        padding-top: 2rem !important; 
        padding-bottom: 5rem !important; 
        padding-left: 1.5rem !important; 
        padding-right: 1.5rem !important; 
        max-width: 98% !important; 
    }

    /* サイドバー */
    [data-testid="stSidebar"] { background-color: #F7F6F3; border-right: 1px solid #E9E9E7; }
    [data-testid="stSidebar"] * { color: #37352f !important; }

    /* コンテナ（カードの枠線） */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF;
        border: 1px solid #E9E9E7 !important;
        border-radius: 6px !important;
        box-shadow: rgba(15, 15, 15, 0.05) 0px 0px 0px 1px, rgba(15, 15, 15, 0.1) 0px 2px 4px !important;
        padding: 1.2rem !important;
        margin-bottom: 1.2rem !important;
    }

    /* ボタン */
    .stButton>button {
        border-radius: 4px; border: 1px solid #E9E9E7; background-color: #FFFFFF; color: #37352F; font-weight: 500; transition: background-color 0.1s;
        box-shadow: rgba(15, 15, 15, 0.05) 0px 1px 2px;
    }
    .stButton>button[kind="primary"] {
        background-color: #2383E2; color: #FFFFFF; border: none;
    }
    .stButton>button:hover { background-color: #F7F6F3; color: #37352F; }
    .stButton>button[kind="primary"]:hover { background-color: #0077D4; color: #FFFFFF; }

    /* メトリクス（数字） */
    [data-testid="stMetricValue"] { font-size: 26px !important; font-weight: 600 !important; color: #37352F !important; }
    [data-testid="stMetricLabel"] { font-size: 13px !important; color: #787774 !important; font-weight: 500 !important; }

    /* メモ・数式ボックス */
    .formula-box {
        background-color: #F7F6F3; padding: 12px 18px; border-radius: 4px; border-left: 4px solid #DFDEDC;
        margin-bottom: 12px; color: #37352F; font-family: monospace; font-size: 13px;
    }

    h1, h2, h3, h4 { color: #37352F !important; font-weight: 600 !important; letter-spacing: -0.01em; }
    .section-title { font-size: 28px; font-weight: bold; color: #1a1a1a; margin-bottom: 1.5rem; }

    @keyframes blink-red {
        0%, 100% { color: #e53e3e; opacity: 1; }
        50% { opacity: 0.1; }
    }
    .blink-text {
        animation: blink-red 1.2s infinite;
        font-weight: 700 !important;
        color: #e53e3e !important;
    }
    @keyframes blink-bg {
        0%, 100% { background-color: #fff5f5; border: 2px solid #e53e3e; box-shadow: 0 0 8px rgba(229, 62, 62, 0.4); }
        50% { background-color: #ffffff; border: 2px solid #fc8181; box-shadow: none; }
    }
    .blink-box {
        animation: blink-bg 1.2s infinite;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 📊 データ抽出・パース用ヘルパー関数群
# ==========================================

# ==========================================
# 💡 データの読み込み・初期化（後半）
# ==========================================
if "projects_db" not in st.session_state:
    with st.spinner("☁️ データベースから最新の物件情報を読み込んでいます..."):
        st.session_state.projects_db = load_projects()

projects_db = st.session_state.projects_db

try:
    df_contractor_master = pd.read_csv("data_contractor.csv", encoding="utf-8")
except Exception:
    try:
        df_contractor_master = pd.read_csv("data_contractor.csv", encoding="shift_jis")
    except Exception:
        df_contractor_master = pd.DataFrame(columns=["業者管理番号", "業者・工種名"]) 

if "db_cleaned" not in st.session_state:
    keys_to_delete = [k for k, v in projects_db.items() if isinstance(v, dict) and ("合計" in str(v.get("client_name", "")) or v.get("project_month", "") == "通期合計" or v.get("client_name", "") == "未設定 (自動追加)")]
    for k in keys_to_delete: 
        del projects_db[k]
        db.collection("projects").document(k).delete() 
    st.session_state.db_cleaned = True

if "parsed_andpad_data" not in st.session_state:
    files_tuple = get_accumulated_files_tuple()
    st.session_state.parsed_andpad_data = get_accumulated_andpad_dict(files_tuple)

parsed_andpad_data = st.session_state.parsed_andpad_data

if "andpad_hours_cache" not in st.session_state:
    st.session_state.andpad_hours_cache = {}
if "andpad_breakdown_cache" not in st.session_state:
    st.session_state.andpad_breakdown_cache = {}

def get_staff_total_hours(staff_name, target_month):
    if not parsed_andpad_data: return 0.0
    safe_staff = re.sub(r'\s+', '', str(staff_name))
    total = 0.0
    
    m_str = target_month.replace("月", "") if target_month != "通期（全月合計）" else ""
    m_zfill = m_str.zfill(2) if m_str else ""
    
    for excel_staff, items in parsed_andpad_data.items():
        is_staff_match = False
        if safe_staff in excel_staff or excel_staff in safe_staff: is_staff_match = True
        elif len(safe_staff) >= 2 and safe_staff[:2] in excel_staff: is_staff_match = True
        
        if is_staff_match:
            for item in items:
                item_date = str(item.get("date", "")).strip()
                if target_month == "通期（全月合計）":
                    total += item.get("hours", 0.0)
                else:
                    if not item_date or item_date == "不明":
                        continue
                        
                    if f"-{m_zfill}-" in item_date or f"/{m_str}/" in item_date or f"/{m_zfill}/" in item_date or item_date.startswith(f"{m_str}/") or item_date.startswith(f"{m_zfill}/"):
                        total += item.get("hours", 0.0)
    return total

def get_staff_daily_breakdown(staff_name, target_month):
    if not parsed_andpad_data: return []
    safe_staff = re.sub(r'\s+', '', str(staff_name))
    
    m_str = target_month.replace("月", "") if target_month != "通期（全月合計）" else ""
    m_zfill = m_str.zfill(2) if m_str else ""
    
    records = []
    for excel_staff, items in parsed_andpad_data.items():
        is_staff_match = False
        if safe_staff in excel_staff or excel_staff in safe_staff: is_staff_match = True
        elif len(safe_staff) >= 2 and safe_staff[:2] in excel_staff: is_staff_match = True
        
        if is_staff_match:
            for item in items:
                item_date = str(item.get("date", "")).strip()
                hours = item.get("hours", 0.0)
                if hours == 0: continue
                
                is_target_month = False
                if target_month == "通期（全月合計）":
                    is_target_month = True
                else:
                    if not item_date or item_date == "不明":
                        continue
                    if f"-{m_zfill}-" in item_date or f"/{m_str}/" in item_date or f"/{m_zfill}/" in item_date or item_date.startswith(f"{m_str}/") or item_date.startswith(f"{m_zfill}/"):
                        is_target_month = True
                        
                if is_target_month:
                    records.append({
                        "日付": item_date,
                        "打刻名": item.get("raw_name", ""),
                        "工数(h)": hours
                    })
    
    records = sorted(records, key=lambda x: x["日付"])
    return records


# ==========================================
# 🎯 【サイドバーナビゲーション】メニュー構成
# ==========================================
with st.sidebar:
    st.title("MITAKE 管理システム")
    st.markdown("---")
    st.markdown("### ⌕ 共通フィルター")
    global_target_year = st.selectbox("対象の期", YEAR_LIST, index=YEAR_LIST.index("57期") if "57期" in YEAR_LIST else 0, key="global_year")
    global_target_month = st.selectbox("対象の月度", ["通期（全月合計）"] + MONTH_LIST, index=0, key="global_month")

    ai_engine_option = "Gemini 3.6 Flash"  
    
    st.markdown("---")
    st.markdown("### ≡ メニュー")
    selected_menu = st.radio(
        "機能を選択してください",
        [
            "❖ 全社ダッシュボード ＆ 部署別分析",
            "◲ 物件別予算管理・詳細編集",
            "✦ AI自動処理 ＆ 未振分マージ"
        ],
        key="main_menu_nav"
    )
    
    st.markdown("---")
    if st.button("↻ クラウド最新データに更新", use_container_width=True):
        with st.spinner("最新データを取得中..."):
            st.session_state.projects_db = load_projects()
            if "parsed_andpad_data" in st.session_state:
                del st.session_state["parsed_andpad_data"]
            st.session_state.andpad_hours_cache = {}
            st.session_state.andpad_breakdown_cache = {}
        st.rerun()
    st.info("▪ 動作を高速化するため、データは「更新ボタン」を押すまでパソコン内に保持されます。")

# ==========================================
# 🚀 【メイン画面】選択されたメニューのみを描画
# ==========================================

# ------------------------------------------
# [1] ❖ 全社ダッシュボード ＆ 部署別分析
# ------------------------------------------
if selected_menu == "❖ 全社ダッシュボード ＆ 部署別分析":
    render_dashboard(
        projects_db=projects_db,
        parsed_andpad_data=parsed_andpad_data,
        global_target_year=global_target_year,
        global_target_month=global_target_month,
        ai_engine_option=ai_engine_option,
        GEMINI_API_KEY=GEMINI_API_KEY,
        get_staff_total_hours=get_staff_total_hours,
        get_staff_daily_breakdown=get_staff_daily_breakdown
    )

# ==========================================
# [2] ◲ 物件別予算管理・詳細編集セクション
# ==========================================
elif selected_menu == "◲ 物件別予算管理・詳細編集":
    render_budget(
        projects_db=projects_db,
        df_contractor_master=df_contractor_master,
        ai_engine_option=ai_engine_option,
        GEMINI_API_KEY=GEMINI_API_KEY
    )

# ------------------------------------------
# [3] ✦ AI自動処理 ＆ 未振分マージ
# ------------------------------------------
elif selected_menu == "✦ AI自動処理 ＆ 未振分マージ":
    render_ai_merge(
        projects_db=projects_db,
        parsed_andpad_data=parsed_andpad_data,
        GEMINI_API_KEY=GEMINI_API_KEY,
        ai_engine_option=ai_engine_option,
        parse_single_andpad_excel=parse_single_andpad_excel,
        backup_uploaded_file=backup_uploaded_file,
        parse_sales_calc_data=parse_sales_calc_data,
        parse_payment_data=parse_payment_data,
        extract_core_project_num=extract_core_project_num,
        get_default_project_data=get_default_project_data,
        safe_num=safe_num
    )
    
# ==========================================
# 💾 サイドバー：データバックアップ機能
# ==========================================
def convert_firestore_types(data):
    """Firestoreの特殊なデータ型をJSON用に変換するヘルパー関数"""
    if isinstance(data, dict):
        return {k: convert_firestore_types(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_firestore_types(i) for i in data]
    elif hasattr(data, "timestamp"):
        return data.isoformat()
    else:
        return data

with st.sidebar:
    st.divider()
    st.markdown("### 💾 データバックアップ")
    
    # 対象コレクションの選択
    collections = ["minutes", "projects"]
    target_col = st.selectbox("バックアップ対象", collections, key="backup_select")
    
    # ダウンロード準備ボタン
    if st.button("データ取得・準備", key="btn_prepare_backup"):
        with st.spinner("取得中..."):
            try:
                # Firestoreからデータ取得
                docs = db.collection(target_col).stream()
                backup_data = []
                for doc in docs:
                    doc_dict = doc.to_dict()
                    doc_dict["_doc_id"] = doc.id
                    backup_data.append(convert_firestore_types(doc_dict))
                
                if backup_data:
                    # JSON文字列に変換
                    json_str = json.dumps(backup_data, ensure_ascii=False, indent=2)
                    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M")
                    
                    st.success("準備完了！")
                    st.download_button(
                        label=f"📥 {target_col} を保存",
                        data=json_str,
                        file_name=f"backup_{target_col}_{current_time}.json",
                        mime="application/json",
                        type="primary"
                    )
                else:
                    st.warning("データがありません")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")