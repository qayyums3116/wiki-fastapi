import os
import requests
from typing import Optional
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()

WIKI_USERNAME = os.getenv("WIKI_USERNAME")
WIKI_BOT_PASSWORD = os.getenv("WIKI_BOT_PASSWORD")
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "PsiCRM/1.0 (https://your-crm-site.com)"
    })

    # Step 1: Get login token
    r1 = session.get(WIKI_API_URL, params={
        "action": "query",
        "meta": "tokens",
        "type": "login",
        "format": "json"
    })
    login_token = r1.json()["query"]["tokens"]["logintoken"]

    # Step 2: Login with bot password
    r2 = session.post(WIKI_API_URL, data={
        "action": "login",
        "lgname": WIKI_USERNAME,
        "lgpassword": WIKI_BOT_PASSWORD,
        "lgtoken": login_token,
        "format": "json"
    })

    if r2.json().get("login", {}).get("result") != "Success":
        raise RuntimeError("Wikipedia login failed")

    return session

def get_csrf_token(session: requests.Session) -> str:
    r = session.get(WIKI_API_URL, params={
        "action": "query",
        "meta": "tokens",
        "format": "json"
    })
    return r.json()["query"]["tokens"]["csrftoken"]

def render_content(template_name: str, **context) -> str:
    env = Environment(loader=FileSystemLoader("content_templates"))
    template = env.get_template(template_name)
    return template.render(**context)

def publish_page(title: str, content: str, summary: str = "Published via CRM") -> dict:
    session = make_session()
    csrf_token = get_csrf_token(session)

    response = session.post(WIKI_API_URL, data={
        "action": "edit",
        "title": title,
        "text": content,
        "token": csrf_token,
        "format": "json",
        "summary": summary,
        "bot": True,
    })

    result = response.json()
    if "edit" in result and result["edit"]["result"] == "Success":
        return {
            "status": "success",
            "page": title,
            "revid": result["edit"]["newrevid"]
        }
    else:
        raise RuntimeError(result)

def copy_page(from_title: str, to_title: str, reason: str = "Publishing final article") -> dict:
    session = make_session()
    csrf_token = get_csrf_token(session)

    # Step 1: Get content from sandbox page
    response = session.get(WIKI_API_URL, params={
        "action": "query",
        "prop": "revisions",
        "titles": from_title,
        "rvslots": "main",
        "rvprop": "content",
        "formatversion": "2",
        "format": "json"
    })

    pages = response.json().get("query", {}).get("pages", [])
    if not pages or "revisions" not in pages[0]:
        raise RuntimeError("Failed to fetch content from sandbox page")

    content = pages[0]["revisions"][0]["slots"]["main"]["content"]

    # 🚫 SAFEGUARD: Prevent copying redirect content
    if content.strip().lower().startswith("#redirect"):
        raise RuntimeError("Sandbox page is a redirect. Remove '#REDIRECT' before moving to main space.")

    # Step 2: Create new article page using fetched content
    create_response = session.post(WIKI_API_URL, data={
        "action": "edit",
        "title": to_title,
        "text": content,
        "token": csrf_token,
        "format": "json",
        "summary": reason,
        "bot": True,
    })

    result = create_response.json()
    if "edit" in result and result["edit"]["result"] == "Success":
        return {
            "status": "success",
            "from": from_title,
            "to": to_title
        }
    else:
        raise RuntimeError(result)
