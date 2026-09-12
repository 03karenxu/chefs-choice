from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from app.enums import PriceLevel

class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str | None
    address: str | None
    lat: float | None
    lng: float | None
    priceLevel: PriceLevel | None
    priceRange: str | None
    rating: Decimal | None
    userRatingCount: int | None

class RestaurantTypesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    types: list[str]
    count: int

class RestaurantTypeStatResponse(BaseModel):
    type: str
    avg_rating: float | None
    count: int