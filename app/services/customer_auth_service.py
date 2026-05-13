from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.configs.auth_configs import settings
from app.configs.database_configs import get_session
from app.models.models import Customer
from app.services.auth_service import pwd_context


customer_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="customers/login", scheme_name="CustomerOAuth2"
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_customer_token(
    customer: Customer,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": customer.email,
        "customer_id": customer.id,
        "typ": "customer",
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_customer_by_email(session: Session, email: str) -> Optional[Customer]:
    return session.exec(select(Customer).where(Customer.email == email)).first()


def get_customer_by_phone(session: Session, phone: str) -> Optional[Customer]:
    return session.exec(select(Customer).where(Customer.phone == phone)).first()


def authenticate_customer(
    session: Session,
    identifier: str,
    password: str,
) -> Optional[Customer]:
    customer = get_customer_by_email(session, identifier) or get_customer_by_phone(
        session, identifier
    )
    if customer is None:
        return None
    if not verify_password(password, customer.hashed_psd):
        return None
    return customer


def get_current_customer(
    token: Annotated[str, Depends(customer_oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> Customer:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_sub": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise credentials_exception

    if payload.get("typ") != "customer":
        raise credentials_exception

    customer_id = payload.get("customer_id")
    if customer_id is None:
        raise credentials_exception

    customer = session.get(Customer, customer_id)
    if customer is None or customer.disabled:
        raise credentials_exception
    return customer
