"""
__main__.py
───────────
Allows running the backend with: python -m pantheon_v2
Port and host are read from settings (which reads from .env).
"""
import uvicorn
from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
