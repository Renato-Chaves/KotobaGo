from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.models import init_db
from routes import story, vocab

app = FastAPI(title="KotobaGo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(vocab.router)
app.include_router(story.router)


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}
