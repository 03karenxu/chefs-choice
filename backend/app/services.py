from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func, select
from app.models import Restaurant, PriceLevel

class SortOrder(str, Enum):
    ASC     = "asc"
    DESC    = "desc"

class SortField(str, Enum):
    RATING  = "rating"
    PRICE   = "price"
    NAME    = "name"

FIELD2COL = {
    SortField.RATING:   Restaurant.rating,
    SortField.PRICE:    Restaurant.priceLevel,
    SortField.NAME:     Restaurant.name,
}

ORDER2FUNC = {
    SortOrder.ASC:  asc,
    SortOrder.DESC: desc
}

# ------------------------------------------------------------------------------

def get_restaurants(
    db: Session,
    type: str | None                = None,
    priceLevel: PriceLevel | None   = None,
    sort_by: SortField              = SortField.RATING,
    order: SortOrder                = SortOrder.DESC
) -> list[Restaurant]:
    """
    returns all restaurants, with optional type/priceLevel filtering
    """
    column = FIELD2COL[sort_by]
    direction = ORDER2FUNC[order]

    stmt = select(Restaurant)
    if type is not None:
        stmt = stmt.where(Restaurant.type == type)
    if priceLevel is not None:
        stmt = stmt.where(Restaurant.priceLevel == priceLevel)

    return db.scalars(
        stmt
        .order_by(direction(column).nulls_last())
    ).all()


def get_restaurant_by_id(id: str, db: Session) -> Restaurant | None:
    """
    gets single restaurant by restaurant id, returns none if not found
    """
    return db.scalars(
        select(Restaurant).where(Restaurant.id == id)
    ).one_or_none()


def get_distinct_types(db: Session) -> list[str]:
    """
    gets distinct restaurant types ordered by how common they are
    """
    return db.scalars(
        select(Restaurant.type)
        .where(Restaurant.type.is_not(None))
        .group_by(Restaurant.type)
        .order_by(func.count(Restaurant.id).desc())
    ).all()


def get_best_value_restaurants(
    db: Session,
    limit: int = 10
) -> tuple[list[Restaurant], list[Restaurant]]:
    """
    returns the restaurants table in 2 versions
    1. ordered by bayesian average rating
    2. ordered by average rating
    """
    has_data = (
        Restaurant.rating.is_not(None),
        Restaurant.userRatingCount.is_not(None)
    )

    # bayesian rating calculation
    m = db.scalar(
        select(func.avg(Restaurant.rating))
        .where(*has_data)
    )
    C = db.scalar(
        select(func.avg(Restaurant.userRatingCount))
        .where(*has_data)
    )
    v = Restaurant.userRatingCount
    R = Restaurant.rating
    bayesian_avg = (C * m + v * R) / (v + C)

    results_bayesian = db.scalars(
        select(Restaurant)
        .where(*has_data)
        .order_by(bayesian_avg.desc())
        .limit(limit)
    ).all()
    results_avg = db.scalars(
        select(Restaurant)
        .where(*has_data)
        .order_by(Restaurant.rating.desc())
        .limit(limit)
    ).all()

    return results_bayesian, results_avg


def get_stats_by_type(db: Session):
    """
    gets avg rating and number of restaurants for each restaurant type
    """
    return db.execute(
        select(
            Restaurant.type,
            func.avg(Restaurant.rating),
            func.count(Restaurant.id)
        )
        .where(Restaurant.type.is_not(None))
        .group_by(Restaurant.type)
        .order_by(func.count(Restaurant.id).desc())
    ).all()