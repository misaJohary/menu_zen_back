from enum import Enum


class LanguageCode(str, Enum):
    FRENCH = "fr"
    ENGLISH = "en"
    CHINESE = "ch"

LANGUAGE_NAMES = {
    LanguageCode.FRENCH: "French",
    LanguageCode.ENGLISH: "English",
    LanguageCode.CHINESE: "Chinese"
}