from pydantic import BaseModel, ConfigDict, field_validator

from app.models.preferences import AccentColor, Appearance, PreferenceLocale


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    accent_color: AccentColor = AccentColor.PURPLE
    appearance: Appearance = Appearance.LIGHT
    locale: PreferenceLocale = PreferenceLocale.EN


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accent_color: AccentColor | None = None
    appearance: Appearance | None = None
    locale: PreferenceLocale | None = None

    @field_validator("accent_color", "appearance", "locale")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Preference values cannot be null")
        return value
