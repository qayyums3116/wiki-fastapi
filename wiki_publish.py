
import os
import argparse
import logging
import requests
from getpass import getpass
from typing import Optional
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# Configuration
load_dotenv()
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_BOT_SUFFIX = "PsiAdirondackBot"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "content_templates")
DEFAULT_TEMPLATE = "product_wiki.txt"
DEFAULT_SUMMARY = "Automated update via PsiAdirondack CRM"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("wiki_publish.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def make_session() -> requests.Session:
    """Create a configured requests session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "PsiAdirondackBot/2.0 (https://psiadiondack.com; contact@psiadiondack.com)",
        "Accept": "application/json"
    })
    return session

def get_login_token(session: requests.Session) -> str:
    """Retrieve login token from MediaWiki API"""
    try:
        response = session.get(
            WIKI_API_URL,
            params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json"
            }
        )
        response.raise_for_status()
        return response.json()["query"]["tokens"]["logintoken"]
    except Exception as e:
        logger.error(f"Token fetch failed: {str(e)}")
        raise RuntimeError("Could not retrieve login token")

def login(
    session: requests.Session,
    username: str,
    password: str,
    token: str
) -> tuple[str, Optional[str]]:
    """
    Handle Wikipedia login with automatic bot password fallback
    
    Returns:
        tuple: (final_username_used, bot_password_if_created)
    """
    try:
        response = session.post(
            WIKI_API_URL,
            data={
                "action": "login",
                "lgname": username,
                "lgpassword": password,
                "lgtoken": token,
                "format": "json"
            }
        )
        response.raise_for_status()
        
        login_data = response.json().get("login", {})
        if login_data.get("result") == "Success":
            return username, None
            
        if login_data.get("code") == "WrongPass" and "@" not in username:
            logger.info("Attempting bot password creation...")
            bot_username, bot_password = create_bot_password(
                session,
                username,
                password
            )
            return login(
                session,
                bot_username,
                bot_password,
                get_login_token(session)
            )
            
        raise RuntimeError(f"Login failed: {login_data.get('message', 'Unknown error')}")
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise

def create_bot_password(
    session: requests.Session,
    main_username: str,
    main_password: str,
    botname: str = DEFAULT_BOT_SUFFIX
) -> tuple[str, str]:
    """Create a bot password for the user account"""
    try:
        # First login with main credentials
        login_token = get_login_token(session)
        login(session, main_username, main_password, login_token)
        
        # Get CSRF token
        csrf_token = get_csrf_token(session)
        
        # Create bot password
        response = session.post(
            WIKI_API_URL,
            data={
                "action": "botpasswords",
                "format": "json",
                "token": csrf_token,
                "botpasswordname": botname,
                "grants": "editpage,createpage,writeapi",
                "reason": "Automated publishing through PsiAdirondack CRM",
            }
        )
        response.raise_for_status()
        
        result = response.json().get("botpasswords", {})
        if result.get("status") == "success":
            return f"{main_username}@{botname}", result["password"]
            
        raise RuntimeError(result.get("message", "Bot creation failed"))
    except Exception as e:
        logger.error(f"Bot creation error: {str(e)}")
        raise

def get_csrf_token(session: requests.Session) -> str:
    """Retrieve CSRF token for API actions"""
    try:
        response = session.get(
            WIKI_API_URL,
            params={
                "action": "query",
                "meta": "tokens",
                "format": "json"
            }
        )
        response.raise_for_status()
        return response.json()["query"]["tokens"]["csrftoken"]
    except Exception as e:
        logger.error(f"CSRF token fetch failed: {str(e)}")
        raise RuntimeError("Could not retrieve CSRF token")

def edit_page(
    session: requests.Session,
    title: str,
    content: str,
    summary: str,
    retries: int = 2
) -> dict:
    """Edit a Wikipedia page with retry logic"""
    for attempt in range(retries + 1):
        try:
            csrf_token = get_csrf_token(session)
            response = session.post(
                WIKI_API_URL,
                data={
                    "action": "edit",
                    "title": title,
                    "text": content,
                    "token": csrf_token,
                    "summary": summary,
                    "format": "json",
                    "bot": True
                }
            )
            response.raise_for_status()
            
            edit_data = response.json().get("edit", {})
            if edit_data.get("result") == "Success":
                return {
                    "success": True,
                    "revid": edit_data.get("newrevid"),
                    "page": title
                }
                
            raise RuntimeError(edit_data.get("message", "Edit failed"))
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < retries:
                logger.warning(f"Rate limited, retrying... (attempt {attempt + 1})")
                continue
            raise
        except Exception as e:
            if attempt < retries:
                logger.warning(f"Edit failed, retrying... (attempt {attempt + 1})")
                continue
            raise

def render_content(template_name: str, **context) -> str:
    """Render content from template"""
    try:
        env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )
        template = env.get_template(template_name)
        return template.render(**context)
    except Exception as e:
        logger.error(f"Template error: {str(e)}")
        raise RuntimeError(f"Could not render template: {str(e)}")

def get_user_credentials() -> tuple[str, str]:
    """Prompt for credentials if not in environment"""
    username = os.getenv("WIKI_USER")
    password = os.getenv("WIKI_PASS")
    
    if not username:
        username = input("Wikipedia username: ").strip()
    if not password:
        password = getpass("Wikipedia password: ").strip()
        
    return username, password

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Publish/update Wikipedia content through PsiAdirondack CRM"
    )
    
    # Authentication
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--username",
        help="Wikipedia username (or set WIKI_USER in .env)"
    )
    auth_group.add_argument(
        "--password",
        help="Wikipedia password (or set WIKI_PASS in .env)"
    )
    
    # Content options
    content_group = parser.add_argument_group("Content Options")
    content_group.add_argument(
        "--title",
        required=True,
        help="Page title (e.g. 'User:Example/sandbox')"
    )
    content_group.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        help=f"Template filename (default: {DEFAULT_TEMPLATE})"
    )
    content_group.add_argument(
        "--summary",
        default=DEFAULT_SUMMARY,
        help="Edit summary"
    )
    
    # Template context
    content_group.add_argument(
        "--name",
        required=True,
        help="Product/service name"
    )
    content_group.add_argument(
        "--desc",
        required=True,
        help="Description content"
    )
    content_group.add_argument(
        "--features",
        nargs="+",
        default=[],
        help="List of features (for template)"
    )
    
    args = parser.parse_args()
    
    try:
        # Get credentials
        username = args.username or os.getenv("WIKI_USER")
        password = args.password or os.getenv("WIKI_PASS")
        
        if not (username and password):
            username, password = get_user_credentials()
        
        # Prepare content
        context = {
            "page_title": args.title,
            "product_name": args.name,
            "description": args.desc,
            "features": args.features
        }
        content = render_content(args.template, **context)
        
        # Execute publishing
        with make_session() as session:
            login_token = get_login_token(session)
            final_username, bot_password = login(
                session,
                username,
                password,
                login_token
            )
            
            result = edit_page(
                session,
                args.title,
                content,
                args.summary
            )
            
            if result["success"]:
                logger.info(
                    f"Successfully updated {args.title}\n"
                    f"Revision ID: {result['revid']}\n"
                    f"Used account: {final_username}"
                )
                if bot_password:
                    logger.info(
                        "Bot password was automatically created. "
                        "Use these credentials for future automated edits:\n"
                        f"Username: {final_username}\n"
                        f"Password: {bot_password}"
                    )
            else:
                raise RuntimeError("Publishing failed")
                
    except Exception as e:
        logger.error(f"Publishing failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()