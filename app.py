import asyncio
import json
import os
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
try:
    import google.generativeai as genai
except ModuleNotFoundError:
    # Fallback for older library versions, though 'google.generativeai' is standard.
    from google import genai

# -----------------------------------------------------------------------
# 0. Configuration
# -----------------------------------------------------------------------
# Automatically load environment variables from .env file
load_dotenv()

shanghai_tz = pytz.timezone("Asia/Shanghai")

# Improved: Use environment variables for sensitive information
API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("MODEL", "gemini-1.5-pro-latest")

if not API_KEY or API_KEY.startswith("sk-REPLACE_ME"):
    raise RuntimeError("Please configure API_KEY in your environment (e.g., 'export API_KEY=YOUR_KEY')")

# Determine client type based on API_KEY format
if API_KEY.startswith("sk-"):
    # OpenAI-compatible client (e.g., OpenAI, OpenRouter)
    extra_headers = {}
    if "openrouter.ai" in BASE_URL.lower():
        extra_headers = {
            "HTTP-Referer": "https://github.com/fogsightai/fogsight",
            "X-Title": "Fogsight - AI Animation Generator"
        }
    
    client = AsyncOpenAI(
        api_key=API_KEY, 
        base_url=BASE_URL,
        default_headers=extra_headers
    )
    USE_GEMINI = False
else:
    # Google Gemini client
    genai.configure(api_key=API_KEY)
    gemini_client = genai.GenerativeModel(MODEL)
    USE_GEMINI = True

templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------
# 1. FastAPI Initialization
# -----------------------------------------------------------------------
app = FastAPI(title="AI Animation Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    topic: str
    history: Optional[List[dict]] = None

# -----------------------------------------------------------------------
# 2. Core: Streaming Generator
# -----------------------------------------------------------------------
async def llm_event_stream(
    topic: str,
    history: Optional[List[dict]] = None,
) -> AsyncGenerator[str, None]:
    history = history or []
    
    # Improved: Added instruction for structured output in the system prompt
    system_prompt = f"""请你生成一个非常精美的动态动画,讲讲 {topic}
要动态的,要像一个完整的,正在播放的视频，包含进度条或者进度提示器。包含一个完整的过程，能把知识点讲清楚。
页面极为精美，好看，有设计感，同时能够很好的传达知识。知识和图像要准确
附带一些旁白式的文字解说,从头到尾讲清楚一个小的知识点
不需要任何互动按钮,直接开始播放
使用和谐好看，广泛采用的浅色配色方案，除非必要，尽量不使用渐变色，使用很多的，丰富的视觉元素。双语字幕
**请保证任何一个元素都在一个2k分辨率的容器中被摆在了正确的位置，避免穿模，字幕遮挡，图形位置错误等等问题影响正确的视觉传达**
html+css+js+svg，放进一个html里。使用 Tailwind CSS <script src="https://cdn.tailwindcss.com"></script>
生成所有交互界面，尽可能不写自定义css。如果需要 Icon ，可以使用FontAwesome（或其他开源UI组件）让界面更加精美、专业化。
**重要指令: 请将最终生成的完整HTML代码包裹在 <final_output> 和 </final_output> 标签中，不要在其他地方使用这个标签。**"""

    if USE_GEMINI:
        try:
            # 1. Prepare messages for Gemini's format
            gemini_history = []
            for msg in history:
                role = 'user' if msg['role'] == 'user' else 'model'
                gemini_history.append({'role': role, 'parts': [msg['content']]})
            
            # Combine system prompt and topic into the first user message
            full_user_prompt = system_prompt + "\n\n" + topic
            contents = [*gemini_history, {'role': 'user', 'parts': [full_user_prompt]}]
            
            # 2. Improved: Use stream=True for a true streaming call
            response_iterator = gemini_client.generate_content(
                contents=contents,
                stream=True
            )
            
            for chunk in response_iterator:
                if chunk.text:
                    payload = json.dumps({"token": chunk.text}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    await asyncio.sleep(0.001) # Minimal delay to allow other tasks

        except Exception as e:
            error_payload = json.dumps({'error': f'Gemini API Error: {str(e)}'}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
            return
    else:  # OpenAI-compatible logic
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": topic},
        ]

        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                stream=True,
                temperature=0.8, 
            )
        except OpenAIError as e:
            error_payload = json.dumps({'error': f'OpenAI API Error: {str(e)}'}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
            return

        async for chunk in response:
            token = chunk.choices[0].delta.content or ""
            if token:
                payload = json.dumps({"token": token}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0.001)

    yield 'data: {"event":"[DONE]"}\n\n'

# -----------------------------------------------------------------------
# 3. Routes (Simplified)
# -----------------------------------------------------------------------
@app.post("/generate")
async def generate(chat_request: ChatRequest):
    """
    Main endpoint: POST /generate
    Accepts a JSON body with "topic" and optional "history".
    Returns an SSE stream.
    """
    # Improved: Directly call and return the streaming generator
    stream_generator = llm_event_stream(
        chat_request.topic, 
        chat_request.history
    )
    
    headers = {
        "Cache-Control": "no-store",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(stream_generator, headers=headers)

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse(
        "index.html", {
            "request": request,
            "time": datetime.now(shanghai_tz).strftime("%Y%m%d%H%M%S")})

# -----------------------------------------------------------------------
# 4. Local Startup Command
# -----------------------------------------------------------------------
# uvicorn app:app --reload --host 0.0.0.0 --port 8000

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
