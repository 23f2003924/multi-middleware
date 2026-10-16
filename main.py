import time
from collections import defaultdict
from typing import Dict
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

app = FastAPI()

# --- Configuration ---
ASSIGNED_ORIGIN = "https://app-52d3te.example.com"
# Include the exam page's origin here during verification if different
ALLOWED_ORIGINS = {
    ASSIGNED_ORIGIN,
    "https://example.com",  # Replace/add exam page origin if necessary
}

RATE_LIMIT_BUCKET_SIZE = 10
RATE_LIMIT_WINDOW = 10  # seconds

# In-memory sliding-window rate limit store: client_id -> list of timestamps
rate_limit_store: Dict[str, list] = defaultdict(list)


# --- Middleware 1: Request Context ---
class RequestContextMiddleware(BaseHTTPMiddleware):

  async def dispatch(self, request: Request, call_next):
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
      request_id = str(uuid.uuid4())

    # Store in request state for downstream handlers
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


# --- Middleware 2: Scoped CORS ---
class ScopedCORSMiddleware(BaseHTTPMiddleware):

  async def dispatch(self, request: Request, call_next):
    origin = request.headers.get("Origin")

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
      if origin in ALLOWED_ORIGINS:
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, OPTIONS, PUT, DELETE"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "X-Request-ID, X-Client-Id, Content-Type, Authorization"
        )
        return response
      else:
        return Response(status_code=403)

    response = await call_next(request)

    # Attach ACAO only for allowed origins (no wildcards)
    if origin in ALLOWED_ORIGINS:
      response.headers["Access-Control-Allow-Origin"] = origin

    return response


# Register middleware (Starlette executes middlewares added last first on inbound requests)
app.add_middleware(ScopedCORSMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.get("/ping")
async def ping(request: Request):
  request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
  return {"email": "user@example.com", "request_id": request_id}
