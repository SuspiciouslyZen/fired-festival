import logging
import os
import uvicorn
from src.api.routes import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n  UI:    http://localhost:{port}/static/trigger.html")
    print(f"  Agent: selected per-request via UI or agent_type field\n")
    reload = os.environ.get("ENV", "development") != "production"
    uvicorn.run("src.api.routes:app", host="0.0.0.0", port=port, reload=reload)
