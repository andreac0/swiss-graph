import pandas as pd
import os
import json
import logging
import re
from collections import defaultdict
from graphdatascience import GraphDataScience


# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add a FileHandler to also log to a file
log_file_path = 'articles_population.log'
file_handler = logging.FileHandler(log_file_path, mode='a') # 'a' for append, 'w' to overwrite each run
file_handler.setLevel(logging.INFO) # You can set a different level for file logging if needed
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logging.getLogger().addHandler(file_handler) # Add the handler to the root logger


# --- Helper function to load topics data ---
def load_topics_data(topics_filepath):
    """Loads topics from a CSV file into a dictionary."""
    topics_map = {}
    try:
        df = pd.read_csv(topics_filepath)
        for _, row in df.iterrows():
            if pd.notna(row.get('id')) and pd.notna(row.get('topics')):
                # Topics are comma-separated; split them into a list of strings
                topics_list = [topic.strip() for topic in str(row['topics']).split(',')]
                topics_map[str(row['id'])] = topics_list
        logging.info(f"Successfully loaded {len(topics_map)} topic entries from {topics_filepath}")
    except FileNotFoundError:
        logging.error(f"Topics file not found: {topics_filepath}")
    except Exception as e:
        logging.error(f"Failed to load or parse topics data from {topics_filepath}: {e}")
    return topics_map

# --- Helper Functions ---
def load_json_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f) # Assuming this was the missing part
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Failed to load JSON {filepath}: {e}")
        return None

def is_annex_file(filename):
    """Check if a file is an annex based on filename."""
    return "Allegato" in filename

def extract_annex_and_parent_ids(filename):
    """
    Extract annex ID and parent law ID from filename.
    Example: 'RU 1998 2847_Allegato_1.json' -> 
    annex_id: 'RU 1998 2847_Allegato_1', parent_law_id: 'RU 1998 2847'
    """
    base = filename.replace(".json", "")
    if "_Allegato_" in base:
        parts = base.split("_Allegato_")
        parent_law_id = parts[0]
        annex_id = base
        return annex_id, parent_law_id
    return None, None

def clean_source_file_to_law_id(source_file_name, to_clean):
    """Converts '1999-181.json' to 'RU 1999 181' or similar."""
    # Assuming source_file is like "YYYY-NNN.json" or "YYYY-NNN_final.json"
    if to_clean:
        base = os.path.splitext(source_file_name)[0].replace("_final", "")
        parts = base.split('-')
        if len(parts) == 2:
            return f"RU {parts[0]} {parts[1]}" # Defaulting to RU for source, adjust if needed
        logging.warning(f"Could not parse LawID from source_file: {source_file_name}")
        return None
    return source_file_name.replace(".json", "")
    
def get_target_law_id_from_reference(reference, rs_to_ru_map):
    """Determines the target LawID from a reference item."""
    ref_type = reference.get("type")
    ref_text = reference.get("text", "") # Raw text like "RU 1999 1321" or "RS 832.20" or "FF 1997"

    if ref_type == "RS":
        # The ref_text for RS type in your example is "RS 832.20", so we remove the RS prefix
        # If ref_text was just "832.20", you'd use it directly."
        rs_source = ref_text.split(" ")[1] if " " in ref_text else ref_text
        target_ru = rs_to_ru_map.get(rs_source) # ref_text should be "RS X.Y.Z"
        if target_ru:
            return target_ru # This is already in "RU YYYY NNN" format
        else:
            # logging.warning(f"RS reference '{ref_text}' not found in RS-to-RU mapping.")
            return None
    elif ref_type == "RU":
        # ref_text is already "RU YYYY NNN"
        return ref_text
    elif ref_type == "FF":
        # FF references usually are "FF YYYY NNNN". Convert to a standard LawID form if necessary.
        # For now, assuming FF references directly map to a LawID if it exists.
        # Or, if FF is not directly a LawID but a document ID you need to look up, adjust here.
        # Let's assume it will be matched directly against existing Law nodes with this ID.
        return f"{ref_type} {ref_text}"
    else:
        # logging.warning(f"Unknown reference type '{ref_type}' or missing type for reference: {reference}")
        return None

def create_annex_node(data, parent_law_id, annex_id, driver):
    """
    Creates an Annex node and HAS_ANNEX relationship from parent Law to Annex.
    Returns True if successful, False otherwise.
    """
    try:
        document_title = data.get("document_title", "")
        sections_list = data.get("sections_list", [])
        num_articles = len(sections_list)
        
        cypher_create_annex = """
        MATCH (parent_law:Law {lawId: $parent_law_id})
        MERGE (a:Annex {annexId: $annex_id})
        ON CREATE SET a.sourceLawId = $parent_law_id, a.title = $title, a.numArt = $num_articles
        ON MATCH SET a.sourceLawId = $parent_law_id, a.title = $title, a.numArt = $num_articles
        MERGE (parent_law)-[r_has:HAS_ANNEX]->(a)
        RETURN id(a) as annex_neo4j_id, id(r_has) as rel_neo4j_id
        """
        
        params_annex = {
            "parent_law_id": parent_law_id,
            "annex_id": annex_id,
            "title": document_title,
            "num_articles": num_articles
        }
        
        result = driver.run_cypher(cypher_create_annex, params_annex)
        if result.empty or result['annex_neo4j_id'].iloc[0] is None:
            logging.error(f"Failed to create Annex {annex_id} or HAS_ANNEX relationship. Parent Law {parent_law_id} might be missing.")
            return False
        
        logging.info(f"Successfully created Annex {annex_id} with {num_articles} articles")
        return True
        
    except Exception as e:
        logging.error(f"Error creating Annex node {annex_id}: {e}")
        return False

# --- Main Neo4j Population Function ---
def populate_sections_and_citations(final_json_dir, rs_to_ru_mapping, driver, topics_csv_filepath): # Added topics_csv_filepath
    """
    Iterates through final JSON files, creates Section nodes with topics, and CITATION relationships
    using dynamic relationship types based on classified fn_indexes.
    """
    rs_to_ru_map = load_json_file(rs_to_ru_mapping)
    if not rs_to_ru_map:
        logging.critical("RS to RU mapping file could not be loaded. Aborting.")
        exit()

    topics_map = load_topics_data(topics_csv_filepath) # Load topics data

    logging.info(f"Starting population of sections and citations from {final_json_dir}...")
    files_processed = 0
    files_missing = [] # Parent Law nodes missing for section creation
    file_undetermined = [] # Source LawID could not be determined from filename
    rs_to_ru_map_missing = set() # Store unique filenames where an RS mapping was missing
    missing_ref_for_index = [] # Store details of fn_indexes that had no corresponding reference_item
    law_not_found_in_db = set()  # Store unique target_law_ids not found during citation creation
    sections_created = 0
    has_article_rels_created = 0
    citation_rels_created = 0
    annexes_created = 0
    has_annex_rels_created = 0

    for filename in os.listdir(final_json_dir):
        if not filename.lower().endswith(".json"):
            continue

        filepath = os.path.join(final_json_dir, filename)
        data = load_json_file(filepath)
        if not data:
            logging.warning(f"Skipping empty or invalid JSON: {filepath}")
            continue
        
        # Check if this is an annex file
        if is_annex_file(filename):
            # Handle annex file
            annex_id, parent_law_id = extract_annex_and_parent_ids(filename)
            if not annex_id or not parent_law_id:
                logging.warning(f"Could not extract annex and parent IDs from {filename}. Skipping.")
                file_undetermined.append(filename)
                continue
            
            # Create annex node first
            if create_annex_node(data, parent_law_id, annex_id, driver):
                annexes_created += 1
                has_annex_rels_created += 1
                
                # Process sections in the annex
                sections = data.get("sections_list", [])
                references = data.get("references_list", [])
                
                refs_by_fn_number = defaultdict(list)
                for ref in references:
                    fn_num_str = str(ref.get("fn_number"))
                    if fn_num_str != "None":
                        refs_by_fn_number[fn_num_str].append(ref)
                
                # Process sections within the annex
                for section_index, section_data in enumerate(sections):
                    section_marker = section_data.get("marker", f"Section_{section_index}")
                    section_title = section_data.get("title", "")
                    section_text = section_data.get("text", "")
                    section_fn_indexes_dict = section_data.get("fn_indexes", {})
                    
                    # Section ID includes annex ID, but sourceLawId points to main law
                    section_node_id = f"{annex_id}/{section_marker}"
                    section_topic = topics_map.get(section_node_id, [])
                    
                    # Create Section Node and HAS_ARTICLE relationship from Annex to Section
                    cypher_create_section_from_annex = """
                    MATCH (parent_annex:Annex {annexId: $annex_id})
                    MERGE (s:Section {sectionId: $section_node_id})
                    ON CREATE SET s.marker = $marker, s.title = $title, s.text = $text, s.sourceLawId = $source_law_id, s.topics = $section_topic
                    ON MATCH SET s.marker = $marker, s.title = $title, s.text = $text, s.sourceLawId = $source_law_id, s.topics = $section_topic
                    MERGE (parent_annex)-[r_has:HAS_ARTICLE]->(s)
                    RETURN id(s) as section_neo4j_id, id(r_has) as rel_neo4j_id
                    """
                    
                    params_section = {
                        "annex_id": annex_id,
                        "section_node_id": section_node_id,
                        "marker": section_marker,
                        "title": section_title,
                        "text": section_text,
                        "source_law_id": parent_law_id,  # Still points to main law
                        "section_topic": section_topic
                    }
                    
                    try:
                        result = driver.run_cypher(cypher_create_section_from_annex, params_section)
                        if result.empty or result['section_neo4j_id'].iloc[0] is None:
                            logging.error(f"Failed to create/merge section {section_node_id} in annex {annex_id}")
                            continue
                        sections_created += 1
                        has_article_rels_created += 1
                        
                        # Process citations for annex sections (same logic as regular sections)
                        if isinstance(section_fn_indexes_dict, dict):
                            for fn_idx_str, citation_label in section_fn_indexes_dict.items():
                                if not isinstance(citation_label, str) or not re.match(r"^[A-Z_]+$", citation_label):
                                    logging.warning(f"Invalid citation label '{citation_label}' for fn_idx '{fn_idx_str}' in annex section '{section_node_id}'. Skipping.")
                                    continue

                                reference_items_list = refs_by_fn_number.get(fn_idx_str, [])
                                if not reference_items_list:
                                    logging.warning(f"No reference items found for fn_idx '{fn_idx_str}' in annex section '{section_node_id}' of {filename}.")
                                    missing_ref_for_index.append(f"{filename} - {section_node_id} - fn_idx {fn_idx_str} (label {citation_label})")
                                    continue

                                unique_targets_for_this_fn_and_label = set()
                                for reference_item in reference_items_list:
                                    target_law_id = get_target_law_id_from_reference(reference_item, rs_to_ru_map)
                                    
                                    if target_law_id and target_law_id not in unique_targets_for_this_fn_and_label:
                                        cypher_create_citation = f"""
                                        MATCH (source_section:Section {{sectionId: $section_node_id}})
                                        MATCH (target_law:Law {{lawId: $target_law_id}})
                                        MERGE (source_section)-[r_cites:{citation_label}]->(target_law)
                                        RETURN id(r_cites) as citation_neo4j_id
                                        """
                                        params_citation = {
                                            "section_node_id": section_node_id,
                                            "target_law_id": target_law_id
                                        }
                                        try:
                                            citation_result = driver.run_cypher(cypher_create_citation, params_citation)
                                            if not citation_result.empty and citation_result['citation_neo4j_id'].iloc[0] is not None:
                                                citation_rels_created += 1
                                                unique_targets_for_this_fn_and_label.add(target_law_id)
                                            else:
                                                law_not_found_in_db.add(target_law_id)
                                        except Exception as e:
                                            logging.error(f"Error creating {citation_label} relationship from annex section {section_node_id} to Law {target_law_id}: {e}")
                                    elif not target_law_id:
                                        rs_to_ru_map_missing.add(filename)
                                        
                    except Exception as e:
                        logging.error(f"Error creating section node for {section_node_id} from annex {annex_id}: {e}")
                        continue
            else:
                logging.error(f"Failed to create annex {annex_id} from {filename}. Skipping sections.")
                continue
        else:
            # Handle regular law file (existing logic)
            source_law_id_str = clean_source_file_to_law_id(data.get("source_file", filename), to_clean=False)
            if not source_law_id_str:
                logging.warning(f"Could not determine source LawID for {filename}. Skipping.")
                file_undetermined.append(filename)
                continue

            sections = data.get("sections_list", [])
            references = data.get("references_list", [])
            
            refs_by_fn_number = defaultdict(list)
            for ref in references:
                fn_num_str = str(ref.get("fn_number"))
                if fn_num_str != "None":
                    refs_by_fn_number[fn_num_str].append(ref)

            for section_index, section_data in enumerate(sections):
                section_marker = section_data.get("marker", f"Section_{section_index}")
                section_title = section_data.get("title", "")
                section_text = section_data.get("text", "")

                section_fn_indexes_dict = section_data.get("fn_indexes", {}) 
                
                # Ensure marker_id doesn't create overly long or problematic node IDs
                section_node_id = f"{source_law_id_str}/{section_marker}"
                section_topic = topics_map.get(section_node_id, [])

                # 1. Create Section Node and HAS_ARTICLE relationship
                cypher_create_section = """
                MATCH (parent_law:Law {lawId: $source_law_id})
                MERGE (s:Section {sectionId: $section_node_id})
                ON CREATE SET s.marker = $marker, s.title = $title, s.text = $text, s.sourceLawId = $source_law_id, s.topics = $section_topic
                ON MATCH SET s.marker = $marker, s.title = $title, s.text = $text, s.sourceLawId = $source_law_id, s.topics = $section_topic
                MERGE (parent_law)-[r_has:HAS_ARTICLE]->(s)
                RETURN id(s) as section_neo4j_id, id(r_has) as rel_neo4j_id
                """
                params_section = {
                    "source_law_id": source_law_id_str,
                    "section_node_id": section_node_id,
                    "marker": section_marker,
                    "title": section_title,
                    "text": section_text,
                    "section_topic": section_topic
                }
                try:
                    result = driver.run_cypher(cypher_create_section, params_section)
                    if result.empty or result['section_neo4j_id'].iloc[0] is None:
                        logging.error(f"Failed to create/merge section or HAS_ARTICLE rel for {section_node_id} in {filename}. Parent Law {source_law_id_str} might be missing.")
                        if source_law_id_str not in files_missing:
                            files_missing.append(source_law_id_str)
                        continue 
                    sections_created +=1 # This might overcount if MERGE matches existing
                    has_article_rels_created +=1 # This might overcount if MERGE matches existing
                except Exception as e:
                    logging.error(f"Error creating/merging section node for {section_node_id} from {filename}: {e}")
                    continue 

                # 2. Create CITATION relationships with dynamic types
                if isinstance(section_fn_indexes_dict, dict):
                    for fn_idx_str, citation_label in section_fn_indexes_dict.items():
                        # Validate the citation_label
                        if not isinstance(citation_label, str) or not re.match(r"^[A-Z_]+$", citation_label):
                            logging.warning(f"Invalid or non-string citation label '{citation_label}' for fn_idx '{fn_idx_str}' in section '{section_node_id}'. Skipping this footnote's citation.")
                            continue

                        reference_items_list = refs_by_fn_number.get(fn_idx_str, [])
                        
                        if not reference_items_list:
                            logging.warning(f"No reference items found in 'references_list' for fn_idx '{fn_idx_str}' (label: {citation_label}) in section '{section_node_id}' of {filename}.")
                            missing_ref_for_index.append(f"{filename} - {section_node_id} - fn_idx {fn_idx_str} (label {citation_label})")
                            continue

                        unique_targets_for_this_fn_and_label = set() 

                        for reference_item in reference_items_list:
                            target_law_id = get_target_law_id_from_reference(reference_item, rs_to_ru_map)
                            
                            if target_law_id:
                                if target_law_id in unique_targets_for_this_fn_and_label:
                                    continue 
                                
                                # Dynamically set relationship type
                                cypher_create_citation = f"""
                                MATCH (source_section:Section {{sectionId: $section_node_id}})
                                MATCH (target_law:Law {{lawId: $target_law_id}})
                                MERGE (source_section)-[r_cites:{citation_label}]->(target_law)
                                RETURN id(r_cites) as citation_neo4j_id
                                """
                                params_citation = {
                                    "section_node_id": section_node_id,
                                    "target_law_id": target_law_id
                                }
                                try:
                                    citation_result = driver.run_cypher(cypher_create_citation, params_citation)
                                    if not citation_result.empty and citation_result['citation_neo4j_id'].iloc[0] is not None:
                                        citation_rels_created += 1
                                        unique_targets_for_this_fn_and_label.add(target_law_id)
                                    else:
                                        # This might happen if target_law doesn't exist
                                        if "RU" in target_law_id or "FF" in target_law_id: # Check common prefixes
                                            logging.warning(f"Could not create/find {citation_label} from {section_node_id} to Law {target_law_id}. Target Law might be missing.")
                                        law_not_found_in_db.add(target_law_id)
                                except Exception as e:
                                    logging.error(f"Error creating {citation_label} relationship from {section_node_id} to Law {target_law_id}: {e}")
                            else: # target_law_id is None
                                rs_to_ru_map_missing.add(filename) 
                else:
                    logging.info(f"section_fn_indexes for {section_node_id} in {filename} is not a dictionary (value: {section_fn_indexes_dict}). No dynamic citation relationships will be created for this section.")
        
        files_processed += 1

    logging.info(f"Finished processing. Files processed: {files_processed}")
    logging.info(f"Files with missing parent Law (for section creation): {len(files_missing)}")
    logging.info(f"Sections created/merged: {sections_created}") # Note: MERGE counts existing too if not careful with increment
    logging.info(f"HAS_ARTICLE relationships created/merged: {has_article_rels_created}") # Same as above
    logging.info(f"Annexes created/merged: {annexes_created}")
    logging.info(f"HAS_ANNEX relationships created/merged: {has_annex_rels_created}")
    logging.info(f"Dynamic CITATION relationships created/merged: {citation_rels_created}")
    logging.info(f"Files with undetermined source LawID: {len(file_undetermined)}")
    logging.info(f"Files with missing RS to RU mapping entries (unique filenames): {len(rs_to_ru_map_missing)}")
    logging.info(f"Missing references_list entries for fn_indexes: {len(missing_ref_for_index)}")
    logging.info(f"Target Law IDs not found in DB for citations (unique IDs): {len(law_not_found_in_db)}")


# --- Main Execution ---
if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv()

    # Directory containing the JSON files with classified fn_indexes
    # This should be the output directory of your article_retrieval.py script
    FINAL_JSON_DIR = "./LawsDocs/processed/JSONs_classified_edges/Legge federale" 
    RS_TO_RU_MAPPING_FILE = "./raw_data/RS_RU_mapping.json" 
    TOPICS_CSV_FILE = "./raw_data/Topics/only_topics.csv" # Path to the topics CSV

    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:49877")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "itlawskg")
    driver = None # Initialize driver
    try:
        driver = GraphDataScience(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), database="neo4j") # Specify database if not default
        logging.info(f"Successfully connected to Neo4j at {NEO4J_URI}")
        
        # Call populate_sections_and_citations with the new topics_csv_filepath argument
        populate_sections_and_citations(FINAL_JSON_DIR, RS_TO_RU_MAPPING_FILE, driver, TOPICS_CSV_FILE)

    except Exception as e:
        logging.critical(f"Failed to connect to Neo4j or critical error during script execution: {e}", exc_info=True)
    finally:
        if driver:
            driver.close()
            logging.info("Neo4j connection closed.")