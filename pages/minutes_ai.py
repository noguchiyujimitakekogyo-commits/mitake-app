import os
from datetime import datetime, date
import streamlit as st
import google.generativeai as genai  # 🎤 音声処理用に追加

# ==========================================
# 既存の社内共通ツールを読み込む
# ==========================================
from utils.db_client import db
from utils.ai_engine import call_jarvis_ai

def generate_structured_minutes(raw_text: str, project_name: str) -> str:
    """既存のJARVIS機能を使って要約を実行する"""
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    
    sys_prompt = """あなたは店舗設計・内装施工管理のプロフェッショナルなアシスタントです。
以下の打ち合わせメモから、後から「あの時どう判断したか」を正確に振り返られるように要点を整理してください。
【整理のルール】:
1. 決定事項 (Decisions)
2. 保留・現場リスク (Risks)
3. 次回アクション・TODO (Tasks)"""
    
    user_query = f"【案件・物件名】: {project_name}\n\n【打ち合わせメモ】:\n{raw_text}"
    return call_jarvis_ai(sys_prompt, user_query, model_choice="Gemini 3.6 Flash", gemini_api_key=GEMINI_API_KEY)
    
def transcribe_audio_with_gemini(audio_bytes):
    """Gemini APIを使って音声データを文字起こしする"""
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 音声認識に強いGemini 1.5モデルを使用
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = "この音声の内容を正確に文字起こししてください。話者の区別などは不要で、テキストのみを出力してください。ノイズや無音部分は無視してください。"
    
    try:
        response = model.generate_content([
            prompt,
            {"mime_type": "audio/wav", "data": audio_bytes}
        ])
        return response.text
    except Exception as e:
        return f"文字起こしエラー: {e}"

def fetch_past_minutes():
    """Firestoreから過去の議事録を取得"""
    docs = db.collection("minutes").stream()
    m_list = [doc.to_dict() for doc in docs]
    # 日付の新しい順に並び替え
    m_list.sort(key=lambda x: x.get("meeting_date", ""), reverse=True)
    return m_list

def render_minutes_ai_view():
    st.markdown('<div class="section-title">🧠 AI議事録アシスタント</div>', unsafe_allow_html=True)

    # 📝 入力テキストの状態管理（ファイルや音声からの自動入力用）
    if "input_raw_text" not in st.session_state:
        st.session_state["input_raw_text"] = ""
    if "last_uploaded_file" not in st.session_state:
        st.session_state["last_uploaded_file"] = None
    if "last_audio_data" not in st.session_state:
        st.session_state["last_audio_data"] = None

    tab_create, tab_history = st.tabs(["📝 新規議事録の作成・要約", "📁 過去の議事録一覧"])

    # ----------------------------------------
    # タブ1: 新規作成・要約
    # ----------------------------------------
    with tab_create:
        col1, col2 = st.columns([2, 1])
        with col1: 
            project_name = st.text_input("案件名 / 物件名", placeholder="例: 渋谷カフェ新装工事")
        with col2: 
            meeting_date = st.date_input("打ち合わせ日", value=date.today())

        st.markdown("##### 📥 データの自動読み込み")
        col_file, col_audio = st.columns(2)
        
        # ① テキストファイルのドラッグ＆ドロップ機能
        with col_file:
            uploaded_file = st.file_uploader("📄 テキストファイルをドロップ", type=["txt", "md", "csv"])
            if uploaded_file is not None and uploaded_file.name != st.session_state["last_uploaded_file"]:
                try:
                    file_text = uploaded_file.read().decode("utf-8")
                    if st.session_state["input_raw_text"]:
                        st.session_state["input_raw_text"] += f"\n\n--- 📄 ファイル読込 ({uploaded_file.name}) ---\n{file_text}"
                    else:
                        st.session_state["input_raw_text"] = file_text
                    st.session_state["last_uploaded_file"] = uploaded_file.name
                    st.rerun()
                except Exception as e:
                    st.error(f"ファイルの読み込みに失敗しました: {e}")

        # ② 音声の録音と文字起こし機能
        with col_audio:
            audio_data = st.audio_input("🎙 音声を録音して文字起こし")
            if audio_data is not None and audio_data != st.session_state["last_audio_data"]:
                with st.spinner("AIが音声を文字起こし中... (数秒かかります)"):
                    audio_bytes = audio_data.read()
                    transcript = transcribe_audio_with_gemini(audio_bytes)
                    if st.session_state["input_raw_text"]:
                        st.session_state["input_raw_text"] += f"\n\n--- 🎤 音声文字起こし ---\n{transcript}"
                    else:
                        st.session_state["input_raw_text"] = transcript
                    st.session_state["last_audio_data"] = audio_data
                    st.rerun()

        st.markdown("##### 📝 会議・打ち合わせの生テキスト")
        
        # 手入力と自動入力のデータを同期する
        def update_raw_text():
            st.session_state["input_raw_text"] = st.session_state["text_area_widget"]

        raw_text = st.text_area(
            "ファイルや音声から読み込んだ内容、または直接メモを入力", 
            value=st.session_state["input_raw_text"],
            height=180, 
            key="text_area_widget",
            on_change=update_raw_text
        )

        if st.button("🚀 AI要約・構造化を実行", type="primary"):
            if not project_name:
                st.warning("案件名を入力してください。")
            elif not raw_text.strip():
                st.warning("打ち合わせテキストを入力してください。")
            else:
                with st.spinner("JARVISが議事録を構造化中..."):
                    summary = generate_structured_minutes(raw_text, project_name)
                    st.session_state["last_summary"] = summary
                    st.session_state["last_project"] = project_name
                    st.session_state["last_date"] = str(meeting_date)
                    st.session_state["last_raw_text"] = raw_text

        # 生成結果のプレビュー & 保存
        if "last_summary" in st.session_state:
            st.markdown("### 📋 AI要約プレビュー")
            st.markdown(st.session_state["last_summary"])

            if st.button("💾 この議事録をデータベースに保存する"):
                new_doc = {
                    "project_name": st.session_state["last_project"],
                    "meeting_date": st.session_state["last_date"],
                    "raw_text": st.session_state["last_raw_text"],
                    "summary": st.session_state["last_summary"],
                    "created_at": datetime.now().isoformat(),
                }
                with st.spinner("Firestoreへ保存中..."):
                    db.collection("minutes").add(new_doc)
                    st.success("✅ 議事録を保存しました！")
                    del st.session_state["last_summary"]
                    # 保存後にテキスト欄をリセット
                    st.session_state["input_raw_text"] = ""
                    st.session_state["last_uploaded_file"] = None
                    st.session_state["last_audio_data"] = None
                    st.rerun()

    # ----------------------------------------
    # タブ2: 過去ログ一覧・「あの時」を振り返る
    # ----------------------------------------
    with tab_history:
        st.subheader("過去の議事録一覧")
        search_query = st.text_input("🔍 案件名やキーワードで検索", placeholder="例: 配管、厨房機器、渋谷...")
        
        try:
            minutes_list = fetch_past_minutes()
        except Exception as e:
            st.error(f"データの取得に失敗しました: {e}")
            minutes_list = []
        
        if search_query:
            minutes_list = [m for m in minutes_list if search_query.lower() in m.get("project_name", "").lower() or search_query.lower() in m.get("summary", "").lower()]

        if not minutes_list:
            st.info("該当する議事録がありません。")
        else:
            for item in minutes_list:
                title = f"📅 {item.get('meeting_date', '日付不明')} ｜ 🏢 {item.get('project_name', '案件名なし')}"
                with st.expander(title):
                    st.markdown("#### 【AI構造化サマリー】")
                    st.markdown(item.get("summary", "要約なし"))
                    with st.popover("元の生テキストを確認"):
                        st.text(item.get("raw_text", "記録なし"))

# 実行（テスト時用）
if __name__ == "__main__":
    render_minutes_ai_view()