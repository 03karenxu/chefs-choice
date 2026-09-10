from app.db import Base
from sqlalchemy import Column, Float, String, Numeric, Integer

class Restaurant(Base):
    __tablename__="restaurants"

    id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50))
    address = Column(String(200))
    lat = Column(Float)
    lng = Column(Float)
    priceLevel = Column(String(50))
    princeRange = Column(String(20))
    rating = Column(Numeric(2,1))
    userRatingCount = Column(Integer)