import pandas as pd
from graphdatascience import GraphDataScience
import logging
import math

# --- Configuration ---
BATCH_SIZE = 1000  # number of updates per batch
THRESHOLD_DATE = '2025-06-10'

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def clean_value(value):
    """
    Normalize values by stripping whitespace and quotes, convert NaN to None.
    """
    if pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip().strip('"').strip()
        return cleaned or None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def update_end_applicability(csv_file, gds):
    """
    Reads endApplicability CSV, matches Law nodes by act, sets endApplicabilityDate,
    and updates validity to 'Abrogated' if endApplicabilityDate < THRESHOLD_DATE.
    """
    try:
        df = pd.read_csv(csv_file, comment='/', keep_default_na=True, na_values=['', 'NULL', 'NaN'])
    except Exception as e:
        logging.error(f"Error reading CSV {csv_file}: {e}")
        return

    # clean header names
    df.columns = [col.strip().strip('"').strip() for col in df.columns]

    batch = []
    total = 0
    for idx, row in df.iterrows():
        act_val = clean_value(row.get('RU_URI'))
        if not act_val:
            logging.warning(f"Skipping row {idx+1}: missing RU_URI")
            continue
        date_val = clean_value(row.get('rsDateEndApplicability'))
        batch.append({'act': act_val, 'endApplicabilityDate': date_val})
        if len(batch) >= BATCH_SIZE:
            _run_batch(batch, gds)
            total += len(batch)
            logging.info(f"Updated batch of {len(batch)} nodes; total updated: {total}")
            batch.clear()
    if batch:
        _run_batch(batch, gds)
        total += len(batch)
        logging.info(f"Updated final batch of {len(batch)} nodes; total updated: {total}")


def _run_batch(batch, gds):
    cypher = f"""
    UNWIND $batch AS row
    MATCH (l:Law {{act: row.act}})
    SET l.endApplicabilityDate = CASE WHEN row.endApplicabilityDate IS NOT NULL THEN date(row.endApplicabilityDate) ELSE l.endApplicabilityDate END,
        l.validity = CASE WHEN row.endApplicabilityDate IS NOT NULL AND date(row.endApplicabilityDate) < date($threshold) THEN 'Abrogated' ELSE l.validity END
    """
    try:
        gds.run_cypher(cypher, {'batch': batch, 'threshold': THRESHOLD_DATE})
    except Exception as e:
        logging.error(f"Batch update failed: {e}")


if __name__ == '__main__':
    from dotenv import load_dotenv
    import os
    load_dotenv()
    
    logging.info("Starting end applicability update script.")
    NEO4J_URI = os.getenv("NEO4J_URI", 'bolt://localhost:49879')
    NEO4J_USER = os.getenv("NEO4J_USER", 'neo4j')
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", 'itlawskg')
    NEO4J_AUTH = (NEO4J_USER, NEO4J_PASSWORD)
    CSV_FILE = './raw_data/endApplicability_merged.csv'
    try:
        with GraphDataScience(NEO4J_URI, auth=NEO4J_AUTH) as gds:
            logging.info(f"Connected to Neo4j at {NEO4J_URI}")
            update_end_applicability(CSV_FILE, gds)
    except Exception as e:
        logging.critical(f"Critical error: {e}")
    logging.info("End applicability update script finished.")