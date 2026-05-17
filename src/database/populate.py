import os
from dotenv import load_dotenv
from graphdatascience import GraphDataScience
from .nodes import start_population_script
from .articles import populate_sections_and_citations
import logging

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:49875")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "itlawskg")
NODES_FILE_PATH = "./raw_data/complete_DB.csv"
BASE_ARTICLES_JSON_DIR = "./LawsDocs/processed/JSONs_classified_edges/"
RS_TO_RU_MAPPING_FILE = "./raw_data/RS_RU_mapping.json"
TOPICS_CSV_FILEPATH = "./raw_data/Topics/only_topics.csv" # Added topics file path

# --- Setup Logging ---
# Basic logging configuration, similar to what might be in articles.py or nodes.py
# You might want to centralize logging configuration if this script becomes more complex
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')


def main():
    """
    Main function to orchestrate the database population process.
    """
    driver = None  # Initialize driver to None
    try:
        # Initialize DB connection
        logging.info(f"Attempting to connect to Neo4j at {NEO4J_URI}...")
        driver = GraphDataScience(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), database="neo4j")
        logging.info("Successfully connected to Neo4j.")

        # Call nodes.py to populate the DB
        logging.info(f"Starting Law node population from: {NODES_FILE_PATH}")
        start_population_script(NODES_FILE_PATH, driver)
        logging.info("Finished Law node population.")

        # Add Articles and references to nodes
        logging.info(f"Starting population of sections and citations from base directory: {BASE_ARTICLES_JSON_DIR}")
        # Iterate through subdirectories in the BASE_ARTICLES_JSON_DIR
        for item_name in os.listdir(BASE_ARTICLES_JSON_DIR):
            item_path = os.path.join(BASE_ARTICLES_JSON_DIR, item_name)
            if os.path.isdir(item_path):
                logging.info(f"--- Processing subdirectory for articles: {item_path} ---")
                # Pass TOPICS_CSV_FILEPATH to populate_sections_and_citations
                populate_sections_and_citations(item_path, RS_TO_RU_MAPPING_FILE, driver, TOPICS_CSV_FILEPATH)
                logging.info(f"--- Finished processing subdirectory for articles: {item_path} ---")
            else:
                logging.info(f"Skipping non-directory item: {item_path}")
        logging.info("All subdirectories for articles processed.")

    except Exception as e:
        logging.critical(f"An error occurred during the database population process: {e}", exc_info=True)
    finally:
        if driver:
            driver.close()
            logging.info("Neo4j connection closed.")
        logging.info("Database population script finished.")

if __name__ == "__main__":
    main()