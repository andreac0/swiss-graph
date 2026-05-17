import pandas as pd
from graphdatascience import GraphDataScience
import logging
import math # To check for NaN specifically if needed, though pd.isna() is better

# --- Configuration ---
BATCH_SIZE = 1000 # Process data in batches for efficiency

# --- Column Name Constants (Updated for new headers) ---
COL_ACT = 'act' # New primary identifier column
COL_TITLE_IT = 'title_it'
COL_TITLE_FR = 'title_fr'
COL_TITLE_DE = 'title_de'
COL_PUB_DATE = 'publicationDate'
COL_DEC_DATE = 'decisionDate'
COL_ENTRY_DATE = 'entryintoforceDate'
COL_NOLONGER_DATE = 'nolongerinforceDate' # New date column
COL_STATUS = 'status'                 # New status column
COL_TYPEDOC_IT = 'typeDoc_it'
COL_TYPEDOC_FR = 'typeDoc_fr'
COL_TYPEDOC_DE = 'typeDoc_de'
COL_RU_LABEL = 'ruLabel' # Previously like an ID
COL_RO_LABEL = 'roLabel' # Previously like an ID
COL_AS_LABEL = 'asLabel' # Previously like an ID

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_value(value):
    """
    Cleans incoming data:
    - Converts pandas NA/NaN/None to Python None.
    - Converts empty strings to None.
    - Strips leading/trailing whitespace from strings.
    """
    if pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    # Handle potential float NaNs that pd.isna might miss in rare cases
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

def populate_db_batched(nodes_file, gds):
    """
    Populates the Neo4j database from a CSV file using batched transactions.
    Uses MERGE to avoid creating duplicate nodes based on the 'act' property.
    Handles missing values gracefully by setting them to null in Neo4j.
    """
    try:
        # Read CSV, explicitly treat common NA strings as NA
        db_population = pd.read_csv(
            nodes_file,
            keep_default_na=True,
            na_values=['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan', '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'n/a', 'nan', 'null']
        )
        logging.info(f"Read {len(db_population)} rows from {nodes_file}")
    except FileNotFoundError:
        logging.error(f"Error: Nodes file not found at {nodes_file}")
        return
    except Exception as e:
        logging.error(f"Error reading CSV file {nodes_file}: {e}")
        return

    # Prepare data for batching - List of dictionaries
    data_batch = []
    total_rows_processed = 0
    nodes_created = 0
    nodes_merged = 0 # Keep track if needed, though MERGE doesn't directly return this

    # Cypher query using UNWIND and MERGE for batch processing and duplicate prevention
    # MERGE finds a node based on 'act' or creates it if it doesn't exist.
    # ON CREATE SET only sets properties when the node is newly created.
    # If you want to UPDATE existing nodes, add an ON MATCH SET clause.
    cypher_query = f"""
    UNWIND $batch AS row
    MERGE (l:Law {{{COL_ACT}: row.act}}) // Use the actual column name constant here for the property key
    ON CREATE SET // Only set properties if the node was just created
        l.title_it = row.title_it,
        l.title_fr = row.title_fr,
        l.title_de = row.title_de,
        l.validity = row.status,
        l.typeLaw_it = row.typeDoc_it,
        l.typeLaw_fr = row.typeDoc_fr,
        l.typeLaw_de = row.typeDoc_de,
        l.itId = row.ruLabel,
        l.frId = row.roLabel,
        l.deId = row.asLabel,
        l.lawId = row.ruLabel,
        // Conditionally convert dates only if they are not null
        l.publicationDate = CASE WHEN row.publicationDate IS NOT NULL THEN date(row.publicationDate) ELSE null END,
        l.decisionDate = CASE WHEN row.decisionDate IS NOT NULL THEN date(row.decisionDate) ELSE null END,
        l.entryintoforceDate = CASE WHEN row.entryintoforceDate IS NOT NULL THEN date(row.entryintoforceDate) ELSE null END,
        l.nolongerinforceDate = CASE WHEN row.nolongerinforceDate IS NOT NULL THEN date(row.nolongerinforceDate) ELSE null END
    // Optional: If you want to *update* existing nodes if found by MERGE, add ON MATCH SET
    // ON MATCH SET
    //    l.title_it = row.title_it, // etc. for all properties you want to update
    """

    for index, row in db_population.iterrows():
        # Clean data and create parameter map for the current row
        # Use .get() with default=None for safety, though clean_value handles pd.isna
        act_value = clean_value(row.get(COL_ACT))

        # --- Crucial Check: Primary Key ---
        # A node MUST have the property used in MERGE. Skip rows without a valid 'act'.
        if act_value is None:
            logging.warning(f"Skipping row {index + 2} due to missing or invalid primary identifier '{COL_ACT}'.")
            continue # Skip this row

        params = {
            # Primary key used for MERGE - MUST NOT BE NULL
            "act": act_value,
            # Other properties
            "title_it": clean_value(row.get(COL_TITLE_IT)),
            "title_fr": clean_value(row.get(COL_TITLE_FR)),
            "title_de": clean_value(row.get(COL_TITLE_DE)),
            "status": clean_value(row.get(COL_STATUS)),
            "typeDoc_it": clean_value(row.get(COL_TYPEDOC_IT)),
            "typeDoc_fr": clean_value(row.get(COL_TYPEDOC_FR)),
            "typeDoc_de": clean_value(row.get(COL_TYPEDOC_DE)),
            "ruLabel": clean_value(row.get(COL_RU_LABEL)),
            "roLabel": clean_value(row.get(COL_RO_LABEL)),
            "asLabel": clean_value(row.get(COL_AS_LABEL)),
             # Clean dates, pass as string or None. Cypher's date() handles conversion.
            "publicationDate": clean_value(row.get(COL_PUB_DATE)),
            "decisionDate": clean_value(row.get(COL_DEC_DATE)),
            "entryintoforceDate": clean_value(row.get(COL_ENTRY_DATE)),
            "nolongerinforceDate": clean_value(row.get(COL_NOLONGER_DATE)), # New date
        }

        data_batch.append(params)

        # When batch is full, execute the Cypher query
        if len(data_batch) >= BATCH_SIZE:
            try:
                # MERGE doesn't easily return created vs matched count without more complex Cypher
                gds.run_cypher(cypher_query, {"batch": data_batch})
                processed_in_batch = len(data_batch)
                total_rows_processed += processed_in_batch
                logging.info(f"Processed batch of {processed_in_batch}. Total processed: {total_rows_processed}")
                data_batch = [] # Reset batch
            except Exception as e:
                logging.error(f"Error processing batch ending at row {index + 2}: {e}")
                # Optional: Decide whether to stop or continue on error
                # return # Stop processing
                data_batch = [] # Clear batch and continue with next

    # Process any remaining items in the last batch
    if data_batch:
        try:
            gds.run_cypher(cypher_query, {"batch": data_batch})
            processed_in_batch = len(data_batch)
            total_rows_processed += processed_in_batch
            logging.info(f"Processed final batch of {processed_in_batch}. Total processed: {total_rows_processed}")
        except Exception as e:
            logging.error(f"Error processing final batch: {e}")

    logging.info(f"Database population attempt complete. Processed {total_rows_processed} CSV rows.")
    # Note: total_rows_processed counts rows attempted from CSV, not necessarily nodes created/merged.


def start_population_script(NODES_FILE, gds):
    logging.info("Starting database population script.")
    try:
        # --- IMPORTANT: Add constraint for uniqueness and performance ---
        # This ensures 'act' is unique at the DB level and helps MERGE performance.
        # Use a specific constraint name for better management.
        constraint_name = "constraint_law_act_unique"
        constraint_query = f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (l:Law) REQUIRE l.{COL_ACT} IS UNIQUE"
        try:
            gds.run_cypher(constraint_query)
            logging.info(f"Unique constraint '{constraint_name}' on :Law({COL_ACT}) ensured.")
        except Exception as e:
            # Catching specific CypherSyntaxError or others might be better
            logging.error(f"Failed to create or verify uniqueness constraint '{constraint_name}': {e}")
            # Decide if you want to proceed without the constraint.
            # raise  # Re-raise if the constraint is absolutely required

        # Proceed with population
        populate_db_batched(NODES_FILE, gds)

    except Exception as e:
        logging.critical(f"Failed to connect to Neo4j or critical error during execution: {e}")

    logging.info("Script finished.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv()

    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:49877")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "itlawskg")
    NEO4J_AUTH = (NEO4J_USER, NEO4J_PASSWORD)
    NODES_FILE = "./raw_data/complete_DB.csv" # Make sure this points to the *new* CSV
    logging.info("Starting database population script.")
    try:
        # Use context manager for automatic connection closing
        with GraphDataScience(NEO4J_URI, auth=NEO4J_AUTH) as gds:
            logging.info(f"Connected to Neo4j at {NEO4J_URI}")

            # --- IMPORTANT: Add constraint for uniqueness and performance ---
            # This ensures 'act' is unique at the DB level and helps MERGE performance.
            # Use a specific constraint name for better management.
            constraint_name = "constraint_law_act_unique"
            constraint_query = f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (l:Law) REQUIRE l.{COL_ACT} IS UNIQUE"
            try:
                gds.run_cypher(constraint_query)
                logging.info(f"Unique constraint '{constraint_name}' on :Law({COL_ACT}) ensured.")
            except Exception as e:
                # Catching specific CypherSyntaxError or others might be better
                logging.error(f"Failed to create or verify uniqueness constraint '{constraint_name}': {e}")
                # Decide if you want to proceed without the constraint.
                # raise  # Re-raise if the constraint is absolutely required

            # Proceed with population
            populate_db_batched(NODES_FILE, gds)

    except Exception as e:
        logging.critical(f"Failed to connect to Neo4j or critical error during execution: {e}")

    logging.info("Script finished.")