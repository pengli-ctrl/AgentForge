"""本地 OpenAI 兼容 mock 服务。"""
from fastapi import FastAPI
app = FastAPI()
@app.get("/health")
def health():
    """返回健康状态。"""
    return {"status": "ok"}
@app.post("/v1/chat/completions")
def chat(body: dict):
    """返回固定聊天响应。"""
    return {"id":"mock","object":"chat.completion","model":body.get("model","mock-model"),"choices":[{"index":0,"message":{"role":"assistant","content":"mock response"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}
