from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

app = FastAPI(
    title="AI-Powered Technical Project Manager API",
    description="Backend API services for context-centric multi-agent coordination.",
    version="1.0.0",
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing AI-TPM API service...")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AI-TPM API service...")

@app.get("/health", status_code=200)
async def health_check():
    """
    Service health check endpoint.
    """
    logger.debug("Health check requested.")
    return {
        "status": "healthy",
        "service": "ai-tpm-backend"
    }
