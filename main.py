from fastapi import FastAPI

from recommender import chat
from schemas import ChatRequest, ChatResponse


app = FastAPI(title="SHL Assessment Recommender")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> dict:
    messages = [message.model_dump() for message in request.messages]
    return chat(messages)
