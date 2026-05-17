import json
import re
import os
import logging
from collections import defaultdict, Counter


# --- Setup Logging ---
LOG_FILE_PATH = "./scripts/PDF_articles/using_pdf_properties/analysis_stats.log"

# Remove existing handlers if any
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode='w', encoding='utf-8'), # Write to file
        logging.StreamHandler() # Write to console
    ]
)

# --- Helper Functions ---

def load_json_file(filepath):
    """Loads a JSON file with error handling."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Failed to load JSON {filepath}: {e}")
        return None

def roman_to_int(s):
    """Converts a Roman numeral string to an integer."""
    if not s: return None
    s = s.upper()
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    result = 0
    prev_value = 0
    try:
        for numeral in reversed(s):
            value = roman_map[numeral]
            if value < prev_value:
                result -= value
            else:
                result += value
            prev_value = value
        return result
    except KeyError:
        logging.warning(f"Invalid Roman numeral character found in '{s}'")
        return None

def check_sequence_gaps(numbers, sequence_type, filename):
    """Checks for gaps (difference > 1) in a sorted list of unique integers."""
    gaps_found = []
    if len(numbers) > 1:
        for i in range(len(numbers) - 1):
            diff = numbers[i+1] - numbers[i]
            if diff > 1:
                gap_info = f"Gap > 1 found after {numbers[i]} (next is {numbers[i+1]})"
                gaps_found.append(gap_info)
                logging.warning(f"[{filename}] {sequence_type} sequence: {gap_info}")
    return gaps_found

# --- Main Analysis Function ---

def analyze_file_stats(filepath):
    """Analyzes a single final JSON file for statistics."""
    filename = os.path.basename(filepath)
    data = load_json_file(filepath)
    if not data:
        return None # Skip file if loading failed

    stats = defaultdict(list)
    error_flags = defaultdict(bool)

    # --- Basic Checks ---
    if not data.get("document_title"):
        stats["missing_title_files"].append(filename)
        error_flags["missing_title"] = True
        logging.warning(f"[{filename}] Document title is missing or empty.")

    references = data.get("references_list", [])
    sections = data.get("sections_list", [])

    # --- Reference Analysis ---
    fn_numbers_found = []
    fn_number_details = [] # Store tuples (number, is_first_ref)
    duplicate_fn_numbers = Counter()

    for i, ref in enumerate(references):
        is_first_ref = (i == 0)
        fn_num_str = ref.get("fn_number")
        ref_id = ref.get("id", "UNKNOWN_REF_ID")
        
        # Check for missing fn_number
        if fn_num_str is None:
            stats["missing_fn_number"].append({"file": filename, "ref_id": ref_id, "is_first": is_first_ref})
            error_flags["missing_fn_number"] = True
            logging.warning(f"[{filename}] Reference {ref_id} is missing fn_number (Is first ref: {is_first_ref}).")
        else:
            try:
                 fn_num_int = int(fn_num_str)
                 fn_numbers_found.append(fn_num_int)
                 fn_number_details.append((fn_num_int, is_first_ref))
                 duplicate_fn_numbers[fn_num_int] += 1
            except ValueError:
                 logging.warning(f"[{filename}] Reference {ref_id} has non-integer fn_number: '{fn_num_str}'.")
                 stats["invalid_fn_number"].append({"file": filename, "ref_id": ref_id, "value": fn_num_str})
                 error_flags["invalid_fn_number"] = True


        # Check for missing type
        if ref.get("type") is None:
            stats["missing_ref_type"].append({"file": filename, "ref_id": ref_id})
            error_flags["missing_ref_type"] = True
            logging.warning(f"[{filename}] Reference {ref_id} is missing 'type' (RS/FF/RU).")
            
    # Report duplicate fn_numbers
    for num, count in duplicate_fn_numbers.items():
        if count > 1:
             stats["duplicate_fn_number"].append({"file": filename, "fn_number": num, "count": count})
             error_flags["duplicate_fn_number"] = True
             logging.warning(f"[{filename}] Footnote number {num} is duplicated {count} times.")

    # Check for gaps in fn_number sequence
    if fn_numbers_found:
        sorted_unique_fn_nums = sorted(list(set(fn_numbers_found)))
        fn_num_gaps = check_sequence_gaps(sorted_unique_fn_nums, "Footnote Number (fn_number)", filename)
        if fn_num_gaps:
            stats["gaps_in_fn_number"].append({"file": filename, "gaps": fn_num_gaps})
            error_flags["gaps_in_fn_number"] = True

    # --- Section Analysis ---
    all_fn_indexes = []
    art_markers = {} # marker_text -> marker_id
    roman_markers = {}
    arabic_markers = {}
    duplicate_markers = Counter()
    empty_sections = []

    art_pattern = re.compile(r"Art\.\s*(\d+)[a-zA-Z]?") # Extract number
    roman_pattern = re.compile(r"([IVXLCDM]+)") # Extract numeral
    arabic_pattern = re.compile(r"(\d+)\.") # Extract number before dot

    for i, sec in enumerate(sections):
        # Combine fn_indexes from all sections
        all_fn_indexes.extend(sec.get("fn_indexes", []))
        
        marker_text = sec.get("marker", "")
        marker_id = sec.get("marker_id")
        
        # Check for duplicate markers
        if marker_text != "Preamble":
             duplicate_markers[marker_text] += 1
        
        # Check for empty text (ignore Preamble)
        if marker_text != "Preamble" and not sec.get("text", "").strip():
             empty_sections.append({"file": filename, "marker": marker_text, "marker_id": marker_id})
             logging.warning(f"[{filename}] Section '{marker_text}' (ID: {marker_id}) has empty text.")
             error_flags["empty_section"] = True

        # Extract marker numbers for gap checking
        art_match = art_pattern.match(marker_text)
        roman_match = roman_pattern.fullmatch(marker_text) # Use fullmatch for standalone Roman
        arabic_match = arabic_pattern.match(marker_text)

        if art_match:
            try:
                num = int(art_match.group(1))
                if num not in art_markers: art_markers[num] = []
                art_markers[num].append(marker_id or f"section_index_{i}")
            except ValueError:
                 logging.warning(f"[{filename}] Could not parse number from Art marker: '{marker_text}'")
        elif roman_match:
            num = roman_to_int(roman_match.group(1))
            if num is not None:
                if num not in roman_markers: roman_markers[num] = []
                roman_markers[num].append(marker_id or f"section_index_{i}")
        elif arabic_match:
             try:
                 num = int(arabic_match.group(1))
                 if num not in arabic_markers: arabic_markers[num] = []
                 arabic_markers[num].append(marker_id or f"section_index_{i}")
             except ValueError:
                  logging.warning(f"[{filename}] Could not parse number from Arabic marker: '{marker_text}'")

    # Report duplicate markers
    for marker, count in duplicate_markers.items():
        if count > 1:
            stats["duplicate_marker"].append({"file": filename, "marker": marker, "count": count})
            error_flags["duplicate_marker"] = True
            logging.warning(f"[{filename}] Section marker '{marker}' is duplicated {count} times.")
            
    if empty_sections:
         stats["empty_sections"].extend(empty_sections)


    # Check for gaps in fn_indexes sequence
    if all_fn_indexes:
        sorted_unique_fn_idxs = sorted(list(set(all_fn_indexes)))
        fn_idx_gaps = check_sequence_gaps(sorted_unique_fn_idxs, "Superscript Index (fn_indexes)", filename)
        if fn_idx_gaps:
            stats["gaps_in_fn_indexes"].append({"file": filename, "gaps": fn_idx_gaps})
            error_flags["gaps_in_fn_indexes"] = True

    # --- Compare fn_indexes and fn_numbers ---
    set_fn_indexes = set(all_fn_indexes)
    set_fn_numbers = set(fn_numbers_found)

    missing_in_numbers = sorted(list(set_fn_indexes - set_fn_numbers)) # Superscripts without matching ref number
    missing_in_indexes = sorted(list(set_fn_numbers - set_fn_indexes)) # Ref numbers without matching superscript

    if missing_in_numbers:
        stats["indexes_missing_from_numbers"].append({"file": filename, "missing_numbers": missing_in_numbers})
        error_flags["mismatch_indexes_numbers"] = True
        logging.warning(f"[{filename}] Superscript indexes found without matching fn_number: {missing_in_numbers}")

    if missing_in_indexes:
        stats["numbers_missing_from_indexes"].append({"file": filename, "missing_indexes": missing_in_indexes})
        error_flags["mismatch_numbers_indexes"] = True
        logging.warning(f"[{filename}] Reference fn_numbers found without matching superscript index: {missing_in_indexes}")

    # --- Check Gaps in Section Markers ---
    if art_markers:
        art_nums = sorted(art_markers.keys())
        art_gaps = check_sequence_gaps(art_nums, "Art. Marker Number", filename)
        if art_gaps:
            stats["gaps_in_art_markers"].append({"file": filename, "gaps": art_gaps})
            error_flags["gaps_in_art_markers"] = True
            
    if roman_markers:
        roman_nums = sorted(roman_markers.keys())
        roman_gaps = check_sequence_gaps(roman_nums, "Roman Marker Number", filename)
        if roman_gaps:
             stats["gaps_in_roman_markers"].append({"file": filename, "gaps": roman_gaps})
             error_flags["gaps_in_roman_markers"] = True
             
    if arabic_markers:
         arabic_nums = sorted(arabic_markers.keys())
         arabic_gaps = check_sequence_gaps(arabic_nums, "Arabic Marker Number", filename)
         if arabic_gaps:
              stats["gaps_in_arabic_markers"].append({"file": filename, "gaps": arabic_gaps})
              error_flags["gaps_in_arabic_markers"] = True


    # Add filename to list if any error/warning was flagged for it
    if any(error_flags.values()):
         stats["files_with_issues"].append(filename)

    return stats

# --- Main Execution ---
def start_analysis(FINAL_JSON_DIR):
    if not os.path.isdir(FINAL_JSON_DIR):
        logging.error(f"Final JSON directory not found: {FINAL_JSON_DIR}")
    else:
        all_stats = defaultdict(list)
        total_files = 0
        processed_files = 0

        logging.info(f"Starting analysis of files in: {FINAL_JSON_DIR}")
        logging.info(f"Logging statistics to: {LOG_FILE_PATH}")

        for filename in os.listdir(FINAL_JSON_DIR):
            if filename.lower().endswith(".json"):
                total_files += 1
                filepath = os.path.join(FINAL_JSON_DIR, filename)
                logging.info(f"--- Analyzing: {filename} ---")
                file_stats = analyze_file_stats(filepath)
                if file_stats:
                    processed_files += 1
                    # Aggregate stats
                    for key, value in file_stats.items():
                        if isinstance(value, list):
                             all_stats[key].extend(value)
                        else: # Should not happen with defaultdict(list) but safer
                              all_stats[key].append(value) 
                else:
                    logging.error(f"Failed to process {filename}.")

        logging.info(f"--- Analysis Complete ---")
        logging.info(f"Processed {processed_files} out of {total_files} files.")

        # --- Report Aggregated Statistics ---
        logging.info("\n--- AGGREGATED STATISTICS ---")

        # Missing fn_number
        missing_fn_num_count = len(all_stats.get("missing_fn_number", []))
        first_ref_missing_count = sum(1 for item in all_stats.get("missing_fn_number", []) if item.get("is_first"))
        missing_fn_num_files = sorted(list(set(item['file'] for item in all_stats.get("missing_fn_number", []))))
        logging.info(f"References missing fn_number: {missing_fn_num_count}")
        if missing_fn_num_count > 0:
             logging.info(f"  - Instances where the *first* reference was missing fn_number: {first_ref_missing_count}")
             logging.info(f"  - Files affected: {len(missing_fn_num_files)} -> {missing_fn_num_files}")

        # Invalid fn_number (non-integer)
        invalid_fn_num_count = len(all_stats.get("invalid_fn_number", []))
        invalid_fn_num_files = sorted(list(set(item['file'] for item in all_stats.get("invalid_fn_number", []))))
        if invalid_fn_num_count > 0:
             logging.info(f"References with invalid (non-integer) fn_number: {invalid_fn_num_count}")
             logging.info(f"  - Files affected: {len(invalid_fn_num_files)} -> {invalid_fn_num_files}")
             
        # Duplicate fn_number
        duplicate_fn_num_count = len(all_stats.get("duplicate_fn_number", []))
        duplicate_fn_num_files = sorted(list(set(item['file'] for item in all_stats.get("duplicate_fn_number", []))))
        if duplicate_fn_num_count > 0:
            logging.info(f"Instances of duplicate fn_numbers found: {duplicate_fn_num_count}")
            logging.info(f"  - Files affected: {len(duplicate_fn_num_files)} -> {duplicate_fn_num_files}")


        # Mismatches fn_indexes vs fn_numbers
        missing_num_count = len(all_stats.get("indexes_missing_from_numbers", []))
        missing_num_files = sorted(list(set(item['file'] for item in all_stats.get("indexes_missing_from_numbers", []))))
        if missing_num_count > 0:
            logging.info(f"Files with Superscript Indexes missing a matching Reference fn_number: {len(missing_num_files)}")
            logging.info(f"  - Files: {missing_num_files}")
            # Example detail for first few files
            for item in all_stats.get("indexes_missing_from_numbers", [])[:3]:
                 logging.info(f"    - {item['file']}: Missing numbers {item['missing_numbers']}")

        missing_idx_count = len(all_stats.get("numbers_missing_from_indexes", []))
        missing_idx_files = sorted(list(set(item['file'] for item in all_stats.get("numbers_missing_from_indexes", []))))
        if missing_idx_count > 0:
             logging.info(f"Files with Reference fn_numbers missing a matching Superscript Index: {len(missing_idx_files)}")
             logging.info(f"  - Files: {missing_idx_files}")
             for item in all_stats.get("numbers_missing_from_indexes", [])[:3]:
                  logging.info(f"    - {item['file']}: Missing indexes {item['missing_indexes']}")


        # Missing document title
        missing_title_files = all_stats.get("missing_title_files", [])
        logging.info(f"Files missing document_title: {len(missing_title_files)} -> {missing_title_files}")

        # Missing reference type
        missing_ref_type_count = len(all_stats.get("missing_ref_type", []))
        missing_ref_type_files = sorted(list(set(item['file'] for item in all_stats.get("missing_ref_type", []))))
        logging.info(f"References missing type (RS/FF/RU): {missing_ref_type_count}")
        if missing_ref_type_count > 0:
             logging.info(f"  - Files affected: {len(missing_ref_type_files)} -> {missing_ref_type_files}")

        # Gaps in fn_number
        gaps_fn_num_files = sorted(list(set(item['file'] for item in all_stats.get("gaps_in_fn_number", []))))
        logging.info(f"Files with gaps (>1) in fn_number sequence: {len(gaps_fn_num_files)} -> {gaps_fn_num_files}")

        # Gaps in fn_indexes
        gaps_fn_idx_files = sorted(list(set(item['file'] for item in all_stats.get("gaps_in_fn_indexes", []))))
        logging.info(f"Files with gaps (>1) in fn_indexes sequence: {len(gaps_fn_idx_files)} -> {gaps_fn_idx_files}")

        # Gaps in Art Markers
        gaps_art_files = sorted(list(set(item['file'] for item in all_stats.get("gaps_in_art_markers", []))))
        logging.info(f"Files with gaps (>1) in Art. marker sequence: {len(gaps_art_files)} -> {gaps_art_files}")

        # Gaps in Roman Markers
        gaps_roman_files = sorted(list(set(item['file'] for item in all_stats.get("gaps_in_roman_markers", []))))
        logging.info(f"Files with gaps (>1) in Roman marker sequence: {len(gaps_roman_files)} -> {gaps_roman_files}")

        # Gaps in Arabic Markers
        gaps_arabic_files = sorted(list(set(item['file'] for item in all_stats.get("gaps_in_arabic_markers", []))))
        logging.info(f"Files with gaps (>1) in Arabic marker sequence: {len(gaps_arabic_files)} -> {gaps_arabic_files}")
        
        # Duplicate Markers
        duplicate_marker_count = len(all_stats.get("duplicate_marker", []))
        duplicate_marker_files = sorted(list(set(item['file'] for item in all_stats.get("duplicate_marker", []))))
        if duplicate_marker_count > 0:
             logging.info(f"Instances of duplicate section markers found: {duplicate_marker_count}")
             logging.info(f"  - Files affected: {len(duplicate_marker_files)} -> {duplicate_marker_files}")
             
        # Empty Sections
        empty_section_count = len(all_stats.get("empty_sections", []))
        empty_section_files = sorted(list(set(item['file'] for item in all_stats.get("empty_sections", []))))
        if empty_section_count > 0:
             logging.info(f"Non-preamble sections with empty text found: {empty_section_count}")
             logging.info(f"  - Files affected: {len(empty_section_files)} -> {empty_section_files}")


        logging.info("--- End of Statistics Report ---")


if __name__ == "__main__":
    
    # --- Configuration ---
    # Directory containing the final reconstructed JSON files (_final.json)
    FINAL_JSON_DIR = "./LawsDocs/processed/Legge federale/JSONs" 
    # Path for the output log file

    start_analysis(FINAL_JSON_DIR)
