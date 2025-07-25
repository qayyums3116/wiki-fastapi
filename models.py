# models.py
from pydantic import BaseModel, SecretStr
from typing import Optional

class WikipediaCredentials(BaseModel):
    username: str
    password: SecretStr
    store_bot_only: bool = True

class PublishRequest(WikipediaCredentials):
    title: str
    content: str
    summary: Optional[str] = None
    use_template: bool = False
    template_name: Optional[str] = "product_wiki.txt"
    template_context: Optional[dict] = None

class PublishResponse(BaseModel):
    status: str
    page_title: str
    revision_id: Optional[int] = None
    url: Optional[str] = None
    bot_password_created: bool = False
    message: Optional[str] = None
    warnings: Optional[list[str]] = None