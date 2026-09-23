from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.domains.profile_targets import calculate_profile_target_band
from app.models.enums import UserRole


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class ProfileFieldsResponse(UserResponse):
    email_verified: bool
    phone_number: str | None
    date_of_birth: date | None
    country: str | None
    city: str | None
    occupation: str | None
    institution: str | None
    target_band: Decimal | None
    target_listening_band: Decimal | None
    target_reading_band: Decimal | None
    target_writing_band: Decimal | None
    target_speaking_band: Decimal | None
    target_test_date: date | None
    bio: str | None

    @model_validator(mode="after")
    def derive_overall_target(self) -> "ProfileFieldsResponse":
        self.target_band = calculate_profile_target_band(
            self.target_listening_band,
            self.target_reading_band,
            self.target_writing_band,
            self.target_speaking_band,
        )
        return self


class ProfileResponse(ProfileFieldsResponse):
    has_password: bool


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=160)
    phone_number: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    country: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    occupation: str | None = Field(default=None, max_length=160)
    institution: str | None = Field(default=None, max_length=200)
    target_listening_band: Decimal | None = None
    target_reading_band: Decimal | None = None
    target_writing_band: Decimal | None = None
    target_speaking_band: Decimal | None = None
    target_test_date: date | None = None
    bio: str | None = Field(default=None, max_length=1000)

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Display name is required")
        return value.strip()

    @field_validator(
        "phone_number", "country", "city", "occupation", "institution", "bio", mode="before"
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @field_validator(
        "target_listening_band",
        "target_reading_band",
        "target_writing_band",
        "target_speaking_band",
    )
    @classmethod
    def validate_band(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (
            not value.is_finite()
            or value < 0
            or value > 9
            or value * 2 != (value * 2).to_integral_value()
        ):
            raise ValueError("Target band must be 0–9 in half-band increments")
        return value


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=256)

    model_config = {"extra": "forbid"}

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Display name is required")
        return stripped


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AuthSessionResponse(BaseModel):
    user: UserResponse
    access_expires_at: datetime


class LogoutResponse(BaseModel):
    logged_out: bool = True
