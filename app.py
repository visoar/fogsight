import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Optional
from pathlib import Path

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
try:
    import google.generativeai as genai
except ModuleNotFoundError:
    from google import genai

# -----------------------------------------------------------------------
# 0. Configuration & Initialization
# -----------------------------------------------------------------------
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
ANIMATIONS_DIR = BASE_DIR / "animations"
ANIMATIONS_DIR.mkdir(exist_ok=True)
shanghai_tz = pytz.timezone("Asia/Shanghai")

API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("MODEL", "gemini-1.5-pro-latest")

if not API_KEY or API_KEY.startswith("sk-REPLACE_ME"):
    raise RuntimeError("Please configure API_KEY in your environment (e.g., 'export API_KEY=YOUR_KEY')")

if API_KEY.startswith("sk-"):
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    USE_GEMINI = False
else:
    genai.configure(api_key=API_KEY)
    gemini_client = genai.GenerativeModel(MODEL)
    USE_GEMINI = True

# -----------------------------------------------------------------------
# 1. FastAPI App Initialization
# -----------------------------------------------------------------------
app = FastAPI(title="Fogsight AI Animation Backend", version="1.4.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/animations", StaticFiles(directory=ANIMATIONS_DIR), name="animations")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# -----------------------------------------------------------------------
# 2. Pydantic Models for Requests
# -----------------------------------------------------------------------
class GenerateOutlineRequest(BaseModel):
    topic: str
    feedback: Optional[str] = None # NEW: Added feedback field

class GenerateAnimationRequest(BaseModel):
    topic: str
    outline: str

# -----------------------------------------------------------------------
# 3. Core Logic: Streaming Generators
# -----------------------------------------------------------------------
async def stream_llm_response(messages: list) -> AsyncGenerator[str, None]:
    print(f"--- [LLM Streamer] Preparing to send request. Using Gemini: {USE_GEMINI} ---")
    # Gemini logic here...
    if USE_GEMINI:
        # ... same as before
        pass
    else: # OpenAI-compatible
        try:
            response = await client.chat.completions.create(
                model=MODEL, messages=messages, stream=True, temperature=0.8,
            )
            async for chunk in response:
                token = chunk.choices[0].delta.content or ""
                if token: yield token
        except OpenAIError as e:
            print(f"!!! [LLM Streamer] OpenAI API Error caught: {e}")
            yield json.dumps({'error': f'OpenAI API Error: {str(e)}'}, ensure_ascii=False)
            return

# -----------------------------------------------------------------------
# 4. API Endpoints
# -----------------------------------------------------------------------
@app.post("/generate-outline")
async def generate_outline(req: GenerateOutlineRequest):
    print(f"\n--- [API /generate-outline] Received request for topic: '{req.topic}' ---")
    
    # NEW: Dynamically build the prompt based on feedback
    if req.feedback:
        print(f"--- [API /generate-outline] With feedback: '{req.feedback}' ---")
        user_prompt = f"""你是一个专业的影视编剧。请根据用户的修改意见，重新生成或调整关于主题 “{req.topic}” 的动画分镜大纲。

用户的修改意见是：
"{req.feedback}"

请严格按照用户的意见进行修改。如果意见是补充，请在原有基础上补充；如果是修改，请替换相应部分。保持大纲的完整性和逻辑性。
输出格式依然是包含【场景描述】和【旁白】的 Markdown。
"""
    else:
        user_prompt = f"""你是一个专业的影视编剧和知识科普专家。
请为主题 “{req.topic}” 生成一个动画分镜大纲。
大纲需要清晰、有逻辑，分为3-5个场景。
每个场景需要包含【场景描述】和【旁白】两部分。
【场景描述】说明这个场景的核心视觉元素和动态效果。
【旁白】是这个场景配的解说词。
请使用 Markdown 格式化你的回答。
"""
    messages = [{"role": "user", "content": user_prompt}]
    
    print(f"--- [API /generate-outline] Sending messages to LLM:\n{json.dumps(messages, indent=2, ensure_ascii=False)}")
    
    async def sse_generator():
        is_first_chunk = True
        async for raw_chunk in stream_llm_response(messages):
            if is_first_chunk:
                is_first_chunk = False
                try:
                    error_data = json.loads(raw_chunk)
                    if isinstance(error_data, dict) and 'error' in error_data:
                        print(f"--- [API /generate-outline] Detected error object: {error_data}")
                        yield f'data: {json.dumps(error_data, ensure_ascii=False)}\n\n'
                        return
                except json.JSONDecodeError:
                    pass # Normal token, continue
            
            payload = json.dumps({"token": raw_chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.001)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.post("/generate-animation")
async def generate_animation(req: GenerateAnimationRequest):
    # This endpoint remains largely the same
    print(f"\n--- [API /generate-animation] Received request for topic: '{req.topic}' ---")
    user_prompt = f"""你将根据用户提供的主题和动画大纲，生成一个精美的动态动画。
**主题:** {req.topic}
**动画大纲:**
---
{req.outline}
---
**你的任务和要求:**
1.  **严格遵循大纲:** 必须按照上面提供的动画大纲来生成场景和旁白。
2.  **成品要求:** 生成一个完整的、独立的 HTML 文件。
3.  **技术栈:** 使用 Tailwind CSS (`<script src="https://cdn.tailwindcss.com"></script>`)。
4.  **视觉设计:** 页面精美，包含SVG动画、进度条，提供中英双语字幕。
5.  **最终输出格式:** **至关重要!** 将最终生成的完整 HTML 代码包裹在 `<final_output>` 和 `</final_output>` 标签中。
"""
    messages = [{"role": "user", "content": user_prompt}]
    print(f"--- [API /generate-animation] Sending messages to LLM:\n{json.dumps(messages, indent=2, ensure_ascii=False)}")

    async def animation_stream_and_save():
        full_html_content = ""
        async for token in stream_llm_response(messages):
            try: # Error checking on every token
                error_data = json.loads(token)
                if isinstance(error_data, dict) and 'error' in error_data:
                    yield f'data: {json.dumps(error_data, ensure_ascii=False)}\n\n'
                    return
            except json.JSONDecodeError:
                pass # Normal token
            
            full_html_content += token
            yield f'data: {json.dumps({"token": token}, ensure_ascii=False)}\n\n'
            await asyncio.sleep(0.001)

        # ... (saving logic remains the same)
        try:
            start_tag, end_tag = "<final_output>", "</final_output>"
            start_index, end_index = full_html_content.find(start_tag), full_html_content.find(end_tag)
            if start_index != -1 and end_index != -1:
                final_html = full_html_content[start_index + len(start_tag):end_index].strip()
                animation_id = str(uuid.uuid4())
                file_path = ANIMATIONS_DIR / f"{animation_id}.html"
                with open(file_path, "w", encoding="utf-8") as f: f.write(final_html)
                print(f"--- [API /generate-animation] Successfully saved animation to {file_path} ---")
                yield f'data: {json.dumps({"event": "done", "animation_id": animation_id})}\n\n'
            else:
                print(f"!!! [API /generate-animation] Error: <final_output> tags not found.")
                yield f'data: {json.dumps({"event": "error", "message": "Could not find <final_output> tags."})}\n\n'
        except Exception as e:
            print(f"!!! [API /generate-animation] Error saving file: {e}")
            yield f'data: {json.dumps({"event": "error", "message": f"Failed to save animation file: {str(e)}"})}\n\n'

    return StreamingResponse(animation_stream_and_save(), media_type="text/event-stream")

# Other routes remain the same
@app.get("/view/{animation_id}", response_class=HTMLResponse)
async def view_animation(animation_id: str):
    file_path = ANIMATIONS_DIR / f"{animation_id}.html"
    if not file_path.is_file(): raise HTTPException(status_code=404, detail="Animation not found")
    with open(file_path, "r", encoding="utf-8") as f: return HTMLResponse(content=f.read())

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", { "request": request, "time": datetime.now(shanghai_tz).strftime("%Y%m%d%H%M%S") })

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)