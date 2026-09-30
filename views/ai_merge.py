# views/ai_merge.py

import streamlit as st
import pandas as pd
import os
import json
import re
import datetime
import google.generativeai as genai
from PIL import Image, ImageEnhance

# 必要な裏方ツールの読み込み
from utils.db_client import save_project_to_db
from utils.andpad_parser import ANDPAD_ACC_DIR
from utils.ai_engine import call_jarvis_ai
from config import YEAR_LIST, MONTH_LIST

def render_ai_merge(
    projects_db, 
    parsed_andpad_data, 
    GEMINI_API_KEY, 
    ai_engine_option,
    parse_single_andpad_excel, 
    backup_uploaded_file, 
    parse_sales_calc_data, 
    parse_payment_data, 
    extract_core_project_num, 
    get_default_project_data, 
    safe_num
):
    st.markdown('<div class="section-title">✦ AI書類自動処理 ＆ データ取込</div>', unsafe_allow_html=True)
    st.markdown("書類やExcel/CSVファイルをアップロードして、システムに自動で数値を読み込ませます。")

    if "ai_result" not in st.session_state: st.session_state.ai_result = None

    with st.container(border=True):
        st.markdown("### Step 1: 書類の選択とアップロード")
        col_doc, col_input = st.columns(2)
        with col_doc: 
            doc_type = st.radio("読み込む書類の種類", [
                "営業計算書（AI読取無し - PDF / 画像プレビュー用）", 
                "営業計算書（AI読取 - PDF / 画像）", 
                "営業計算書（Excel / CSV データ取込）", 
                "支払実績データ（AI読取 - PDF / 画像）",
                "支払実績データ（Excel / CSV データ取込）",
                "発注書（AI読取 - PDF / 画像）", 
                "請求書等（AI読取 - PDF / 画像）", 
                "会議議事録（AI読取 - PDF / 画像）",
                "会議議事録（Obsidian / Markdown 取込）",
                "担当表(ANDPAD Excel)"
            ], key="ai_doc_type_v_sidebar")
            
        with col_input: 
            if doc_type in ["担当表(ANDPAD Excel)", "営業計算書（Excel / CSV データ取込）", "支払実績データ（Excel / CSV データ取込）", "会議議事録（Obsidian / Markdown 取込）", "営業計算書（AI読取無し - PDF / 画像プレビュー用）"]:
                st.info("データは「ファイルから選ぶ」のみ対応しています。")
                input_type = "ファイルから選ぶ"
            else:
                input_type = st.radio("入力方法", ["ファイル(PDF/画像)から選ぶ", "カメラで撮影する"], key="ai_input_type_v_sidebar")

        if doc_type == "担当表(ANDPAD Excel)":
            excel_file = st.file_uploader("担当表Excel (.xlsx, .xls) を選択", type=["xlsx", "xls"], key="ai_excel_uploader_v_sidebar")
            if excel_file is not None:
                with st.spinner("ファイルを解析中..."):
                    preview_data = parse_single_andpad_excel(excel_file)
                
                if preview_data:
                    st.info(f"💡 {len(preview_data)} 名分の担当表データを抽出しました。内容を確認してシステムに取り込んでください。")
                    
                    preview_rows = []
                    for staff, items in preview_data.items():
                        total_h = sum(i["hours"] for i in items)
                        preview_rows.append({"担当者名": staff, "抽出データ件数": len(items), "合計工数 (h)": total_h})
                    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
                    
                    if st.button("✓ この内容でシステムにデータを取り込む", type="primary", use_container_width=True, key="andpad_reflect_v_sidebar"):
                        os.makedirs(ANDPAD_ACC_DIR, exist_ok=True)
                        current_ymd = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        acc_path = os.path.join(ANDPAD_ACC_DIR, f"andpad_{current_ymd}.xlsx")
                        excel_file.seek(0)
                        with open(acc_path, "wb") as f: f.write(excel_file.read())
                        
                        if "parsed_andpad_data" in st.session_state:
                            del st.session_state.parsed_andpad_data
                        st.session_state.andpad_hours_cache = {}
                        st.session_state.andpad_breakdown_cache = {}
                        
                        backup_uploaded_file(excel_file.getvalue(), excel_file.name, prefix="attendance")
                        st.success(f"✓ 担当表データの取り込みが完了しました！全体に反映されました。")
                        st.rerun()
                else:
                    st.warning("データが抽出できませんでした。ファイルの形式を確認してください。")

        elif doc_type == "営業計算書（AI読取無し - PDF / 画像プレビュー用）":
            preview_file = st.file_uploader("営業計算書のファイル(.pdf, .jpg, .png, .xlsx 等)を選択", type=["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "csv"], key="preview_uploader_v_sidebar")
            if preview_file is not None:
                if st.button("✓ このファイルをプレビュー用として登録画面へ進む", type="primary", use_container_width=True, key="preview_read_v_sidebar"):
                    file_bytes = preview_file.read()
                    file_name = preview_file.name
                    st.session_state.ai_result = {"is_preview_only": True, "file_name": file_name, "file_bytes": file_bytes}
                    st.success("✓ ファイルを読み込みました！下部のStep3に進んでください。")

        elif doc_type in ["営業計算書（Excel / CSV データ取込）", "支払実績データ（Excel / CSV データ取込）"]:
            calc_data_file = st.file_uploader("該当データのExcel(.xlsx, .xls)またはCSVを選択", type=["xlsx", "xls", "csv"], key="calc_data_uploader_v_sidebar")
            if calc_data_file is not None:
                if st.button("✓ データを読み込む", type="primary", use_container_width=True, key="calc_read_v_sidebar"):
                    with st.spinner("データを読み込んでいます..."):
                        try:
                            if calc_data_file.name.endswith(".csv"):
                                try: df_data = pd.read_csv(calc_data_file, header=None, encoding='utf-8')
                                except:
                                    calc_data_file.seek(0)
                                    df_data = pd.read_csv(calc_data_file, header=None, encoding='shift_jis')
                            else:
                                df_data = pd.read_excel(calc_data_file, sheet_name=0, header=None)
                                
                            if doc_type == "営業計算書（Excel / CSV データ取込）":
                                extracted = parse_sales_calc_data(df_data, mode="budget")
                            else:
                                extracted = parse_payment_data(df_data)
                                
                            st.session_state.ai_result = extracted
                            st.success("✓ データ抽出が完了しました！下部のStep3に進んでください。")
                        except Exception as e: st.error(f"データの読み込みに失敗しました: {e}")

        elif doc_type == "会議議事録（Obsidian / Markdown 取込）":
            md_file = st.file_uploader("Obsidianのマークダウン(.md)またはテキストを選択", type=["md", "txt"], key="ai_md_uploader_v_sidebar")
            if md_file is not None:
                st.info("▪ テキストデータを読み込みました。下のボタンを押してAIに要約を依頼してください。")
                if st.button("✦ AIで議事録を要約して抽出する", type="primary", use_container_width=True, key="ai_extract_md_btn_v_sidebar"):
                    if GEMINI_API_KEY == "ここに取得したAPIキーを貼り付けてください" or GEMINI_API_KEY == "YOUR_KEY_HERE":
                        st.error("⚠ APIキーが設定されていません。")
                    else:
                        with st.spinner('AIがテキストを解析・要約中...'):
                            try:
                                text_content = md_file.read().decode('utf-8')
                                sys_instruction = "あなたは最高精度の要約AIアシスタントです。提供されたテキストを構造化し、指定されたJSON構造で出力してください。"
                                model = genai.GenerativeModel('gemini-3.6-flash', system_instruction=sys_instruction)
                                
                                prompt = f"""
                                以下の会議議事録（Markdownテキスト）を読み込み、要点を整理して以下のJSONフォーマットで完全に抽出してください：
                                {{
                                    "会議議事録": "ここに議事録の要約（決定事項、課題、スケジュール、懸念点など）を詳細かつ簡潔にテキストとして抽出してください。改行も保持してください。"
                                }}
                                
                                【議事録テキスト】
                                {text_content}
                                """
                                
                                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json", "temperature": 0.0})
                                try:
                                    st.session_state.ai_result = json.loads(response.text)
                                    st.success("✓ AIによる要約が完了しました！下部のStep3に進んでください。")
                                except:
                                    match = re.search(r'\{.*\}', response.text, re.DOTALL)
                                    if match: st.session_state.ai_result = json.loads(match.group())
                                    else: st.error("解析に失敗しました。")
                            except Exception as e: st.error(f"エラー: {e}")

        elif doc_type not in ["担当表(ANDPAD Excel)"]:
            ai_image_file = None
            if input_type == "ファイル(PDF/画像)から選ぶ": 
                ai_image_file = st.file_uploader("画像（jpg, png）または PDF", type=["jpg", "jpeg", "png", "pdf"], key="ai_file_uploader_v_sidebar")
            else: 
                ai_image_file = st.camera_input("書類を撮影", key="ai_camera_input_v_sidebar")

    if doc_type not in ["担当表(ANDPAD Excel)", "営業計算書（Excel / CSV データ取込）", "支払実績データ（Excel / CSV データ取込）", "会議議事録（Obsidian / Markdown 取込）", "営業計算書（AI読取無し - PDF / 画像プレビュー用）"] and 'ai_image_file' in locals() and ai_image_file is not None:
        with st.container(border=True):
            st.markdown("### Step 2: AI解析の実行")
            if input_type == "ファイル(PDF/画像)から選ぶ" and ai_image_file.name.lower().endswith('.pdf'):
                try:
                    import fitz
                    doc = fitz.open(stream=ai_image_file.read(), filetype="pdf")
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=180)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                except ImportError:
                    st.error("🚨 PDF読み込み機能を使うためのライブラリが不足しています。")
                    st.stop()
            else: img = Image.open(ai_image_file).convert('RGB')
            
            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            enhancer = ImageEnhance.Contrast(img)
            img_processed = enhancer.enhance(1.2)
            st.image(img_processed, caption="AIが解析する画像", width=400)
            
            if st.button("✦ AIで情報を自動抽出する", type="primary", use_container_width=True, key="ai_extract_btn_v_sidebar"):
                if GEMINI_API_KEY == "ここに取得したAPIキーを貼り付けてください" or GEMINI_API_KEY == "YOUR_KEY_HERE":
                    st.error("⚠ APIキーが設定されていません。")
                else:
                    with st.spinner('AIが高精度解析中...'):
                        try:
                            sys_instruction = """
                            あなたは最高精度の経理AIアシスタントです。
                            画像内の文字、表、数字を極めて高い精度で正確に解析し、指定されたJSON構造のみを出力してください。
                            【厳守事項】
                            1. 「工種」と「業者名」が上下2段に分かれている場合でも、必ず同じブロック内の金額を抽出すること。行ズレを絶対に起こさないでください。
                            2. 全ての業者抽出後、金額が上下の業者とズレていないか自己チェックすること。
                            3. 「小計」「合計」の行は絶対に抽出しないこと。
                            """
                            model = genai.GenerativeModel('gemini-3.6-flash', system_instruction=sys_instruction)
                            
                            if doc_type == "営業計算書（AI読取 - PDF / 画像）":
                                prompt = f"""
                                営業計算書の画像・PDFです。以下のJSONフォーマットで完全に抽出してください：
                                {{
                                    "物件番号": "...", "顧客名": "...", "物件名": "...", "営業担当": "...", "受注金額": 1234567, "月度": "7月",
                                    "分類1": "...", "分類2": "...", "元請_下請": "...",
                                    "目標工数": 0, "工事原価合計": 78500, "労務費": 23500, "売上総利益": 39000, "売上粗利率": 0.33,
                                    "販売管理費": 11750, "営業利益": 5870, "原価＋営業利益": 96120, "実行予算利益": 21370, "実行予算粗利率": 0.18,
                                    "入金スケジュール": [ {{"月度": "7月", "金額": 500000}}, {{"月度": "8月", "金額": 675000}} ],
                                    "材料費リスト": [ {{"会社名": "〇〇建材", "金額": 100000}} ],
                                    "外注費リスト": [ {{"会社名": "〇〇設備", "金額": 250000}} ],
                                    "現場経費リスト": [ {{"会社名": "〇〇リース", "金額": 15000}} ],
                                    "会議議事録": "議事録や打合せメモなどの記載があれば、ここに全文をテキストとして抽出してください。"
                                }}
                                - 受注金額は税抜の「本工事受注金額」を抽出。
                                - 「受注・請求（出来高請求）」などの行や「集金日（出来高）」「〆月」の記載を読み取り、各月の請求・入金予定を『入金スケジュール』として抽出してください。最大3回分程度。
                                - 工事原価合計〜実行予算粗利率などのサマリー項目は、表の右下部分から正確に数値を拾ってください。
                                """
                            elif doc_type == "支払実績データ（AI読取 - PDF / 画像）":
                                prompt = f"""
                                「仕入先別原価推移表」などの実績データから、以下のJSONフォーマットで完全に抽出してください：
                                {{
                                    "物件番号": "56T-2-3006-00", "顧客名": "株式会社OMC", "物件名": "和甘 エキュート大宮店 木札工事", "営業担当": "...", 
                                    "受注金額": 11750, "月度": "7月",
                                    "外注費リスト": [ {{"会社名": "亮美建", "金額": 5500}} ]
                                }}
                                - 業者名（仕入先）と、初めの「原価累計」または「当月の発生金額」を抽出してください。
                                - 「ZZ-JISYA」のような社内経費の行は無視するか、社内管理費として現場経費リストに入れてください。
                                - すべての抽出業者リストは「外注費リスト」として出力してください。
                                """
                            elif doc_type == "会議議事録（AI読取 - PDF / 画像）":
                                prompt = f"""
                                会議議事録や打ち合わせメモの画像・PDFです。以下のJSONフォーマットで完全に抽出してください：
                                {{
                                    "会議議事録": "ここに議事録の全文（決定事項、課題、スケジュールなど）を詳細にテキストとして抽出してください。改行も保持してください。"
                                }}
                                """
                            else:
                                prompt = f"""
                                発注書や請求書の画像・PDFです。以下のJSONフォーマットで完全に抽出してください：
                                {{
                                    "物件名": "...", 
                                    "顧客名": "...", 
                                    "業社・工種名": "...", 
                                    "金額": 150000, 
                                    "工種名": "..."
                                }}
                                - 金額は「税抜きの合計金額」または「発注金額」を抽出してください。
                                - 業社・工種名には、書類の発行元（請求元・受注者）を抽出してください。
                                - 工種名には、「内装工事」「電気工事」「材料費」など、書類の内容から推測できるカテゴリを簡潔に記載してください。
                                """
                            
                            response = model.generate_content([prompt, img_processed], generation_config={"response_mime_type": "application/json", "temperature": 0.0})
                            try:
                                st.session_state.ai_result = json.loads(response.text)
                                st.success("✓ 高精度AIによる読み取りが完了しました！下部のStep3に進んでください。")
                            except:
                                match = re.search(r'\{.*\}', response.text, re.DOTALL)
                                if match: st.session_state.ai_result = json.loads(match.group())
                                else: st.error("解析に失敗しました。")
                        except Exception as e: st.error(f"エラー: {e}")
    
    if st.session_state.ai_result:
        with st.container(border=True):
            st.markdown("### Step 3: 抽出結果の確認と反映")
            data = st.session_state.ai_result
            project_names = [k for k in projects_db.keys() if k != "_SYSTEM_SETTINGS_"]
            
            if data.get("is_preview_only"):
                st.info("↓ 紐付ける物件を選択して反映してください。")
                ai_target_project = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names, key="ai_sel_proj_preview_v_sidebar")
                st.write(f"📂 アップロードされたファイル: **{data['file_name']}**")
                
                if st.button("✓ このファイルを物件に保管する", type="primary", key="ai_btn_preview_v_sidebar"):
                    if ai_target_project != "(選択してください)":
                        os.makedirs("uploaded_images", exist_ok=True)
                        safe_name = "".join([c for c in ai_target_project if c.isalnum() or c in " _-"])
                        ext = data["file_name"].split('.')[-1].lower()
                        file_path = f"uploaded_images/{safe_name}_calc_{datetime.datetime.now().strftime('%H%M%S')}.{ext}"
                        with open(file_path, "wb") as f:
                            f.write(data["file_bytes"])
                        
                        projects_db[ai_target_project]["calc_image"] = file_path
                        save_project_to_db(ai_target_project, projects_db[ai_target_project])
                        st.success(f"✓ {ai_target_project} にプレビュー用ファイルを保管しました！")
                        st.session_state.ai_result = None
                        st.rerun()
                    else: st.error("物件名を選択してください。")
            
            elif doc_type in ["会議議事録（AI読取 - PDF / 画像）", "会議議事録（Obsidian / Markdown 取込）"]:
                st.info("↓ 以下の抽出された項目を確認・修正して反映してください。")
                ai_target_project = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names, key="ai_sel_proj_giji_v_sidebar")
                confirm_memo = st.text_area("抽出された議事録内容", value=data.get("会議議事録", ""), height=300, key="ai_memo_giji_v_sidebar")
                
                if st.button("✓ この議事録を物件に反映する", type="primary", key="ai_btn_giji_v_sidebar"):
                    if ai_target_project != "(選択してください)":
                        if "meeting_memo" not in projects_db[ai_target_project]:
                            projects_db[ai_target_project]["meeting_memo"] = ""
                        update_msg = f"【{datetime.datetime.now().strftime('%Y/%m/%d %H:%M')} AI議事録取込】\n{confirm_memo}"
                        projects_db[ai_target_project]["meeting_memo"] = update_msg + "\n\n" + str(projects_db[ai_target_project].get("meeting_memo", ""))
                        save_project_to_db(ai_target_project, projects_db[ai_target_project])
                        st.success(f"✓ {ai_target_project} の「会議議事録」にデータを反映しました！")
                        st.session_state.ai_result = None
                        st.rerun()
                    else: st.error("物件名を選択してください。")
                    
            elif doc_type in ["営業計算書（AI読取 - PDF / 画像）", "営業計算書（Excel / CSV データ取込）", "支払実績データ（Excel / CSV データ取込）", "支払実績データ（AI読取 - PDF / 画像）"]:
                st.info("↓ 以下の抽出された項目を確認・修正して反映してください。")
                ai_proj_num = data.get("物件番号", "")
                core_ai_num = extract_core_project_num(ai_proj_num)
                
                matched_existing_key = None
                if ai_proj_num:
                    for k, v in projects_db.items():
                        existing_num = str(v.get("project_number", ""))
                        core_existing_num = extract_core_project_num(existing_num)
                        if core_existing_num and core_existing_num == core_ai_num:
                            matched_existing_key = k
                            break
                        elif existing_num.strip() == str(ai_proj_num).strip() and existing_num.strip() != "":
                            matched_existing_key = k
                            break
                
                if matched_existing_key:
                    st.success(f"🔗 **既存物件（{matched_existing_key}）と一致しました！**\nこのまま反映すると、既存の予算データに今回の実績がマージされます。")
                    confirm_proj = st.text_input("対象物件名（一致した既存物件が自動セットされています）", value=matched_existing_key, key="ai_proj_name_v_sidebar")
                else:
                    confirm_proj = st.text_input("対象物件名", value=data.get("物件名", ""), key="ai_proj_name_v_sidebar")
                
                col_client, col_num, col_rep = st.columns(3)
                with col_client: confirm_client = st.text_input("顧客名", value=data.get("顧客名", ""), key="ai_client_name_v_sidebar")
                with col_num: confirm_num = st.text_input("物件番号", value=ai_proj_num, key="ai_proj_num_v_sidebar")
                with col_rep: confirm_sales_rep = st.text_input("営業担当", value=data.get("営業担当", ""), key="ai_sales_rep_v_sidebar")
                
                guessed_term = "57期"
                if confirm_num and confirm_num[:2].isdigit():
                    term_str = confirm_num[:2] + "期"
                    if term_str in YEAR_LIST: guessed_term = term_str
                        
                confirm_year = st.selectbox("対象の期", YEAR_LIST, index=YEAR_LIST.index(guessed_term), key="ai_proj_year_v_sidebar")
                ai_month = data.get("月度", "9月")
                if ai_month not in MONTH_LIST: ai_month = "9月"
                confirm_month = st.selectbox("月度（売上計上月）", MONTH_LIST, index=MONTH_LIST.index(ai_month), key="ai_proj_month_v_sidebar")
                
                col_amt_1, col_amt_2 = st.columns(2)
                with col_amt_1: confirm_order_amt = st.number_input("受注金額（税抜）", value=int(data.get("受注金額", 0)), key="ai_proj_order_amt_v_sidebar")
                with col_amt_2: confirm_target_hours = st.number_input("目標工数 (予定) [h]", value=float(data.get("目標工数", 0.0)), step=1.0, key="ai_proj_target_hours_v_sidebar")
                
                confirm_meeting_memo = ""
                if doc_type in ["営業計算書（AI読取 - PDF / 画像）", "営業計算書（Excel / CSV データ取込）"]:
                    with st.expander("抽出された計画サマリー（確認用）", expanded=True):
                        c_preview1, c_preview2, c_preview3 = st.columns(3)
                        c_preview1.write(f"**工事原価合計:** ¥ {data.get('工事原価合計', 0):,.0f}")
                        c_preview2.write(f"**売上総利益:** ¥ {data.get('売上総利益', 0):,.0f}")
                        c_preview3.write(f"**実行予算利益:** ¥ {data.get('実行予算利益', 0):,.0f}")
                    if data.get("会議議事録", ""):
                        confirm_meeting_memo = st.text_area("抽出された会議議事録・メモ", value=data.get("会議議事録", ""), height=100, key="ai_proj_meeting_memo_v_sidebar")
                
                st.markdown("#### 抽出された業者・金額リスト")
                extracted_items = []
                for mat_key, category_name in [("材料費リスト", "AI読取(材料費)"), ("外注費リスト", "AI読取(外注費)"), ("現場経費リスト", "AI読取(現場経費)")]:
                    for item in data.get(mat_key, []):
                        name = item.get("会社名", item.get("業者名", ""))
                        if doc_type in ["営業計算書（Excel / CSV データ取込）", "支払実績データ（Excel / CSV データ取込）"]:
                            budget = item.get("実行予算", 0)
                            payment = item.get("支払金額", 0)
                        elif doc_type == "支払実績データ（AI読取 - PDF / 画像）":
                            budget = 0
                            payment = item.get("金額", 0)
                        else:
                            amt = item.get("金額", 0)
                            budget = amt
                            payment = 0
                        if name and str(name).lower() != "none" and str(name).strip() != "":
                            extracted_items.append({"工種名": category_name, "業者・工種名": str(name).strip(), "実行予算": safe_num(budget), "支払金額": safe_num(payment)})

                df_extracted = pd.DataFrame(extracted_items) if extracted_items else pd.DataFrame(columns=["工種名", "業者・工種名", "実行予算", "支払金額"])
                edited_df = st.data_editor(df_extracted, num_rows="dynamic", use_container_width=True, key="ai_multi_items_ed_v_sidebar")
                
                if st.button("✓ このデータを反映する（新規作成 / 既存とマージ）", type="primary", key="ai_btn_reflect_v_sidebar"):
                    if confirm_proj:
                        target_proj_key = confirm_proj
                        is_matched_by_num = False
                        if confirm_num:
                            core_confirm_num = extract_core_project_num(confirm_num)
                            for k, v in projects_db.items():
                                existing_num = str(v.get("project_number", ""))
                                core_existing_num = extract_core_project_num(existing_num)
                                if core_existing_num and core_existing_num == core_ai_num:
                                    target_proj_key = k
                                    is_matched_by_num = True
                                    break
                                elif existing_num.strip() == str(confirm_num).strip() and existing_num.strip() != "":
                                    target_proj_key = k
                                    is_matched_by_num = True
                                    break
                                    
                        is_new = target_proj_key not in projects_db
                        p_data = get_default_project_data() if is_new else projects_db[target_proj_key]
       
                        if confirm_client: p_data["client_name"] = confirm_client
                        if confirm_num: p_data["project_number"] = confirm_num
                        p_data["project_year"] = confirm_year
                        p_data["project_month"] = confirm_month
                        if confirm_order_amt > 0: p_data["受注金額"] = confirm_order_amt
                        if confirm_target_hours > 0: p_data["target_hours"] = confirm_target_hours
                        p_data["sales_rep"] = confirm_sales_rep 
                        
                        save_project_to_db(confirm_proj, projects_db[confirm_proj] if not is_new else p_data)
                        st.success("完了しました！")
                        st.session_state.ai_result = None 
                        st.rerun()

            elif doc_type == "発注書（AI読取 - PDF / 画像）":
                st.info("↓ 以下の抽出された項目を確認・修正して反映してください。")
                ai_target_project = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names, key="ai_sel_proj_hachu_v_sidebar")
                confirm_client = st.text_input("顧客名", value=data.get("顧客名", ""), key="ai_client_hachu_v_sidebar")
                
                ai_amount = data.get("発注金額", data.get("金額", 0))
                confirm_amount = st.number_input("税抜振込金額", value=int(ai_amount), key="ai_amt_hachu_v_sidebar")
                ai_contractor = data.get("業社・工種名", "")
                confirm_contractor = st.text_input("業者名", value=ai_contractor, key="ai_contractor_hachu_v_sidebar")
                
                if st.button("✓ この発注データを物件に反映する", type="primary", key="ai_btn_hachu_v_sidebar"):
                    if ai_target_project != "(選択してください)":
                        projects_db[ai_target_project]["client_name"] = confirm_client
                        new_req = {
                            "移動先": "-", "工種名": "AI読取(発注書)", "業者管理番号": "", "業者・工種名": confirm_contractor,
                            "実行予算": 0, "協力業者支払": confirm_amount, "完了金額": 0
                        }
                        if "detail_request" not in projects_db[ai_target_project]:
                            projects_db[ai_target_project]["detail_request"] = []
                        projects_db[ai_target_project]["detail_request"].append(new_req)
                        save_project_to_db(ai_target_project, projects_db[ai_target_project])
                        st.success(f"✓ {ai_target_project} に発注データ（{confirm_contractor}：{confirm_amount}円）を反映しました！")
                        st.session_state.ai_result = None
                        st.rerun()
                    else: st.error("物件名を選択してください。")
                    
            else:
                st.info("↓ 以下の抽出された項目を確認・修正して反映してください。")
                ai_target_project = st.selectbox("紐付ける物件名", ["(選択してください)"] + project_names, key="ai_sel_proj_seikyu_v_sidebar")
                ai_contractor = data.get("業者名", data.get("業社・工種名", ""))
                c_col1, c_col2, c_col3 = st.columns(3)
                with c_col1: confirm_gyousha = st.text_input("紐付ける業者", value=ai_contractor, key="ai_sel_gyo_seikyu_v_sidebar")
                with c_col2:
                    ai_koshu = data.get("工種名", "AI自動読取")
                    confirm_koshu = st.text_input("工種名（メモ）", value=ai_koshu, key="ai_koshu_seikyu_v_sidebar")
                with c_col3: confirm_amount = st.number_input("税抜支払金額", value=int(data.get("金額", data.get("発注金額", 0))), key="ai_amt_seikyu_v_sidebar")
                
                if st.button("✓ この支払データを「依頼業社」に送る", type="primary", key="ai_btn_seikyu_v_sidebar"):
                    if ai_target_project != "(選択してください)":
                        new_req = {
                            "移動先": "-", "工種名": confirm_koshu, "業者管理番号": "", "業者・工種名": confirm_gyousha,
                            "実行予算": 0, "協力業者支払": confirm_amount, "完了金額": 0
                        }
                        if "detail_request" not in projects_db[ai_target_project]:
                            projects_db[ai_target_project]["detail_request"] = []
                        projects_db[ai_target_project]["detail_request"].append(new_req)
                        save_project_to_db(ai_target_project, projects_db[ai_target_project])
                        st.success(f"完了： {ai_target_project} の「依頼業社」にデータを送信しました！")
                        st.session_state.ai_result = None
                        st.rerun()
                    else: st.error("物件名を選択してください。")

    # ======= 2. 勤怠・未振分マージセクション =======
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">◴ 未振分工数（〇ルール）マージ管理</div>', unsafe_allow_html=True)
    st.markdown("ANDPADの予定表に入力された（〇）から始まる仮の物件名と、その累計工数を表示しています。")

    all_provisional = {} 
    if parsed_andpad_data:
        for staff, items in parsed_andpad_data.items():
            for item in items:
                p_name = item["raw_name"]
                if p_name and str(p_name).strip().startswith(('〇', '○', '◯', '丸')):
                    all_provisional[p_name] = all_provisional.get(p_name, 0.0) + item["hours"]
        
    mapped_aliases = set()
    for p_data in projects_db.values():
        if isinstance(p_data, dict):
            for alias in p_data.get("aliases", []):
                mapped_aliases.add(alias)
                
    sys_settings = projects_db.get("_SYSTEM_SETTINGS_", {})
    ignored_provis = sys_settings.get("ignored_provisional", [])
                
    unmapped_provisional = {k: v for k, v in all_provisional.items() if k not in mapped_aliases and k not in ignored_provis}
    official_project_options = ["-"] + [k for k in projects_db.keys() if k != "_SYSTEM_SETTINGS_"]

    if unmapped_provisional:
        df_unmapped = pd.DataFrame([
            {"除外": False, "仮物件名": k, "累計工数 (h)": v, "紐付け先物件": "-"} 
            for k, v in unmapped_provisional.items()
        ])
        st.info(f"▪ 現在、{len(unmapped_provisional)}件 の未振分データが見つかりました。")
        edited_unmapped = st.data_editor(
            df_unmapped,
            column_config={
                "除外": st.column_config.CheckboxColumn("✕ 削除", default=False),
                "仮物件名": st.column_config.TextColumn("「〇」で入力された仮物件名", disabled=True),
                "累計工数 (h)": st.column_config.NumberColumn("全メンバー累計工数 (h)", disabled=True),
                "紐付け先物件": st.column_config.SelectboxColumn("紐付け先 (本登録物件を選択)", options=official_project_options)
            },
            hide_index=True,
            use_container_width=True,
            key="unmapped_editor_v_sidebar"
        )
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✓ 選択した紐付けを確定して合算する", type="primary", key="merge_unmapped_btn_v_sidebar"):
                updated_projects = set()
                for idx, row in edited_unmapped.iterrows():
                    target = row["紐付け先物件"]
                    alias = row["仮物件名"]
                    if target != "-":
                        if "aliases" not in projects_db[target]:
                            projects_db[target]["aliases"] = []
                        if alias not in projects_db[target]["aliases"]:
                            projects_db[target]["aliases"].append(alias)
                            updated_projects.add(target)
                if updated_projects:
                    for t in updated_projects:
                        save_project_to_db(t, projects_db[t])
                    st.session_state.andpad_hours_cache = {}
                    st.session_state.andpad_breakdown_cache = {}
                    st.success("✓ 紐付け（合算）が完了しました！")
                    st.rerun()
                else:
                    st.warning("変更がありませんでした。")
                    
        with col_btn2:
            if st.button("🗑️ チェックした未振分物件を一覧から削除", key="delete_unmapped_btn_v_sidebar"):
                keys_to_del = edited_unmapped[edited_unmapped["除外"] == True]["仮物件名"].tolist()
                if keys_to_del:
                    if "_SYSTEM_SETTINGS_" not in projects_db:
                        projects_db["_SYSTEM_SETTINGS_"] = get_default_project_data()
                    if "ignored_provisional" not in projects_db["_SYSTEM_SETTINGS_"]:
                        projects_db["_SYSTEM_SETTINGS_"]["ignored_provisional"] = []
                    
                    projects_db["_SYSTEM_SETTINGS_"]["ignored_provisional"].extend(keys_to_del)
                    save_project_to_db("_SYSTEM_SETTINGS_", projects_db["_SYSTEM_SETTINGS_"])
                    st.success(f"✓ {len(keys_to_del)} 件の未振分物件を削除（非表示に）しました。")
                    st.rerun()
                else:
                    st.warning("削除対象にチェックが入っていません。")
    else:
        st.success("✓ 現在、未振分の「〇」物件データはありません。")

    st.markdown("---")
    with st.expander("紐付け（学習）済みのルール一覧", expanded=False):
        mapped_rows = []
        for p_name, p_data in projects_db.items():
            if isinstance(p_data, dict) and p_data.get("aliases"):
                for alias in p_data["aliases"]:
                    mapped_rows.append({"本登録物件名": p_name, "学習済みの仮物件名": alias})
        if mapped_rows:
            st.dataframe(pd.DataFrame(mapped_rows), use_container_width=True, hide_index=True)
            if st.button("✕ 学習済みのルールをすべてリセット", type="secondary", key="reset_alias_v_sidebar"):
                for p_name in projects_db:
                    if "aliases" in projects_db[p_name] and projects_db[p_name]["aliases"]:
                        projects_db[p_name]["aliases"] = []
                        save_project_to_db(p_name, projects_db[p_name])
                    if p_name == "_SYSTEM_SETTINGS_" and "ignored_provisional" in projects_db[p_name]:
                        projects_db[p_name]["ignored_provisional"] = []
                        save_project_to_db(p_name, projects_db[p_name])
                st.session_state.andpad_hours_cache = {}
                st.session_state.andpad_breakdown_cache = {}
                st.success("リセット完了しました。")
                st.rerun()
        else:
            st.info("現在学習済みのルールはありません。")