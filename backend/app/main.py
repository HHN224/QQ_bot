from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, load_config
from .db import Database, utcnow
from .models import FeedbackRequest, GenerateRequest, SettingsUpdate
from .services.parser import parse_chat
from .services.pipeline import DigestPipeline


def runtime(db: Database):
    return load_config(db.settings())


initial_config = load_config()
db = Database(initial_config.database_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.cleanup(runtime(db).retention_days)
    yield


app = FastAPI(title="QQ 群聊每日简报", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"status": "ok", "local_only": True}


@app.post("/api/jobs")
async def create_job(request: GenerateRequest, background_tasks: BackgroundTasks):
    digest_date = request.digest_date.isoformat()
    messages = parse_chat(request.text, digest_date)
    if not messages:
        raise HTTPException(400, "没有解析到有效消息")
    new_count, duplicate_count = db.ingest(digest_date, messages)
    job_id = db.create_job(digest_date, new_count, duplicate_count)
    if new_count == 0:
        db.update_job(job_id, status="completed", stage="所有消息都已处理过", progress=100)
    else:
        pipeline = DigestPipeline(db, runtime(db))
        background_tasks.add_task(pipeline.run, job_id, digest_date)
    return {"job_id": job_id, "new_count": new_count, "duplicate_count": duplicate_count}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@app.get("/api/digests/{digest_date}")
def get_digest(digest_date: str):
    digest = db.digest(digest_date)
    if not digest:
        raise HTTPException(404, "当天还没有简报")
    return digest


@app.get("/api/history")
def history(q: str = Query(default="", max_length=100)):
    return db.history(q.strip())


@app.get("/api/settings")
def get_settings():
    config = runtime(db)
    return {
        "api_base_url": config.api_base_url, "screening_model": config.screening_model,
        "final_model": config.final_model, "monthly_budget_cny": config.monthly_budget_cny,
        "retention_days": config.retention_days, "input_price_cny_per_million": config.input_price_cny_per_million,
        "output_price_cny_per_million": config.output_price_cny_per_million,
        "api_key_configured": bool(config.api_key), "monthly_spend_cny": round(db.monthly_spend(), 4),
        "allow_local_fallback": config.allow_local_fallback,
    }


@app.put("/api/settings")
def put_settings(request: SettingsUpdate):
    if not request.api_base_url.startswith(("http://", "https://")):
        raise HTTPException(400, "Base URL 必须是 HTTP/HTTPS 地址")
    values = {"OPENAI_BASE_URL": request.api_base_url, "SCREENING_MODEL": request.screening_model, "FINAL_MODEL": request.final_model, "MONTHLY_BUDGET_CNY": str(request.monthly_budget_cny), "RETENTION_DAYS": str(request.retention_days), "INPUT_PRICE_CNY_PER_MILLION": str(request.input_price_cny_per_million), "OUTPUT_PRICE_CNY_PER_MILLION": str(request.output_price_cny_per_million)}
    db.update_settings(values)
    db.cleanup(request.retention_days)
    return get_settings()


@app.post("/api/feedback", status_code=204)
def feedback(request: FeedbackRequest):
    with db.connect() as connection:
        connection.execute("INSERT INTO feedback(digest_item_id,value,created_at) VALUES(?,?,?)", (request.digest_item_id, request.value, utcnow()))


frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        requested = frontend_dist / path
        if path and requested.is_file() and frontend_dist in requested.resolve().parents:
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")

