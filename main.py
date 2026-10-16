import os
import time
import uuid
from collections import deque
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware


# Configuration
EMAIL = os.getenv(
    "EXAM_EMAIL",
    "23f2003924@ds.study.iitm.ac.in",
)

ASSIGNED_ORIGIN = "https://app-52d3te.example.com"
EXAM_PAGE_ORIGIN = os.getenv("EXAM_PAGE_ORIGIN")

ALLOWED_ORIGINS = [ASSIGNED_ORIGIN]

if EXAM_PAGE_ORIGIN and EXAM_PAGE_ORIGIN not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(EXAM_PAGE_ORIGIN)

app = FastAPI()


# 1. Request context middleware
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")

        if not request_id:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


# 2. Per-client rate limiting middleware
class ClientRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit=10, window_seconds=10):
        super().__init__(app)
        self.limit = limit
        self.window_seconds = window_seconds
        self.buckets = {}
        self.lock = Lock()

    async def dispatch(self, request: Request, call_next):
        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.monotonic()

        with self.lock:
            bucket = self.buckets.setdefault(client_id, deque())

            # Remove requests outside the rolling time window.
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()

            # Reject requests exceeding the limit.
            if len(bucket) >= self.limit:
                response = JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                )

                request_id = getattr(request.state, "request_id", None)
                if request_id:
                    response.headers["X-Request-ID"] = request_id

                return response

            bucket.append(now)

        return await call_next(request)


# 3. Register middleware
app.add_middleware(
    ClientRateLimitMiddleware,
    limit=10,
    window_seconds=10,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=[
        "X-Request-ID",
        "X-Client-Id",
        "Content-Type",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)

app.add_middleware(RequestContextMiddleware)


# 4. Health-check endpoint
@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }


# 5. CORS preflight endpoint
@app.options("/ping")
async def ping_options():
    return Response(status_code=204)
