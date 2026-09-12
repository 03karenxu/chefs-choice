from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.orm import Session

from app import services
from app.db import get_db
from app.enums import PriceLevel, SortField, SortOrder, BestValueMethod
from app.schemas import (
    RestaurantResponse,
    RestaurantTypesResponse,
    RestaurantTypeStatResponse
)

router = APIRouter(prefix="/restaurants")


@router.get("/", response_model=list[RestaurantResponse])
def get_restaurants(
    type: str | None = None,
    price_level: PriceLevel | None = None,
    sort_by: SortField | None = None,
    order: SortOrder | None = None,
    db: Session = Depends(get_db)
) -> list[RestaurantResponse]:

    return services.get_restaurants(
        db=db,
        type=type,
        priceLevel=price_level,
        sort_by=sort_by or SortField.RATING,
        order=order or SortOrder.DESC
    )

@router.get("/types", response_model=RestaurantTypesResponse)
def get_restaurant_types(db: Session = Depends(get_db)) -> RestaurantTypesResponse:
    types = services.get_distinct_types(db=db)
    return {"types": types, "count": len(types)}

@router.get("/types/stats", response_model=list[RestaurantTypeStatResponse])
def get_type_stats(db: Session = Depends(get_db)) -> list[RestaurantTypeStatResponse]:
    return services.get_type_stats(db=db)

@router.get("/best", response_model=list[RestaurantResponse])
def get_best_restaurants(
    method: BestValueMethod = BestValueMethod.BAYESIAN,
    limit: int = 10,
    db: Session = Depends(get_db)
) -> list[RestaurantResponse]:
    return services.get_best_value_restaurants(db=db, method=method, limit=limit)

@router.get("/{id}", response_model=RestaurantResponse)
def get_restaurant_by_id(id: str, db: Session = Depends(get_db)) -> RestaurantResponse:
    result = services.get_restaurant_by_id(id=id, db=db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Restaurant with id {id} not found"
        )
    else:
        return result

