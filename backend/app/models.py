from decimal import Decimal
from app.db import Base
from app.enums import PriceLevel
from sqlalchemy import Float, String, Numeric, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[str]                         = mapped_column(String(100), primary_key=True)
    name: Mapped[str]                       = mapped_column(String(200))
    type: Mapped[str | None]                = mapped_column(String(50))
    address: Mapped[str | None]             = mapped_column(String(200))
    lat: Mapped[float | None]               = mapped_column(Float)
    lng: Mapped[float | None]               = mapped_column(Float)
    priceLevel: Mapped[PriceLevel | None]   = mapped_column(SQLEnum(PriceLevel))
    priceRange: Mapped[str | None]          = mapped_column(String(20))
    rating: Mapped[Decimal | None]          = mapped_column(Numeric(2, 1))
    userRatingCount: Mapped[int | None]     = mapped_column(Integer)
    bayesianRating: Mapped[Decimal | None]  = mapped_column(Numeric(3, 2))