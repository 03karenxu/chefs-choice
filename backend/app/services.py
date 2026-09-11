from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models import Restaurant, PriceLevel
from sqlalchemy import asc, desc

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class SortField(str, Enum):
    RATING = "rating"
    PRICE = "price"
    NAME = "name"

FIELD2COL = {
    SortField.RATING: Restaurant.rating,
    SortField.PRICE: Restaurant.priceLevel,
    SortField.NAME: Restaurant.name,
}

ORDER2FUNC = {
    SortOrder.ASC: asc,
    SortOrder.DESC: desc
}

# ------------------------------------------------------------------------------

def get_all_restaurants(
    db: Session,
    sort_by: SortField = SortField.RATING,
    order: SortOrder = SortOrder.DESC
) -> list[Restaurant]:
    """
    returns all restaurants
    """
    column = FIELD2COL[sort_by]
    direction = ORDER2FUNC[order]

    return db.scalars(
        select(Restaurant)
        .order_by(direction(column).nulls_last())
    ).all()


def get_restaurant_by_id(id: str, db: Session) -> Restaurant | None:
    """
    gets single restaurant by restaurant id, returns none if not found
    """
    return db.scalars(
        select(Restaurant).where(Restaurant.id == id)
    ).one_or_none()


def get_restaurants_by_type(
    type: str,
    db: Session,
    sort_by: SortField = SortField.RATING,
    order: SortOrder = SortOrder.DESC
) -> list[Restaurant]:
    """
    returns all restaurant records of the specified type
    """
    column = FIELD2COL[sort_by]
    direction = ORDER2FUNC[order]

    return db.scalars(
        select(Restaurant)
        .where(Restaurant.type == type)
        .order_by(direction(column).nulls_last())
    ).all()

def get_restaurants_by_price_level(
    price_level: PriceLevel,
    db: Session,
    sort_by: SortField = SortField.RATING,
    order: SortOrder = SortOrder.DESC
) -> list[Restaurant]:
    """
    returns all restaurant records with the specified price level
    """
    direction = ORDER2FUNC[order]
    column = FIELD2COL[sort_by]
    return db.scalars(
        select(Restaurant)
        .where(Restaurant.priceLevel == price_level)
        .order_by(direction(column))
    ).all()


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