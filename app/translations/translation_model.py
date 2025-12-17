from sqlmodel import SQLModel

from app.translations.language_code import LanguageCode


class TranslationModel(SQLModel):
    language_code: LanguageCode