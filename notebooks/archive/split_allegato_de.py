import json
import logging
import os
import re
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
OUTPUT_DIR = "./LawsDocs/for_processing/JSON_in_split"
Y_THRESHOLD_FOR_ALLEGATO = 150  # Pixels from the top. Adjust as needed.
ALLEGATO_KEYWORD = "Anhang" # Case-sensitive

def load_json_data(filepath: str) -> Optional[List[Dict[str, Any]]]:
    """Loads page data from a JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            return data
        else:
            print(f"Error: JSON file {filepath} does not contain a list of page objects.")
            return None
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading {filepath}: {e}")
        return None

def sanitize_for_filename(text: str) -> str:
    """Removes or replaces characters that are problematic in filenames (basic)."""
    # This is less critical now as suffixes are numeric or simple sequences
    text = re.sub(r'[^\w-]', '', text)  # Keep word chars, hyphens (digits are word chars)
    return text if text else "Unnamed"


def find_allegato_markers(pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifies blocks that start an "Allegato".
    The suffix for the Allegato name is now specifically a number immediately
    following the "Allegato" keyword (possibly in the same or next span on the same line).
    Returns a list of dictionaries, each with 'page_idx', 'block_idx', and 'name_suffix'.
    """
    markers = []
    roman_numeral_pattern = r'^(XL|L?X{0,3})(IX|IV|V?I{0,3})$'

    for p_idx, page in enumerate(pages_data):
        page_blocks = page.get('blocks', [])
        for b_idx, block in enumerate(page_blocks):
            block_bbox_y1 = block.get('bbox', [0, float('inf')])[1]

            if block_bbox_y1 < Y_THRESHOLD_FOR_ALLEGATO: # Check if block is near top
                allegato_keyword_found_in_block = False
                numerical_suffix_found = ""

                for line_idx, line in enumerate(block.get('lines', [])):
                    spans = line.get('spans', [])
                    for s_idx, span in enumerate(spans):
                        span_text = span.get('text', '') # Keep original spacing for regex
                        span_text_stripped = span_text.strip()

                        # First try Arabic numbers
                        match_arabic = re.match(rf"^{ALLEGATO_KEYWORD}\s*(\d+)", span_text_stripped)
                        if match_arabic:
                            allegato_keyword_found_in_block = True
                            numerical_suffix_found = match_arabic.group(1)
                            break 
                        
                        # Then try Roman numerals
                        match_roman = re.match(rf"^{ALLEGATO_KEYWORD}\s+([IVX]+)", span_text_stripped)
                        if match_roman and re.match(roman_numeral_pattern, match_roman.group(1)):
                            allegato_keyword_found_in_block = True
                            numerical_suffix_found = match_roman.group(1)
                            break

                        # If just "Allegato" is found, check the next span in the SAME LINE for a number or Roman numeral
                        if span_text_stripped == ALLEGATO_KEYWORD:
                            allegato_keyword_found_in_block = True
                            if s_idx + 1 < len(spans):
                                for next_s_idx in range(s_idx + 1, len(spans)):
                                    next_span_text_stripped = spans[next_s_idx].get('text', '').strip()
                                    # Check for Arabic number
                                    if next_span_text_stripped.isdigit():
                                        numerical_suffix_found = next_span_text_stripped
                                        break 
                                    # Check for Roman numeral
                                    elif re.match(roman_numeral_pattern, next_span_text_stripped):
                                        numerical_suffix_found = next_span_text_stripped
                                        break
                                    elif next_span_text_stripped: 
                                        break 
                                if numerical_suffix_found:
                                    break 
                            break 

                    if allegato_keyword_found_in_block:
                        break

                if allegato_keyword_found_in_block:
                    # Use the found numerical suffix, or fallback to sequential numbering
                    suffix_to_use = numerical_suffix_found if numerical_suffix_found else f"{(len(markers) + 1)}"
                    markers.append({
                        'page_idx': p_idx,
                        'block_idx': b_idx,
                        'name_suffix': suffix_to_use # This will be "1", "2", or "NextSequentialNumber"
                    })
    return markers


def split_and_save_json(input_filepath: str, pages_data: List[Dict[str, Any]], markers: List[Dict[str, Any]], out_path: str):
    """
    Splits the pages_data based on markers and saves them to new JSON files.
    """
    base_filename = os.path.splitext(os.path.basename(input_filepath))[0]
    output_dir = out_path
    if not output_dir:
        output_dir = "."

    if not markers:
        # print(f"No 'Allegato' markers found in {input_filepath}. Original JSON structure is maintained (no split).")
        # Optionally, copy the original file or save it with a "_unsplit" suffix if needed
        output_path = os.path.join(output_dir, f"{base_filename}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=4)
        # print(f"Saved unsplit data to {output_path}")
        return

    # --- Save the main document part (before the first Allegato) ---
    first_marker = markers[0]
    main_doc_pages_data = []
    
    if not (first_marker['page_idx'] == 0 and first_marker['block_idx'] == 0):
        for p_idx in range(first_marker['page_idx'] + 1):
            page_content = pages_data[p_idx]
            new_page = {'page_number': page_content.get('page_number', p_idx + 1), 'blocks': []}

            current_page_blocks = page_content.get('blocks', [])
            if p_idx < first_marker['page_idx']:
                new_page['blocks'] = [block for block in current_page_blocks]
            else: # p_idx == first_marker['page_idx']
                new_page['blocks'] = [block for block in current_page_blocks[:first_marker['block_idx']]]
            
            if new_page['blocks']:
                 main_doc_pages_data.append(new_page)

        if main_doc_pages_data:
            output_main_path = os.path.join(output_dir, f"{base_filename}.json")
            with open(output_main_path, 'w', encoding='utf-8') as f:
                json.dump(main_doc_pages_data, f, ensure_ascii=False, indent=4)
            # print(f"Saved main document part to: {output_main_path}")
        else:
            print(f"No content found for the main document part before the first Allegato in {input_filepath}.")
    else:
        print(f"Document {input_filepath} starts directly with an Allegato. No 'main' part before it.")

    # --- Save each Allegato part ---
    for i, marker in enumerate(markers):
        start_page_idx = marker['page_idx']
        start_block_idx = marker['block_idx']
        allegato_suffix = marker['name_suffix'] # This is now "1", "2", or a sequential number

        if i + 1 < len(markers):
            next_marker = markers[i+1]
            end_page_idx = next_marker['page_idx']
            end_block_idx = next_marker['block_idx']
        else:
            end_page_idx = len(pages_data) -1
            end_block_idx = len(pages_data[end_page_idx].get('blocks', []))

        allegato_pages_data = []
        for p_idx in range(start_page_idx, end_page_idx + 1):
            page_content = pages_data[p_idx]
            new_page = {'page_number': page_content.get('page_number', p_idx + 1), 'blocks': []}
            current_page_blocks = page_content.get('blocks', [])
            
            slice_start = 0
            if p_idx == start_page_idx:
                slice_start = start_block_idx

            slice_end = len(current_page_blocks)
            if p_idx == end_page_idx:
                slice_end = end_block_idx
            
            new_page['blocks'] = [block for block in current_page_blocks[slice_start:slice_end]]
            
            if new_page['blocks']:
                 allegato_pages_data.append(new_page)
        
        if allegato_pages_data:
            # Use the determined suffix for the filename
            allegato_filename_suffix = sanitize_for_filename(allegato_suffix)
            output_allegato_path = os.path.join(output_dir, f"{base_filename}_Allegato_{allegato_filename_suffix}.json")
            with open(output_allegato_path, 'w', encoding='utf-8') as f:
                json.dump(allegato_pages_data, f, ensure_ascii=False, indent=4)
            # print(f"Saved Allegato part to: {output_allegato_path}")
        else:
            print(f"Warning: No content found for Allegato with suffix '{allegato_suffix}' from marker at page {start_page_idx+1}, block {start_block_idx+1}.")


def start_splitting(JSON_INPUT_DIR_WITH_IDS, ANALYSIS_OUTPUT_DIR):
    if not os.path.isdir(JSON_INPUT_DIR_WITH_IDS):
        logging.error(f"Input JSON directory not found: {JSON_INPUT_DIR_WITH_IDS}")
    else:
        os.makedirs(ANALYSIS_OUTPUT_DIR, exist_ok=True) # Create output dir if needed

    skipped_files = []

    for filename in os.listdir(JSON_INPUT_DIR_WITH_IDS):
        if filename.lower().endswith(".json"):
            json_path = os.path.join(JSON_INPUT_DIR_WITH_IDS, filename)
    
            # print(f"--- Processing: {json_path} ---")
            all_pages_data_cc = load_json_data(json_path)

            if all_pages_data_cc:
                allegato_markers_cc = find_allegato_markers(all_pages_data_cc)
                # print(f"Found {len(allegato_markers_cc)} 'Allegato' marker(s): {allegato_markers_cc}")
                split_and_save_json(json_path, all_pages_data_cc, allegato_markers_cc, out_path=ANALYSIS_OUTPUT_DIR)
            else:
                print(f"Could not process {json_path}.")
                skipped_files.append(filename)
    if skipped_files:
        print(f"Skipped files due to errors: {len(skipped_files)} files")


if __name__ == "__main__":
    json_path = './LawsDocs/for_processing/JSON_in/Decreti federali che sottostanno a referendum facoltativo (trattati)/RU 2021 732.json' # Your input JSON with "Allegato"
    
    # print(f"--- Processing: {json_path} ---")
    all_pages_data_cc = load_json_data(json_path)

    if all_pages_data_cc:
        allegato_markers_cc = find_allegato_markers(all_pages_data_cc)
        # print(f"Found {len(allegato_markers_cc)} 'Allegato' marker(s): {allegato_markers_cc}")
        split_and_save_json(json_path, all_pages_data_cc, allegato_markers_cc)
    # else:
        # print(f"Could not process {json_path}.")