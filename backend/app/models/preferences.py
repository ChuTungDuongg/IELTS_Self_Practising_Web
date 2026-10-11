import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AccentColor(StrEnum):
    PURPLE = "PURPLE"
    INDIGO = "INDIGO"
    BLUE = "BLUE"
    CYAN = "CYAN"
    EMERALD = "EMERALD"
    GREEN = "GREEN"
    AMBER = "AMBER"
    ORANGE = "ORANGE"
    RED = "RED"
    PINK = "PINK"


class Appearance(StrEnum):
    LIGHT = "LIGHT"
    DARK = "DARK"


class PreferenceLocale(StrEnum):
    EN = "EN"
    VI = "VI"


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    accent_color: Mapped[AccentColor] = mapped_column(
        Enum(
            AccentColor, name="preference_accent_color", native_enum=False, create_constraint=True
        ),
        default=AccentColor.PURPLE,
        server_default="PURPLE",
        nullable=False,
    )
    appearance: Mapped[Appearance] = mapped_column(
        Enum(Appearance, name="preference_appearance", native_enum=False, create_constraint=True),
        default=Appearance.LIGHT,
        server_default="LIGHT",
        nullable=False,
    )
    locale: Mapped[PreferenceLocale] = mapped_column(
        Enum(PreferenceLocale, name="preference_locale", native_enum=False, create_constraint=True),
        default=PreferenceLocale.EN,
        server_default="EN",
        nullable=False,
    )
