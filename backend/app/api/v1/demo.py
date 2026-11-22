"""Demo dataset generator and interview scenario catalogue."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write
from app.api.v1._helpers import serialize
from app.models.operations import DemoScenario
from app.services.jobs import enqueue

router = APIRouter(prefix="/demo", tags=["demo"])

SCENARIO_COLUMNS = ["id", "key", "title", "question", "context", "challenge", "steps", "modules", "expected_findings", "interpretation", "recommended_actions", "limitations", "interview_explanation", "dataset_info"]


@router.get("/scenarios")
def scenarios(db: DB, user: UserDep):
    rows = db.scalars(select(DemoScenario).order_by(DemoScenario.id)).all()
    if not rows:
        from app.services.scenarios import seed_scenarios

        seed_scenarios(db)
        db.commit()
        rows = db.scalars(select(DemoScenario).order_by(DemoScenario.id)).all()
    return {"items": [serialize(r, SCENARIO_COLUMNS) for r in rows]}


@router.get("/scenarios/{key}")
def scenario(key: str, db: DB, user: UserDep):
    row = db.scalar(select(DemoScenario).where(DemoScenario.key == key))
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(404, "Scenario not found")
    return serialize(row, SCENARIO_COLUMNS)


@router.post("/generate", status_code=202)
def generate(payload: dict | None, db: DB, user: UserDep):
    check_write(user)
    payload = payload or {}
    size = int(payload.get("size", 1000))
    if size > 200000:
        from fastapi import HTTPException

        raise HTTPException(400, "Maximum synthetic dataset size is 200,000 URLs")
    job = enqueue(db, "generate_demo", f"Generate {size:,} URL demo",
                  {**payload, "size": size}, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued",
            "note": "All generated traffic/revenue/keyword metrics are synthetic and labelled as such."}


@router.post("/reset", status_code=202)
def reset(payload: dict | None, db: DB, user: UserDep):
    check_write(user)
    payload = payload or {}
    job = enqueue(db, "reset_demo", "Reset demo data", payload, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}
