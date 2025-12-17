from typing import Dict, List
from fastapi import APIRouter

from app.schemas.language_schemas import Language
from app.translations.language_code import LANGUAGE_NAMES, LanguageCode


router = APIRouter(tags=["languages"])

@router.get("/languages", response_model=List[Language])
def get_languages():
    """Returns a list of all available languages"""
    return [
        Language(
            name=LANGUAGE_NAMES[lang],
            code=lang.value
        )
        for lang in LanguageCode
    ]

@router.get("/language-codes")
def get_language_codes() -> List[str]:
    """Returns just the language codes"""
    return [lang.value for lang in LanguageCode]