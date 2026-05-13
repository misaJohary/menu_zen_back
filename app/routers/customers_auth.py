from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError

from app.configs.database_configs import SessionDep
from app.models.models import Customer
from app.schemas.customer_schemas import (
    CustomerCreate,
    CustomerPasswordChange,
    CustomerPublic,
    CustomerToken,
    CustomerUpdate,
)
from app.services.customer_auth_service import (
    authenticate_customer,
    create_customer_token,
    get_current_customer,
    get_customer_by_email,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/register", response_model=CustomerToken, status_code=status.HTTP_201_CREATED)
def register_customer(payload: CustomerCreate, session: SessionDep) -> CustomerToken:
    if get_customer_by_email(session, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    customer = Customer(
        email=payload.email,
        phone=payload.phone,
        full_name=payload.full_name,
        hashed_psd=hash_password(payload.password),
    )
    session.add(customer)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    session.refresh(customer)

    token = create_customer_token(customer)
    return CustomerToken(
        access_token=token,
        customer=CustomerPublic.model_validate(customer, from_attributes=True),
    )


@router.post("/login", response_model=CustomerToken)
def login_customer(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> CustomerToken:
    customer = authenticate_customer(session, form_data.username, form_data.password)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/phone or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if customer.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account disabled",
        )
    token = create_customer_token(customer)
    return CustomerToken(
        access_token=token,
        customer=CustomerPublic.model_validate(customer, from_attributes=True),
    )


@router.get("/me", response_model=CustomerPublic)
def read_me(
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerPublic:
    return CustomerPublic.model_validate(current, from_attributes=True)


@router.patch("/me", response_model=CustomerPublic)
def update_me(
    payload: CustomerUpdate,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> CustomerPublic:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(current, field, value)
    current.updated_at = datetime.now()
    session.add(current)
    session.commit()
    session.refresh(current)
    return CustomerPublic.model_validate(current, from_attributes=True)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: CustomerPasswordChange,
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> None:
    if not verify_password(payload.old_password, current.hashed_psd):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )
    current.hashed_psd = hash_password(payload.new_password)
    current.updated_at = datetime.now()
    session.add(current)
    session.commit()
    return None


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def disable_me(
    session: SessionDep,
    current: Annotated[Customer, Depends(get_current_customer)],
) -> None:
    current.disabled = True
    current.updated_at = datetime.now()
    session.add(current)
    session.commit()
    return None
