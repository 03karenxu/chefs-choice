#
# ingests restaurant data from .csv file into psql database
#

import os
import logging
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from app.config import DATA_DIR, SCRIPTS_DIR

load_dotenv()

logging.basicConfig(
    filename=SCRIPTS_DIR / "logs" / "ingest_data.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


DB_NAME = os.environ["DB_NAME"]
PG_USER = os.environ["PG_USER"]
TABLE_NAME = "restaurants"


def init_db():
    """
    initializes the table in the specified database
    """
    conn = psycopg2.connect(dbname=DB_NAME, user=PG_USER)
    cur = conn.cursor()

    try:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME}
            (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                type VARCHAR(50),
                address VARCHAR(200),
                lat FLOAT,
                lng FLOAT,
                priceLevel VARCHAR(50),
                priceRange VARCHAR(20),
                rating FLOAT,
                userRatingCount INTEGER
            );
            """
        )
        conn.commit()
        logger.info(f"Created table {TABLE_NAME}")
    except Exception as e:
        logger.error(f"Could not create table {TABLE_NAME}: {e}")
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def load_from_csv(fp: Path | str):
    """
    copies a csv table into the specified postgres table
    """
    fp = Path(fp)

    if not fp.exists(): raise FileNotFoundError()
    
    conn = psycopg2.connect(dbname=DB_NAME, user=PG_USER)
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
    init_db()
    load_from_csv(DATA_DIR / "ALL_RESTAURANTS.csv")
    logger.info(f"All done!")