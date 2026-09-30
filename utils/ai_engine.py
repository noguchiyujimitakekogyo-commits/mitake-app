import google.generativeai as genai

# 🔽 ローカルAI (Ollama)
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

def call_jarvis_ai(system_instruction, user_prompt, model_choice, gemini_api_key):
    """
    Ollama または Gemini を自動で切り替えてAIを呼び出す共通関数
    """
    if "Ollama" in model_choice:
        if not OLLAMA_AVAILABLE:
            return "🚨 Pythonパッケージ 'ollama' が見つかりません。ターミナルで `pip install ollama` を実行してください。"
        
        if "3b" in model_choice:
            ollama_model = "qwen2.5:3b"
        else:
            ollama_model = "qwen2.5:7b"

        try:
            response = ollama.chat(
                model=ollama_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return response['message']['content']
        except Exception as e:
            return f"🚨 Ollamaへの接続に失敗しました。詳細エラー: {e}"
    else:
        if gemini_api_key == "YOUR_KEY_HERE" or gemini_api_key == "ここに取得したAPIキーを貼り付けてください":
            return "⚠ Gemini APIキーが設定されていません。"
        try:
            genai.configure(api_key=gemini_api_key)
            
            # 指示と質問を1つのテキストに合体
            combined_prompt = f"【システムからの絶対厳守の指示】\n{system_instruction}\n\n---\n\n{user_prompt}"
            
            # 💡 APIの指示通り「gemini-3.6-flash」を使用
            model = genai.GenerativeModel('gemini-3.6-flash')
            response = model.generate_content(combined_prompt)
            
            return response.text
        except Exception as e:
            return f"🚨 Gemini APIエラー: {e}"