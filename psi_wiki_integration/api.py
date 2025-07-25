import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from wiki_client import publish_page, render_content  # ⛔️ Removed copy_page
import logging
import traceback

# ---------------- Logging Setup ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("wiki-api")

# ---------------- App Setup ----------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------

class PublishRequest(BaseModel):
    title: str  # final article title, unused in sandbox mode
    summary: Optional[str] = None
    use_template: bool = True
    template_name: Optional[str] = "product_wiki.txt"
    template_context: Optional[dict] = {}

# ---------------- Routes ----------------

@app.post("/api/wiki/publish")
def publish_to_sandbox_only(request: PublishRequest):
    try:
        logger.info(f"Publishing request to sandbox for: {request.title}")

        # Step 1: Render wiki content using Jinja2 template
        content = render_content(request.template_name, **request.template_context)

        # Step 2: Publish ONLY to sandbox (no copy step)
        sandbox_title = f"User:{os.getenv('WIKI_USERNAME')}/sandbox"
        logger.info(f"Publishing to sandbox: {sandbox_title}")
        
        result = publish_page(
            title=sandbox_title,
            content=content,
            summary=request.summary or "Staged content in sandbox"
        )

        if result.get("status") != "success":
            raise RuntimeError("Failed to publish to sandbox")

        logger.info("Successfully published to sandbox.")
        return {
            "status": "success",
            "page": sandbox_title,
            "url": f"https://en.wikipedia.org/wiki/{sandbox_title.replace(' ', '_')}"
        }

    except Exception as e:
        logger.error(f"Error during sandbox publish: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
