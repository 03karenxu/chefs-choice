#
# ingests restaurant data from .csv file into psql database
#

import logging
import psycopg2
from pathlib import Path
from app.db import engine, Base
from app.models import Restaurant
from app.config import DATA_DIR, SCRIPTS_DIR, DB_URL

logging.basicConfig(
    filename=SCRIPTS_DIR / "logs" / "ingest_data.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

TABLE_NAME = "restaurants"

def init_tables():
    try:
        Base.metadata.create_all(engine)
        logger.info("Tables created successfully")
    except Exception as e:
        logger.error(f"Could not create tables: {e}")
        raise e
    

def load_from_csv(fp: Path | str):
    """
    copies a csv table into the specified postgres table
    """
    fp = Path(fp)

    if not fp.exists(): raise FileNotFoundError()
    
    conn = engine.raw_connection()
    cur = conn.cursor()

    try:
        with open(fp, "r") as f:
            cur.copy_expert(f"COPY {TABLE_NAME} FROM STDIN WITH CSV HEADER", f)
        conn.commit()
        logger.info(f"Loaded {fp.name} into table {TABLE_NAME}")
    except Exception as e:
        logger.error(f"Error loading file {fp.name} into table {TABLE_NAME}: {e}")
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_tables()
    load_from_csv(DATA_DIR / "ALL_RESTAURANTS.csv")
    logger.info(f"All done!")