from enum import Enum

class SortOrder(str, Enum):
    ASC     = "asc"
    DESC    = "desc"

class SortField(str, Enum):
    RATING  = "rating"
    PRICE   = "price"
    NAME    = "name"
    
class PriceLevel(str, Enum):
    INEXPENSIVE     = "INEXPENSIVE"
    MODERATE        = "MODERATE"
    EXPENSIVE       = "EXPENSIVE"
    VERY_EXPENSIVE  = "VERY_EXPENSIVE"