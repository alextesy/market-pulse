from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Market Pulse Radar",
    description=(
        "A compact, production‑flavored web app that turns news + social chatter "
        "into per‑ticker signals"
    ),
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Market Pulse Radar API", "version": "0.1.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for docker-compose healthcheck."""
    return {"status": "healthy", "service": "market-pulse-api"}


@app.get("/metrics")
async def metrics() -> dict[str, str]:
    """Prometheus metrics endpoint."""
    # TODO: Add actual metrics collection
    return {"status": "metrics endpoint ready"}
