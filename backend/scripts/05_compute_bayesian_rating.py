from app.db import SessionLocal
from app.services import compute_bayesian_ratings

if __name__ == "__main__":
    db = SessionLocal()
    try:
        compute_bayesian_ratings(db)
        print("Bayesian ratings recomputed.")
    finally:
        db.close()