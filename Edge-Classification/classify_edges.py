import json
import os
from weakref import ref
import pandas as pd
import re
from pathlib import Path
import logging
from datetime import datetime

# Attempt to import BERTedgeReclassifier from the same directory
try:
    from BERTfunctions import BERTedgeReclassifier
except ImportError:
    logging.error("Could not import BERTedgeReclassifier. Make sure BERTfunctions.py is in the same directory.")
    BERTedgeReclassifier = None # Placeholder to allow script structure

# --- Configuration ---
BASE_JSON_DIR = Path("./LawsDocs/processed/JSONs_split_with_fn_placeholders_in")
# Define a new output directory
OUTPUT_JSON_DIR = Path("./LawsDocs/processed/JSONs_classified_edges") 
RS_RU_MAPPING_FILE = Path("./raw_data/RS_RU_mapping.json")
COMPLETE_DB_FILE = Path("./raw_data/complete_DB.csv")
# If your BERT model's classification method needs the edge_labels.csv, load it here.
# BERT_LABELS_FILE = Path("./ClassifyEdges/edge_labels.csv")


CONTEXT_TEXT_WINDOW_SIZE = 200  # Number of characters around the placeholder (100 before, 100 after)

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

MONTH_MAP_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile", 5: "maggio", 6: "giugno",
    7: "luglio", 8: "agosto", 9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"
}

def load_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading JSON file {file_path}: {e}")
        return None

def save_json_file(data, file_path):
    try:
        # Ensure the output directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        # logging.info(f"Successfully saved updated JSON to {file_path}")
    except Exception as e:
        logging.error(f"Error saving JSON file {file_path}: {e}")

def get_search_text_for_db(ref_details, rs_ru_map):
    """Formats the reference text for DB lookup based on its type."""
    ref_type = ref_details.get('type')
    ref_text_original = ref_details.get('text')

    if not ref_text_original:
        logging.warning(f"Reference text is missing for fn_number {ref_details.get('fn_number')}")
        return None
    if ref_text_original == "101" and not ref_type:
        ref_type = "RS"  

    if ref_type in ["RU", "FF"]:
        return f"{ref_type} {ref_text_original}"
    elif ref_type == "RS":
        if ref_text_original in rs_ru_map:
            return rs_ru_map[ref_text_original]
        else:
            logging.warning(f"RS number '{ref_text_original}' not found in RS_RU_mapping. Using original RS number for search.")
            # Depending on how your DB is structured, you might want to search for the RS number directly
            # or return None if an RU label is strictly required.
            return ref_text_original # Or None, or f"RS {ref_text_original}"
    else:
        logging.warning(f"Unknown reference type '{ref_type}' for RS number '{ref_text_original}'. Using original text.")
        return ref_text_original

def get_decision_date_prompt_part(decision_date_str):
    """Formats the decision date into 'Legge del DD month YYYY'."""
    if not decision_date_str or pd.isna(decision_date_str):
        return ""
    try:
        dt_object = datetime.strptime(str(decision_date_str).split(' ')[0], '%Y-%m-%d') # Handle potential time part
        day = dt_object.day
        month_name = MONTH_MAP_IT.get(dt_object.month, str(dt_object.month))
        year = dt_object.year
        return f"Legge del {day} {month_name} {year}\n\n"
    except ValueError as e:
        logging.warning(f"Could not parse decision date '{decision_date_str}': {e}")
        return ""

def get_context_around_placeholder(text, fn_placeholder, window_size):
    """Extracts text around a given placeholder."""
    placeholder_index = text.find(fn_placeholder)
    if placeholder_index == -1:
        logging.warning(f"Placeholder '{fn_placeholder}' not found in text. Using full text as context.")
        return text # Or a snippet from the beginning/end

    half_window = window_size // 2
    start_index = max(0, placeholder_index - half_window)
    # Ensure end_index captures text *after* the placeholder
    end_index = min(len(text), placeholder_index + len(fn_placeholder) + half_window)
    
    context = text[start_index:end_index]
    return context.strip()

def process_json_file_content(json_data, rs_ru_map, complete_db_df, bert_model):
    """Processes sections and their footnote indexes within a single JSON data object."""
    if not bert_model:
        logging.error("BERT model not available. Skipping processing.")
        return json_data # Return original data if model is not loaded

    modified = False
    # Create a deep copy if you want to ensure the original json_data passed in is not modified
    # For this script, modifying in place and returning is fine as we save to a new file.
    # processed_json_data = copy.deepcopy(json_data) 

    for section in json_data.get("sections_list", []): 
        original_fn_indexes = section.get("fn_indexes")
        if not isinstance(original_fn_indexes, list) or not all(isinstance(fn, int) for fn in original_fn_indexes) :
            # If fn_indexes is already processed or not in the expected list format, skip
            # logging.debug(f"Skipping section with fn_indexes: {original_fn_indexes} (already processed or unexpected format)")
            continue

        updated_fn_labels = {}
        references_list = json_data.get("references_list", [])

        for fn_num_original in original_fn_indexes:
            # Find the reference details from references_list
            ref_details = next((ref for ref in references_list if str(ref.get("fn_number")) == str(fn_num_original)), None)

            if not ref_details:
                logging.warning(f"Details for footnote number '{fn_num_original}' not found in references_list. Skipping.")
                updated_fn_labels[str(fn_num_original)] = "ERROR_REF_DETAILS_NOT_FOUND"
                continue

            # 1. Get search text for DB
            search_text_in_db = get_search_text_for_db(ref_details, rs_ru_map)
            if not search_text_in_db:
                logging.warning(f"Could not determine search text for DB for fn_number {fn_num_original}. Skipping.")
                updated_fn_labels[str(fn_num_original)] = "ERROR_DB_SEARCH_TEXT_FAIL"
                continue

            # 2. Find decision date from complete_DB.csv
            matching_rows = complete_db_df[complete_db_df['ruLabel'] == search_text_in_db]
            decision_date_str = None
            if not matching_rows.empty:
                decision_date_str = matching_rows['decisionDate'].iloc[0]
            else:
                logging.warning(f"No match found for ruLabel '{search_text_in_db}' in complete_DB.csv.")

            # 3. Create date part of the prompt
            date_prompt_part = get_decision_date_prompt_part(decision_date_str)

            # 4. Extract context text
            section_text = section.get("text", "")
            fn_placeholder = f"[FN_{fn_num_original}]"
            context_text_part = get_context_around_placeholder(section_text, fn_placeholder, CONTEXT_TEXT_WINDOW_SIZE)

            # 5. Combine for prompt_text
            prompt_text = date_prompt_part + context_text_part
            if not prompt_text.strip():
                logging.warning(f"Generated prompt text is empty for fn_number {fn_num_original}. Skipping BERT query.")
                updated_fn_labels[str(fn_num_original)] = "ERROR_EMPTY_PROMPT"
                continue
            
            # 6. Query BERT model
            label_type = "DEFAULT_BERT_LABEL" # Default if prediction fails
            try:
                # IMPORTANT: Adjust this call based on your BERTedgeReclassifier's actual method
                # If it's model.textWithRef(prompt, labels_df), you'll need to load/pass labels_df
                label_type = bert_model.predict_label(prompt_text)
                # logging.info(f"BERT classification for fn {fn_num_original} (prompt snippet: '{prompt_text[:50]}...'): {label_type}")
            except AttributeError:
                logging.error(f"BERTedgeReclassifier instance does not have a 'predict_label' method. Please implement or adjust.")
                label_type = "ERROR_BERT_METHOD_MISSING"
            except Exception as e:
                logging.error(f"Error during BERT prediction for fn_number {fn_num_original}: {e}")
                label_type = "ERROR_BERT_PREDICTION_FAILED"
            
            updated_fn_labels[str(fn_num_original)] = label_type
            modified = True

        if updated_fn_labels: # Only update if there were processable fn_indexes
            section["fn_indexes"] = updated_fn_labels
            
    if modified:
        logging.info(f"File '{json_data.get('source_file', 'Unknown source')}' was modified and new data will be saved.")
    return json_data # Return the (potentially) modified json_data


def main():
    if not BERTedgeReclassifier:
        logging.critical("BERTedgeReclassifier class not loaded. Exiting.")
        return

    # Ensure output base directory exists
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)

    # Load RS-RU mapping
    rs_ru_map = {}
    if RS_RU_MAPPING_FILE.exists():
        rs_ru_map_data = load_json_file(RS_RU_MAPPING_FILE)
        if rs_ru_map_data:
            rs_ru_map = rs_ru_map_data
    else:
        logging.warning(f"RS_RU_mapping.json not found at {RS_RU_MAPPING_FILE}. RS to RU conversion will be limited.")

    # Load complete_DB.csv
    complete_db_df = None
    if COMPLETE_DB_FILE.exists():
        try:
            complete_db_df = pd.read_csv(COMPLETE_DB_FILE)
            logging.info(f"Loaded complete_DB.csv with {len(complete_db_df)} rows.")
        except Exception as e:
            logging.error(f"Failed to load {COMPLETE_DB_FILE}: {e}")
            return # Cannot proceed without this
    else:
        logging.error(f"{COMPLETE_DB_FILE} not found. Cannot proceed.")
        return

    bert_model = BERTedgeReclassifier()

    processed_files_count = 0
    for subdir, _, files in os.walk(BASE_JSON_DIR):
        # Determine the relative path from the base input directory
        relative_subdir = Path(subdir).relative_to(BASE_JSON_DIR)
        # Construct the corresponding output subdirectory
        output_subdir_path = OUTPUT_JSON_DIR / relative_subdir
        
        for filename in files:
            if filename.endswith(".json"):
                input_json_file_path = Path(subdir) / filename
                output_json_file_path = output_subdir_path / filename
                
                logging.info(f"Processing file: {input_json_file_path}")
                
                json_data = load_json_file(input_json_file_path)
                if json_data:
                    updated_json_data = process_json_file_content(json_data, rs_ru_map, complete_db_df, bert_model)
                    save_json_file(updated_json_data, output_json_file_path) # Save to new location
                    processed_files_count += 1

    logging.info(f"Processing complete. Processed {processed_files_count} JSON files. Output saved to {OUTPUT_JSON_DIR}")

if __name__ == "__main__":
    main()