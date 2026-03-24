import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    secret_key: str = os.getenv("SECRET_KEY", "fallback-secret-key")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "3000"))
    
    # RBAC Super Admin Defaults
    super_admin_email: Optional[str] = os.getenv("SUPER_ADMIN_EMAIL")
    super_admin_username: str = os.getenv("SUPER_ADMIN_USERNAME", "super_admin")
    super_admin_password: Optional[str] = os.getenv("SUPER_ADMIN_PASSWORD")
    
    class Config:
        env_file = ".env"

settings = Settings()