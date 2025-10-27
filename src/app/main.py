# from fastapi.security import OAuth2PasswordBearer
# from fastapi import status
# from src.app.security import (
#     hash_password, verify_password, create_access_token, decode_token
# )
# from src.db.models import Hospital, User
# import os
# import json
# import requests
# from datetime import datetime, timezone, timedelta

# from fastapi import FastAPI, Depends, HTTPException, Body, Request, Path
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from sqlalchemy.orm import Session
# from sqlalchemy import func, desc
# from fastapi.encoders import jsonable_encoder

# from src.db.database import get_db, init_db
# from src.db import crud, schemas
# from src.db.models import Patient, Call

# # ------------------------------------------------------------
# # 🌏 Timezone Helpers (IST)
# # ------------------------------------------------------------

# IST = timezone(timedelta(hours=5, minutes=30))

# def to_ist_iso(dt):
#     """Convert UTC datetime to IST ISO string."""
#     if not dt:
#         return None
#     if dt.tzinfo is None:
#         dt = dt.replace(tzinfo=timezone.utc)
#     return dt.astimezone(IST).isoformat()


# # ------------------------------------------------------------
# # 🚀 FastAPI App Setup
# # ------------------------------------------------------------

# app = FastAPI(title="Hospital Voice Agent API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:3000", "https://localhost:3000"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# @app.on_event("startup")
# def startup_event():
#     print("✅ Starting up FastAPI app")
#     init_db()


# @app.get("/healthz")
# def health_check():
#     return {"status": "ok", "message": "FastAPI running successfully"}


# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
#     payload = decode_token(token)
#     if not payload or "sub" not in payload:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

#     user_id = int(payload["sub"])
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
#     return user
# # ------------------------------------------------------------
# # 👥 Patient Endpoints
# # ------------------------------------------------------------

# @app.post("/patients", response_model=schemas.Patient)
# def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
#     patient = crud.get_or_create_patient(
#         db, payload.name, payload.phone, payload.language, payload.age
#     )
#     return patient


# @app.get("/patients")
# def get_patients(db: Session = Depends(get_db)):
#     results = (
#         db.query(Patient, func.count(Call.id).label("call_count"))
#         .outerjoin(Call, Patient.id == Call.patient_id)
#         .group_by(Patient.id)
#         .order_by(Patient.id.desc())
#         .all()
#     )

#     data = [
#         {
#             "id": p.id,
#             "name": p.name,
#             "phone": p.phone,
#             "age": p.age,
#             "language": p.language,
#             "patient_type": p.patient_type,
#             "custom_questions": p.custom_questions,
#             "created_at": p.created_at,
#             "call_count": count,
#         }
#         for p, count in results
#     ]
#     return JSONResponse(content=jsonable_encoder(data))


# @app.delete("/patients/{patient_id}")
# def delete_patient(patient_id: int, db: Session = Depends(get_db)):
#     success = crud.delete_patient(db, patient_id)
#     if not success:
#         raise HTTPException(status_code=404, detail="Patient not found")
#     return {"status": "deleted"}


# # ------------------------------------------------------------
# # 📞 Bolna API Integration
# # ------------------------------------------------------------

# BOLNA_API_URL = "https://api.bolna.ai/call"
# BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
# BOLNA_AGENT_ID = os.getenv("BOLNA_AGENT_ID")
# BOLNA_FROM_NUMBER = os.getenv("BOLNA_FROM_NUMBER", "+911234567890")


# @app.post("/dial")
# def dial_patient(body: dict = Body(...), db: Session = Depends(get_db)):
#     patient_id = body.get("patient_id")
#     if not patient_id:
#         raise HTTPException(status_code=400, detail="patient_id is required")

#     patient = crud.get_patient_by_id(db, patient_id)
#     if not patient:
#         raise HTTPException(status_code=404, detail="Patient not found")

#     call = crud.create_call(db, patient_id=patient.id, status="initiated")

#     payload = {
#         "agent_id": BOLNA_AGENT_ID,
#         "recipient_phone_number": patient.phone,
#         "from_phone_number": BOLNA_FROM_NUMBER,
#         "user_data": {
#             "patient_id": patient.id,
#             "call_id": call.id,
#             "patient_name": patient.name,
#             "language": patient.language,
#             "custom_questions": patient.custom_questions or [],
#         },
#     }

#     headers = {
#         "Authorization": f"Bearer {BOLNA_API_KEY}",
#         "Content-Type": "application/json",
#     }

#     try:
#         res = requests.post(BOLNA_API_URL, json=payload, headers=headers, timeout=10)
#         if res.status_code == 200:
#             data = res.json()
#             call.status = "calling"
#             db.commit()
#             return {
#                 "status": "success",
#                 "bolna_response": data,
#                 "local_call_id": call.id,
#                 "patient": {"id": patient.id, "name": patient.name, "phone": patient.phone},
#             }
#         else:
#             call.status = "failed"
#             db.commit()
#             raise HTTPException(status_code=500, detail=f"Bolna error: {res.text}")
#     except Exception as e:
#         call.status = "failed"
#         db.commit()
#         raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")


# # ------------------------------------------------------------
# # 📡 Bolna Webhook
# # ------------------------------------------------------------

# @app.post("/webhook/bolna")
# async def bolna_webhook(request: Request, db: Session = Depends(get_db)):
#     try:
#         data = await request.json()
#         print("\n🔔 BOLNA WEBHOOK RECEIVED:")
#         print(json.dumps(data, indent=2))

#         status = data.get("status", "unknown")
#         transcript = data.get("transcript", "")
#         duration = float(data.get("telephony_data", {}).get("duration", 0) or 0)
#         extraction = data.get("extracted_data", {})

#         context_details = data.get("context_details", {})
#         recipient_data = context_details.get("recipient_data", {})
#         user_data = data.get("user_data", {})

#         local_call_id = recipient_data.get("call_id") or user_data.get("call_id")
#         if not local_call_id:
#             return {"status": "warning", "message": "No local call_id"}

#         call = db.query(crud.models.Call).filter(crud.models.Call.id == local_call_id).first()
#         if not call:
#             return {"status": "warning", "message": "Call not found"}

#         call.status = status
#         call.duration = duration
#         call.execution_id = data.get("id")
#         call.ended_at = datetime.utcnow()
#         db.commit()

#         # --- Save transcript with roles ---
#         if transcript:
#             def parse_turns(raw: str):
#                 turns, role, buf = [], None, []
#                 def flush():
#                     if role and buf:
#                         txt = "\n".join(buf).strip()
#                         if txt: turns.append((role, txt))
#                 for line in (raw or "").splitlines():
#                     stripped = line.strip()
#                     if stripped.lower().startswith("assistant:"):
#                         flush(); role = "assistant"; buf = [stripped.split(":", 1)[1].strip()]
#                     elif stripped.lower().startswith("user:"):
#                         flush(); role = "user"; buf = [stripped.split(":", 1)[1].strip()]
#                     else:
#                         buf.append(stripped)
#                 flush()
#                 return turns

#             for r, txt in parse_turns(transcript):
#                 crud.save_transcript(db, local_call_id, txt, role=r)

#         if extraction:
#             crud.save_extraction(db, local_call_id, extraction)

#         print(f"✅ Call {local_call_id} updated successfully.")
#         return {"status": "success", "call_id": local_call_id}

#     except Exception as e:
#         print(f"❌ Webhook error: {e}")
#         return {"status": "error", "message": str(e)}


# # ------------------------------------------------------------
# # ☎️ Patient Call List
# # ------------------------------------------------------------

# @app.get("/patients/{patient_id}/calls")
# def get_patient_calls(patient_id: int, db: Session = Depends(get_db)):
#     from src.db import models

#     patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
#     if not patient:
#         return {"patient_name": "Unknown", "calls": [], "message": "No patient found"}

#     calls = (
#         db.query(models.Call)
#         .filter(models.Call.patient_id == patient_id)
#         .order_by(models.Call.created_at.desc())
#         .all()
#     )

#     call_data = [
#         {
#             "call_id": c.id,
#             "status": c.status,
#             "duration": c.duration or 0,
#             "started_at": to_ist_iso(c.started_at),
#             "ended_at": to_ist_iso(c.ended_at),
#             "cost": 0.0,
#         }
#         for c in calls
#     ]

#     return {"patient_name": patient.name, "calls": call_data}


# # ------------------------------------------------------------
# # 📊 Call Detail (with Bolna cost)
# # ------------------------------------------------------------

# @app.get("/calls/{call_id}")
# def get_call_details(call_id: int, db: Session = Depends(get_db)):
#     from src.db import models

#     call = db.query(models.Call).filter(models.Call.id == call_id).first()
#     if not call:
#         raise HTTPException(status_code=404, detail="Call not found")

#     patient = call.patient

#     transcripts = (
#         db.query(models.Transcript)
#         .filter(models.Transcript.call_id == call_id)
#         .order_by(models.Transcript.id.asc())
#         .all()
#     )

#     conversation = [{"role": (t.role or "assistant"), "content": t.text} for t in transcripts]

#     extraction = (
#         db.query(models.CallExtraction)
#         .filter(models.CallExtraction.call_id == call_id)
#         .order_by(models.CallExtraction.id.desc())
#         .first()
#     )

#     summary = {
#         "has_pain": getattr(extraction, "has_pain", None),
#         "taking_medicines": getattr(extraction, "taking_medicines", None),
#         "overall_mood": getattr(extraction, "overall_mood", None),
#         "needs_callback": getattr(extraction, "needs_callback", None),
#         "answer_q1": getattr(extraction, "answer_q1", None),
#         "answer_q2": getattr(extraction, "answer_q2", None),
#         "answer_q3": getattr(extraction, "answer_q3", None),
#     } if extraction else {}

#     costs = {
#         "stt": 0.0, "llm": 0.0, "tts": 0.0, "telephony": 0.0, "infrastructure": 0.0, "total": 0.0
#     }

#     if getattr(call, "execution_id", None):
#         try:
#             url = f"https://api.bolna.ai/executions/{call.execution_id}"
#             headers = {"Authorization": f"Bearer {BOLNA_API_KEY}"}
#             res = requests.get(url, headers=headers, timeout=5)
#             if res.status_code == 200:
#                 cost_data = res.json()
#                 breakdown = cost_data.get("cost_breakdown", {})
#                 total_cost = cost_data.get("total_cost", 0)
#                 costs["total"] = round(total_cost / 100, 4)
#                 for k, v in breakdown.items():
#                     if isinstance(v, (int, float)):
#                         costs[k] = round(v / 100, 4)
#                     elif isinstance(v, dict) and "cost" in v:
#                         costs[k] = round(v["cost"] / 100, 4)
#         except Exception as e:
#             print(f"⚠️ Failed to fetch Bolna cost: {e}")

#     return {
#         "call_id": call.id,
#         "patient": {
#             "id": patient.id if patient else None,
#             "name": patient.name if patient else None,
#             "phone": patient.phone if patient else None,
#         },
#         "transcript": {"conversation": conversation, "call_ended_at": to_ist_iso(call.ended_at)},
#         "summary": summary,
#         "costs": costs,
#         "duration": call.duration or 0,
#         "created_at": to_ist_iso(call.created_at),
#     }



# from src.db import schemas as auth_schemas  # reuse the ones we added

# @app.post("/auth/signup", response_model=auth_schemas.TokenResponse)
# def signup(body: auth_schemas.SignupRequest, db: Session = Depends(get_db)):
#     # 1) find or create hospital
#     hospital = db.query(Hospital).filter(Hospital.name == body.hospital_name.strip()).first()
#     if not hospital:
#         hospital = Hospital(name=body.hospital_name.strip())
#         db.add(hospital)
#         db.commit()
#         db.refresh(hospital)

#     # 2) ensure email unique
#     existing = db.query(User).filter(User.email == body.email.lower().strip()).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Email already registered")

#     # 3) create user
#     user = User(
#         email=body.email.lower().strip(),
#         password_hash=hash_password(body.password),
#         hospital_id=hospital.id
#     )
#     db.add(user)
#     db.commit()
#     db.refresh(user)

#     # 4) issue token
#     token = create_access_token({"sub": str(user.id), "email": user.email, "hospital_id": user.hospital_id})
#     return auth_schemas.TokenResponse(
#         access_token=token,
#         user=auth_schemas.AuthUser(id=user.id, email=user.email, hospital_id=user.hospital_id)
#     )

# @app.post("/auth/login", response_model=auth_schemas.TokenResponse)
# def login(body: auth_schemas.LoginRequest, db: Session = Depends(get_db)):
#     user = db.query(User).filter(User.email == body.email.lower().strip()).first()
#     if not user or not verify_password(body.password, user.password_hash):
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     token = create_access_token({"sub": str(user.id), "email": user.email, "hospital_id": user.hospital_id})
#     return auth_schemas.TokenResponse(
#         access_token=token,
#         user=auth_schemas.AuthUser(id=user.id, email=user.email, hospital_id=user.hospital_id)
#     )

# @app.get("/auth/me", response_model=auth_schemas.AuthUser)
# def me(current_user: User = Depends(get_current_user)):
#     return auth_schemas.AuthUser(
#         id=current_user.id, email=current_user.email, hospital_id=current_user.hospital_id
#     )

import os
import json
import requests
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, HTTPException, Body, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from fastapi.encoders import jsonable_encoder

from src.db.database import get_db, init_db, engine
from src.db import crud, schemas
from src.db.models import Patient, Call, User
from src.app.security import get_current_user

# ------------------------------------------------------------
# 🌏 Timezone Helpers (IST)
# ------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

def to_ist_iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).isoformat()


# ------------------------------------------------------------
# 🚀 FastAPI Setup
# ------------------------------------------------------------
app = FastAPI(title="Hospital Voice Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
        "https://localhost:3000",
        "http://127.0.0.1:3000",
        "https://127.0.0.1:3000",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    print("✅ Starting up FastAPI app")
    init_db()

    # --- MIGRATION: add hospital_id to patients ---
    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='patients' AND column_name='hospital_id'
                ) THEN
                    ALTER TABLE patients ADD COLUMN hospital_id INTEGER NULL;
                END IF;
            END $$;
        """))

        conn.execute(text("""
            UPDATE patients
            SET hospital_id = 1
            WHERE hospital_id IS NULL
              AND EXISTS (SELECT 1 FROM hospitals WHERE id = 1);
        """))

    print("📦 DB migration for hospital_id done.")


@app.get("/healthz")
def health_check():
    return {"status": "ok", "message": "FastAPI running successfully"}


# ------------------------------------------------------------
# 👥 Patient Endpoints
# ------------------------------------------------------------
@app.post("/patients", response_model=schemas.Patient)
def create_patient(
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patient = crud.get_or_create_patient(
        db,
        name=payload.name,
        phone=payload.phone,
        language=payload.language,
        age=payload.age,
        hospital_id=user.hospital_id
    )
    return patient


@app.get("/patients")
def get_patients(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    results = (
        db.query(Patient, func.count(Call.id).label("call_count"))
        .outerjoin(Call, Patient.id == Call.patient_id)
        .filter(Patient.hospital_id == user.hospital_id)
        .group_by(Patient.id)
        .order_by(Patient.id.desc())
        .all()
    )

    data = [
        {
            "id": p.id,
            "name": p.name,
            "phone": p.phone,
            "age": p.age,
            "language": p.language,
            "patient_type": p.patient_type,
            "custom_questions": p.custom_questions,
            "created_at": p.created_at,
            "call_count": count,
        }
        for p, count in results
    ]
    return JSONResponse(content=jsonable_encoder(data))


@app.get("/patients/{patient_id}/calls")
def get_patient_calls(
    patient_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.hospital_id == user.hospital_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    calls = db.query(Call).filter(Call.patient_id == patient_id).order_by(Call.created_at.desc()).all()

    call_data = []
    for c in calls:
        # Default cost
        total_cost = 0.0

        # Fetch cost if execution_id exists
        if c.execution_id:
            try:
                bolna_url = f"https://api.bolna.ai/executions/{c.execution_id}"
                headers = {"Authorization": f"Bearer {BOLNA_API_KEY}"}
                res = requests.get(bolna_url, headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    total_cost = round(data.get("total_cost", 0) / 100, 4)
            except Exception as e:
                print(f"⚠️ Failed to fetch Bolna cost for call {c.id}: {str(e)}")

        call_data.append({
            "call_id": c.id,
            "status": c.status,
            "duration": c.duration or 0,
            "started_at": to_ist_iso(c.started_at),
            "ended_at": to_ist_iso(c.ended_at),
            "cost": total_cost,
        })

    return {"patient_name": patient.name, "calls": call_data}


# ------------------------------------------------------------
# 📞 Bolna API Integration
# ------------------------------------------------------------
BOLNA_API_URL = "https://api.bolna.ai/call"
BOLNA_API_KEY = os.getenv("BOLNA_API_KEY")
BOLNA_AGENT_ID = os.getenv("BOLNA_AGENT_ID")
BOLNA_FROM_NUMBER = os.getenv("BOLNA_FROM_NUMBER", "+911234567890")


@app.post("/dial")
def dial_patient(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    patient_id = body.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")

    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.hospital_id == user.hospital_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    call = crud.create_call(db, patient_id=patient.id, status="initiated")

    payload = {
        "agent_id": BOLNA_AGENT_ID,
        "recipient_phone_number": patient.phone,
        "from_phone_number": BOLNA_FROM_NUMBER,
        "user_data": {
            "patient_id": patient.id,
            "call_id": call.id,
            "patient_name": patient.name,
            "language": patient.language,
            "custom_questions": patient.custom_questions or [],
        },
    }

    headers = {"Authorization": f"Bearer {BOLNA_API_KEY}", "Content-Type": "application/json"}

    res = requests.post(BOLNA_API_URL, json=payload, headers=headers, timeout=10)
    if res.status_code != 200:
        call.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Bolna error: {res.text}")

    data = res.json()
    call.status = "calling"
    db.commit()
    return {
        "status": "success",
        "bolna_response": data,
        "local_call_id": call.id,
        "patient": {"id": patient.id, "name": patient.name, "phone": patient.phone},
    }


# ------------------------------------------------------------
# 📡 Bolna Webhook Endpoint
# ------------------------------------------------------------
@app.post("/webhook/bolna")
async def bolna_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        print("\n🔔 BOLNA WEBHOOK RECEIVED:")
        # print(json.dumps(data, indent=2))

        status = data.get("status", "unknown")
        transcript = data.get("transcript", "")
        duration = float(data.get("telephony_data", {}).get("duration", 0) or 0)
        extraction = data.get("extracted_data", {})

        context_details = data.get("context_details", {})
        recipient_data = context_details.get("recipient_data", {})
        user_data = data.get("user_data", {})

        local_call_id = recipient_data.get("call_id") or user_data.get("call_id")
        if not local_call_id:
            print("⚠️ No local call_id in webhook payload.")
            return {"status": "warning", "message": "No local call_id"}

        call = db.query(Call).filter(Call.id == local_call_id).first()
        if not call:
            print(f"⚠️ Call {local_call_id} not found in DB.")
            return {"status": "warning", "message": "Call not found"}

        call.status = status
        call.duration = duration
        call.execution_id = data.get("id")
        call.ended_at = datetime.utcnow()
        db.commit()

        if transcript:
            def parse_turns(raw: str):
                turns = []
                role, buf = None, []
                def flush():
                    if role and buf:
                        text = "\n".join(buf).strip()
                        if text:
                            turns.append((role, text))
                for line in (raw or "").splitlines():
                    stripped = line.strip()
                    if stripped.lower().startswith("assistant:"):
                        flush(); role = "assistant"; buf = [stripped.split(":", 1)[1].strip()]
                    elif stripped.lower().startswith("user:"):
                        flush(); role = "user"; buf = [stripped.split(":", 1)[1].strip()]
                    else:
                        buf.append(stripped)
                flush()
                return turns

            for r, txt in parse_turns(transcript):
                crud.save_transcript(db, local_call_id, txt, role=r)

        if extraction:
            crud.save_extraction(db, local_call_id, extraction)
            print(f"🧾 Saved extraction for call {local_call_id}")

        return {"status": "success", "message": "Webhook processed", "call_id": local_call_id}
    except Exception as e:
        print(f"❌ Webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}


# ------------------------------------------------------------
# ☎️ Patient Calls & Cost Report
# ------------------------------------------------------------
# @app.get("/patients/{patient_id}/calls")
# def get_patient_calls(
#     patient_id: int,
#     db: Session = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     patient = db.query(Patient).filter(
#         Patient.id == patient_id,
#         Patient.hospital_id == user.hospital_id
#     ).first()
#     if not patient:
#         raise HTTPException(status_code=404, detail="Patient not found")

#     calls = db.query(Call).filter(Call.patient_id == patient_id).order_by(Call.created_at.desc()).all()
#     call_data = [
#         {
#             "call_id": c.id,
#             "status": c.status,
#             "duration": c.duration or 0,
#             "started_at": to_ist_iso(c.started_at),
#             "ended_at": to_ist_iso(c.ended_at),
#         }
#         for c in calls
#     ]
#     return {"patient_name": patient.name, "calls": call_data}


@app.get("/calls/{call_id}")
def get_call_details(
    call_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call or not call.patient or call.patient.hospital_id != user.hospital_id:
        raise HTTPException(status_code=404, detail="Call not found")

    patient = call.patient
    transcripts = db.query(crud.models.Transcript).filter_by(call_id=call_id).order_by(crud.models.Transcript.id.asc()).all()
    conversation = [{"role": t.role, "content": t.text} for t in transcripts]

    extraction = db.query(crud.models.CallExtraction).filter_by(call_id=call_id).order_by(crud.models.CallExtraction.id.desc()).first()

    summary = {
        "has_pain": getattr(extraction, "has_pain", None),
        "taking_medicines": getattr(extraction, "taking_medicines", None),
        "overall_mood": getattr(extraction, "overall_mood", None),
        "needs_callback": getattr(extraction, "needs_callback", None),
    } if extraction else {}

    costs = {"stt": 0.0, "llm": 0.0, "tts": 0.0, "telephony": 0.0, "infrastructure": 0.0, "total": 0.0}

    if call.execution_id:
        try:
            bolna_url = f"https://api.bolna.ai/executions/{call.execution_id}"
            headers = {"Authorization": f"Bearer {BOLNA_API_KEY}"}
            res = requests.get(bolna_url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                breakdown = data.get("cost_breakdown", {})
                total_cost = data.get("total_cost", 0)
                costs["total"] = round(total_cost / 100, 4)
                for k, v in breakdown.items():
                    if isinstance(v, (int, float)):
                        costs[k] = round(v / 100, 4)
                    elif isinstance(v, dict) and "cost" in v:
                        costs[k] = round(v["cost"] / 100, 4)
        except Exception as e:
            print("⚠️ Failed to fetch Bolna cost:", str(e))

    return {
        "call_id": call.id,
        "patient": {"id": patient.id, "name": patient.name, "phone": patient.phone},
        "transcript": {"conversation": conversation, "call_ended_at": to_ist_iso(call.ended_at)},
        "summary": summary,
        "costs": costs,
        "duration": call.duration or 0,
        "created_at": to_ist_iso(call.created_at),
    }


from fastapi import Depends, HTTPException, Body
from src.app.security import hash_password, verify_password, create_access_token
from src.db import models, schemas
from sqlalchemy.orm import Session

# @app.post("/auth/signup", response_model=schemas.TokenResponse)
# def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
#     # Check if hospital exists
#     hospital = db.query(models.Hospital).filter(models.Hospital.name == body.hospital_name).first()
#     if not hospital:
#         hospital = models.Hospital(name=body.hospital_name)
#         db.add(hospital)
#         db.commit()
#         db.refresh(hospital)

#     # Check if email already exists
#     user = db.query(models.User).filter(models.User.email == body.email).first()
#     if user:
#         raise HTTPException(status_code=400, detail="Email already registered")

#     # Hash password and create user
#     user = models.User(
#         email=body.email,
#         password_hash=hash_password(body.password),
#         hospital_id=hospital.id,
#     )
#     db.add(user)
#     db.commit()
#     db.refresh(user)

#     # Generate JWT
#     token = create_access_token({
#         "sub": str(user.id),
#         "email": user.email,
#         "hospital_id": hospital.id,

#     })

#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {
#             "id": user.id,
#             "email": user.email,
#             "hospital_id": user.hospital_id,
#             "hospital_name": hospital.name,
#         }
#     }


# @app.post("/auth/login", response_model=schemas.TokenResponse)
# def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
#     user = db.query(models.User).filter(models.User.email == body.email).first()
#     if not user or not verify_password(body.password, user.password_hash):
#         raise HTTPException(status_code=401, detail="Invalid credentials")

#     token = create_access_token({
#         "sub": str(user.id),
#         "email": user.email,
#         "hospital_id": user.hospital_id
#     })
#     hospital = db.query(models.Hospital).filter(models.Hospital.id == user.hospital_id).first()

#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {
#             "id": user.id,
#             "email": user.email,
#             "hospital_id": user.hospital_id,
#             "hospital_name": hospital.name if hospital else None
#         }
#     }


# ------------------------------------------------------------
# AUTH ENDPOINTS
# ------------------------------------------------------------
from src.app.security import hash_password, verify_password, create_access_token

@app.post("/auth/signup", response_model=schemas.TokenResponse)
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    hospital = db.query(models.Hospital).filter(models.Hospital.name == body.hospital_name).first()

    if not hospital:
        hospital = models.Hospital(name=body.hospital_name)
        db.add(hospital)
        db.commit()
        db.refresh(hospital)

    existing_user = db.query(models.User).filter(models.User.email == body.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=body.email,
        password_hash=hash_password(body.password),
        hospital_id=hospital.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "hospital_id": user.hospital_id
    })

    print("✅ Signup returning hospital:", hospital.name)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "hospital_id": user.hospital_id,
            "hospital_name": hospital.name
        }
    }


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    hospital = db.query(models.Hospital).filter(models.Hospital.id == user.hospital_id).first()

    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "hospital_id": user.hospital_id
    })

    print("✅ Login returning hospital:", hospital.name if hospital else "None")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "hospital_id": user.hospital_id,
            "hospital_name": hospital.name if hospital else None
        }
    }


@app.get("/auth/me", response_model=schemas.AuthUser)
def me(current_user: models.User = Depends(get_current_user)):
    return schemas.AuthUser(
        id=current_user.id,
        email=current_user.email,
        hospital_id=current_user.hospital_id
    )







@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    success = crud.delete_patient(db, patient_id)
    if not success:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"status": "deleted"}
