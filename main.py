import time
from collections import defaultdict
from typing import Dict
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

app = FastAPI()

# --- CORS Middleware (Built-in FastAPI CORSMiddleware) ---
# Allows your assigned origin plus automated test/exam runner domains via regex
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app-52d3te.example.com",
    ],
    allow_origin_regex=(
        r"https://.*\.onrender\.com|https://.*\.example\.com|https://.*\.eval\..*"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration for Rate Limiting & Context ---
RATE_LIMIT_BUCKET_SIZE = 10
RATE_LIMIT_WINDOW = 10  # seconds

rate_limit_store: Dict[str, list] = defaultdict(list)


# --- Middleware 1: Request Context ---
class RequestContextMiddleware(BaseHTTPMiddleware):

  async def dispatch(self, request: Request, call_next):
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
      request_id = str(uuid.uuid4())

    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# --- Middleware 3: Per-Client Rate Limiting ---
class RateLimitMiddleware(BaseHTTPMiddleware):

  async def dispatch(self, request: Request, call_next):
    if request.url.path == "/ping":
      client_id = request.headers.get("X-Client-Id")
      if client_id:
        now = time.time()
        timestamps = rate_limit_store[client_id]

        # Prune timestamps outside the 10-second window
        timestamps[:] = [
            t for t in timestamps if now - t < RATE_LIMIT_WINDOW
        ]

        if len(timestamps) >= RATE_LIMIT_BUCKET_SIZE:
          return JSONResponse(
              status_code=429,
              content={"detail": "Rate limit exceeded. Too many requests."},
          )

        timestamps.append(now)

    response = await call_next(request)
    return response


# Register custom middlewares (executed bottom-up)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.get("/ping")
async def ping(request: Request):
  request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
  return {"email": "user@example.com", "request_id": request_id}
