import json
import re
import os
import logging

# Search limits for reference components (number of spans to check)
REF_LABEL_SEARCH_BACKWARD_LIMIT = 3
REF_NUMBER_SEARCH_BACKWARD_LIMIT = 5
REF_TEXT_SEARCH_FORWARD_LIMIT = 5

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

def flatten_spans_and_build_lookup(pages_data):
    """
    Creates a flat list of all spans and a lookup dict from hierarchical_id to list index.
    Augments spans with parent indices.
    """
    flat_span_list = []
    id_to_index_lookup = {}
    current_index = 0
    for page_idx, page in enumerate(pages_data):
        for block_idx, block in enumerate(page.get("blocks", [])):
            block_id = block.get("hierarchical_id", f"page-{page_idx}.block-{block_idx}") # Fallback ID
            for line_idx, line in enumerate(block.get("lines", [])):
                for span_idx, span in enumerate(line.get("spans", [])):
                    # Create a copy to avoid modifying the original loaded data
                    augmented_span = span.copy() 
                    augmented_span['page_idx'] = page_idx
                    augmented_span['block_idx'] = block_idx
                    augmented_span['line_idx'] = line_idx
                    augmented_span['span_idx'] = span_idx
                    augmented_span['block_id'] = block_id # Store block ID for easy filtering
                    
                    span_id = augmented_span.get("hierarchical_id")
                    if span_id:
                        id_to_index_lookup[span_id] = current_index
                        flat_span_list.append(augmented_span)
                        current_index += 1
                    else:
                        logging.warning(f"Span missing hierarchical_id on page {page_idx}, block {block_idx}, line {line_idx}")
                        
    # logging.info(f"Created flat span list ({len(flat_span_list)} spans) and ID lookup table.")
    return flat_span_list, id_to_index_lookup

def get_span_text(span):
    """Safely gets text from a span."""
    return span.get('text', '')

def parse_superscripts_from_span(span):
    """Checks a single span for superscript footnote index."""
    span_text = get_span_text(span).strip()
    if span.get('is_superscript') and span_text.isdigit():
        try:
            return int(span_text), True # Return number and flag indicating it's a footnote
        except ValueError:
            return span_text, False # Should not happen, but return text if not int
    else:
        return span_text, False # Return text and flag

# --- Core Reconstruction Functions ---

def process_references(analysis_references, flat_span_list, id_to_index_lookup, is_allegato_file):
    """
    Processes references from analysis data to find type labels (RS/FF/RU),
    footnote numbers, and construct final text. Also identifies blocks to ignore.
    Searches for components are limited to the current and adjacent blocks on the same page.
    """
    output_references = []
    blocks_to_ignore = set() # Store block IDs (e.g., "page-0.block-15")

    for ref_index, ref_item in enumerate(analysis_references):
        ref_item_id = ref_item.get('id')
        if not ref_item_id or ref_item_id not in id_to_index_lookup:
            logging.warning(f"Reference item ID '{ref_item_id}' not found in lookup table. Skipping ref item {ref_index+1}.")
            continue

        # Get the primary reference span and its context
        ref_text_idx = id_to_index_lookup[ref_item_id]
        ref_span = flat_span_list[ref_text_idx]
        current_page_idx = ref_span['page_idx']
        current_block_idx = ref_span['block_idx']
        current_block_id = ref_span['block_id']

        # Remark 1: Ignore the entire block containing reference text
        blocks_to_ignore.add(current_block_id)
        # logging.debug(f"Added block {current_block_id} to ignore list (contains ref text '{ref_item.get('text', '')}')")

        ref_type = None
        fn_number = None
        combined_text = ref_item.get('text', '') # Start with the core text

        # Define target blocks for backward search (current & previous on same page)
        target_blocks_backward = set([(current_page_idx, current_block_idx)])
        if current_block_idx > 0:
            target_blocks_backward.add((current_page_idx, current_block_idx - 1))
        # logging.debug(f"Ref {ref_item_id}: Backward search targets: {target_blocks_backward}")

        # --- 1. Find Type (RS/FF/RU Label) - Searching Backwards by Block ---
        label_span_idx = -1
        search_idx = ref_text_idx - 1 # Start from the span just before the ref text
        while search_idx >= 0:
            prev_span = flat_span_list[search_idx]
            prev_span_page_block = (prev_span['page_idx'], prev_span['block_idx'])

            # Stop search if we move outside the target blocks
            if prev_span_page_block not in target_blocks_backward:
                # logging.debug(f"Label search stopped at span {search_idx}: Outside target blocks.")
                break 

            prev_text = get_span_text(prev_span).strip()
            if prev_text in ("RS", "FF", "RU", "CS"):
                ref_type = prev_text
                label_span_idx = search_idx 
                # Also ignore the block where the label was found
                blocks_to_ignore.add(prev_span['block_id'])
                # logging.debug(f"Found type '{ref_type}' for ref '{ref_item_id}' at index {label_span_idx} (Block: {prev_span['block_id']})")
                break # Found the label
            
            search_idx -= 1 # Move to the previous span

        # --- 2. Find Footnote Number - Searching Backwards by Block ---
        # Start searching from before the label (if found) or before the ref text
        search_start_idx = (label_span_idx if label_span_idx != -1 else ref_text_idx) - 1
        number_span_idx = -1
        search_idx = search_start_idx # Reset search index
        
        while search_idx >= 0:
            prev_span = flat_span_list[search_idx]
            prev_span_page_block = (prev_span['page_idx'], prev_span['block_idx'])

            # Stop search if we move outside the target blocks
            if prev_span_page_block not in target_blocks_backward:
                # logging.debug(f"Number search stopped at span {search_idx}: Outside target blocks.")
                break

            prev_text = get_span_text(prev_span).strip()
            if prev_text.isdigit():
                try:
                    num_val = int(prev_text)

                    if is_allegato_file:
                        fn_number = prev_text
                        number_span_idx = search_idx
                        blocks_to_ignore.add(prev_span['block_id'])
                        break;
                    else:
                        if num_val <= (ref_index + 1): 
                            fn_number = prev_text # Store as string
                            number_span_idx = search_idx
                            # Also ignore the block where the number was found
                            blocks_to_ignore.add(prev_span['block_id'])
                            # logging.debug(f"Found fn_number '{fn_number}' for ref '{ref_item_id}' at index {number_span_idx} (Block: {prev_span['block_id']})")
                            break # Found a suitable number
                        # else:
                            # logging.debug(f"Found digit '{prev_text}' at index {search_idx}, but {num_val} > {ref_index + 1}. Continuing search.")
                except ValueError:
                    pass # Should not happen with isdigit()
            
            search_idx -= 1 # Move to the previous span
        
        if fn_number is None:
            logging.warning(f"Could not find preceding footnote number (<= {ref_index+1}) within target blocks for reference ID: {ref_item_id} (Text: '{ref_item.get('text', '')}')")

        # --- 3. Construct Final Text (Add following digits for RU/FF) - Searching Forward by Block ---
        # Remark 3 & 5: Find following digits for RU/FF
        if ref_type in ("RU", "FF", "CS"):
            # Define target blocks for forward search (current & next on same page)
            target_blocks_forward = set([(current_page_idx, current_block_idx)])
            # We need to know the max block index for the current page to safely check next block
            # Let's find it (can be slightly inefficient if done repeatedly)
            max_block_idx_on_page = -1
            for span in reversed(flat_span_list): # Search from end for last span on page
                 if span['page_idx'] == current_page_idx:
                      max_block_idx_on_page = span['block_idx']
                      break
            if current_block_idx < max_block_idx_on_page:
                target_blocks_forward.add((current_page_idx, current_block_idx + 1))
            # logging.debug(f"Ref {ref_item_id}: Forward search targets: {target_blocks_forward}")
            
            following_digits = []
            search_idx = ref_text_idx + 1 # Start search from span *after* ref text
            
            while search_idx < len(flat_span_list):
                next_span = flat_span_list[search_idx]
                next_span_page_block = (next_span['page_idx'], next_span['block_idx'])

                # Stop search if we move outside the target blocks
                if next_span_page_block not in target_blocks_forward:
                    # logging.debug(f"Forward digit search stopped at span {search_idx}: Outside target blocks.")
                    break 

                next_text = get_span_text(next_span).strip()
                if next_text.isdigit():
                    following_digits.append(next_text)
                    # Also ignore the block containing these digits
                    blocks_to_ignore.add(next_span['block_id'])
                    # logging.debug(f"Found following digit '{next_text}' for ref '{ref_item_id}' at index {search_idx} (Block: {next_span['block_id']})")
                    break
                elif next_text: # Found non-empty, non-digit text
                    # logging.debug(f"Forward digit search stopped at span {search_idx}: Non-digit text '{next_text}'.")
                    break # Stop searching for digits after this type
                    
                search_idx += 1 # Move to the next span

            if following_digits:
                combined_text += " " + " ".join(following_digits) # Add digits to the original ref text

        # Final combined text (Remark 5) - Use ref_type if found
        final_reference_text = f"{ref_type} {combined_text}" if ref_type else combined_text
        
        # Append the processed reference to the output list
        output_references.append({
            "id": ref_item_id,
            "fn_number": fn_number,
            "type": ref_type,
            "text": combined_text.strip() 
        })

    # logging.info(f"Processed {len(output_references)} references. Identified {len(blocks_to_ignore)} unique blocks to ignore.")
    return output_references, blocks_to_ignore




def extract_sections(analysis_sections, analysis_title_id, flat_span_list, id_to_index_lookup, blocks_to_ignore, doc_title_text):
    """
    Extracts text for preamble and marked sections.
    If no analysis_sections are found, creates a single 'Content' section using the document title
    and all text after the title.
    Filters ignored blocks and handles superscripts, inserting placeholders for footnotes.
    """
    output_sections = []
    # logging.info("Extracting section texts...")

    # --- Determine Preamble/Content Start Index (after title) ---
    title_end_span_idx = id_to_index_lookup.get(analysis_title_id, -1)
    content_start_idx = 0 # Default to start of document if title_id is missing or not found
    if title_end_span_idx != -1:
        content_start_idx = title_end_span_idx + 1
    elif analysis_title_id: # title_id was provided but not found in lookup
        logging.warning(f"Title ID '{analysis_title_id}' not found in lookup. Starting content from index 0.")
    else: # No title_id provided at all
        logging.info("No title ID provided. Starting content from index 0.")
    
    # --- Case 1: No sections identified by the analysis script ---
    if not analysis_sections:
        # logging.warning("No sections found in analysis data. Creating a single 'Content' section.")
        
        content_text_parts = []
        content_fn_indexes = []
        
        # Iterate from after the title (or beginning) to the end of the document
        # logging.debug(f"Creating 'Content' section: Spans from {content_start_idx} to {len(flat_span_list)}")
        for idx in range(content_start_idx, len(flat_span_list)):
            span = flat_span_list[idx]
            # Apply Filters
            if span['block_id'] in blocks_to_ignore: continue
            # Skip header blocks on subsequent pages (heuristic, adjust if needed)
            if span['page_idx'] > 0 and span['block_idx'] in [0, 1] and span['bbox'][1] < 100: # Example Y-coord
                is_likely_header = True
                for s_text in ["RU ", "RO ", "FF ", "RS "]: # Common header starts
                    if s_text in get_span_text(span):
                        break
                else: # No common header text found
                    is_likely_header = False
                if is_likely_header:
                    continue
            
            text_part, is_fn = parse_superscripts_from_span(span)
            if is_fn:
                content_fn_indexes.append(text_part)
                content_text_parts.append(f"[FN_{text_part}]") # Insert placeholder
            else:
                content_text_parts.append(text_part)
        
        output_sections.append({
            "marker_id": analysis_title_id if analysis_title_id else "document_start", # Use title_id or a placeholder
            "marker": "Content", # As requested
            "title": doc_title_text if doc_title_text else "Document Content", # Use the doc title
            "text": " ".join(content_text_parts).strip(),
            "fn_indexes": sorted(list(set(content_fn_indexes)))
        })
        # logging.info(f"Created single 'Content' section with {len(content_fn_indexes)} potential footnote refs.")
        return output_sections

    # --- Case 2: Sections were identified by the analysis script (existing logic) ---
    try:
        # Preamble extraction (remains largely the same)
        first_marker_span_idx = id_to_index_lookup.get(analysis_sections[0]['marker_id'])
        if first_marker_span_idx is None:
             logging.error(f"Marker ID '{analysis_sections[0]['marker_id']}' for first section not found. Cannot proceed with standard sectioning.")
             # Fallback: treat as if no sections were found (could call a similar logic as above)
             # For now, returning empty to indicate failure in standard path
             return [] 
        
        preamble_start_idx = content_start_idx # Start preamble after title
        preamble_end_idx = first_marker_span_idx # Preamble ends *before* the first marker span
        
    except Exception as e:
        logging.error(f"Error determining initial section boundaries for standard parsing: {e}")
        return [] # Or handle more gracefully

    # Extract Preamble
    preamble_text_parts = []
    preamble_fn_indexes = []
    # logging.debug(f"Extracting Preamble: Spans from {preamble_start_idx} to {preamble_end_idx}")
    
    # Ensure preamble_start_idx is not greater than or equal to preamble_end_idx
    if preamble_start_idx < preamble_end_idx:
        for idx in range(preamble_start_idx, preamble_end_idx):
            span = flat_span_list[idx]
            if span['block_id'] in blocks_to_ignore: continue
            # Basic header skipping for preamble on subsequent pages
            if span['page_idx'] > 0 and span['block_idx'] in [0, 1] and span['bbox'][1] < 100: continue

            text_part, is_fn = parse_superscripts_from_span(span)
            if is_fn:
                preamble_fn_indexes.append(text_part)
                preamble_text_parts.append(f"[FN_{text_part}]") # Insert placeholder
            else:
                preamble_text_parts.append(text_part)
        
        preamble_text_joined = " ".join(preamble_text_parts).strip()
        if preamble_text_joined: # Only add preamble if it has content
            output_sections.append({
                "marker_id": analysis_title_id if analysis_title_id else "preamble_start",
                "marker": "Preamble",
                "title": "Preamble",
                "text": preamble_text_joined,
                "fn_indexes": sorted(list(set(preamble_fn_indexes)))
            })
            # logging.info(f"Extracted Preamble with {len(preamble_fn_indexes)} potential footnote refs.")
    else:
        logging.info("No preamble content found or first marker is at the beginning.")


    # Extract Marked Sections (existing logic)
    for i, current_section_info in enumerate(analysis_sections):
        current_marker_id = current_section_info['marker_id']
        current_marker_idx = id_to_index_lookup.get(current_marker_id)

        if current_marker_idx is None:
            logging.warning(f"Marker ID '{current_marker_id}' for section {i+1} ('{current_section_info['marker']}') not found. Skipping section.")
            continue

        # Section text starts *after* the marker span itself IF the marker is part of the span list
        # However, the previous script's `sections_list` might already define markers.
        # Let's assume the range is from this marker up to the next.
        # The marker text itself (e.g. "Art. 1") might be part of the first span of the section's content.
        section_text_start_idx = current_marker_idx
        
        if i + 1 < len(analysis_sections):
            next_marker_id = analysis_sections[i+1]['marker_id']
            next_marker_idx = id_to_index_lookup.get(next_marker_id)
            if next_marker_idx is None:
                logging.warning(f"Next marker ID '{next_marker_id}' not found. Reading section {i+1} ('{current_section_info['marker']}') until end of document.")
                section_text_end_idx = len(flat_span_list)
            else:
                section_text_end_idx = next_marker_idx # Text up to, but not including, the next marker
        else:
            section_text_end_idx = len(flat_span_list)
            
        # logging.debug(f"Extracting Section {i+1} ('{current_section_info['marker']}'): Spans from {section_text_start_idx} to {section_text_end_idx}")
        
        section_text_parts = []
        section_fn_indexes = []
        
        for idx in range(section_text_start_idx, section_text_end_idx):
            span = flat_span_list[idx]
            if span['block_id'] in blocks_to_ignore: continue
            if span['page_idx'] > 0 and span['block_idx'] in [0, 1] and span['bbox'][1] < 100: # More robust header skipping
                is_likely_header = True
                for s_text in ["RU ", "RO ", "FF ", "RS "]:
                    if s_text in get_span_text(span):
                        break
                else:
                    is_likely_header = False
                if is_likely_header:
                    continue

            text_part, is_fn = parse_superscripts_from_span(span)
            if is_fn:
                section_fn_indexes.append(text_part)
                section_text_parts.append(f"[FN_{text_part}]") # Insert placeholder
            else:
                section_text_parts.append(text_part)

        output_sections.append({
            "marker_id": current_marker_id,
            "marker": current_section_info['marker'],
            "title": current_section_info['title'],
            "text": " ".join(section_text_parts).strip(),
            "fn_indexes": sorted(list(set(section_fn_indexes)))
        })
        # logging.info(f"Extracted Section {i+1} ('{current_section_info['marker']}') with {len(section_fn_indexes)} potential footnote refs.")

    return output_sections


def reconstruct_document(analysis_file_path, full_text_file_path, output_file_path):
    """
    Loads analysis and full text data, reconstructs the document structure,
    and saves the final JSON output.
    """
    # logging.info(f"--- Starting reconstruction for {os.path.basename(analysis_file_path)} ---")

    # 1. Load Data
    analysis_data = load_json_file(analysis_file_path)
    full_text_data = load_json_file(full_text_file_path)

    if not analysis_data or not full_text_data:
        logging.error("Failed to load required input JSON files. Aborting reconstruction.")
        return False

    # Extract key parts from analysis data
    source_file = analysis_data.get("source_file")
    is_allegato_file = "Allegato" in os.path.basename(analysis_file_path)
    doc_title = analysis_data.get("document_title")
    title_id = analysis_data.get("title_id") # Used to find start of preamble
    analysis_sections = analysis_data.get("sections_list", [])
    analysis_references = analysis_data.get("references_list", [])

    # 2. Prepare Full Text Data Structures
    flat_span_list, id_to_index_lookup = flatten_spans_and_build_lookup(full_text_data)
    if not flat_span_list or not id_to_index_lookup:
         logging.error("Failed to create flat span list or lookup table. Aborting.")
         return False


    # 3. Process References (and identify blocks to ignore)
    output_references, blocks_to_ignore = process_references(
        analysis_references, 
        flat_span_list, 
        id_to_index_lookup,
        is_allegato_file  # Pass the new flag
    )

    # 4. Extract Section Texts (Preamble + Marked Sections)
    output_sections = extract_sections(
        analysis_sections, 
        title_id, 
        flat_span_list, 
        id_to_index_lookup, 
        blocks_to_ignore,
        doc_title # Pass the document title text here
    )


    # 5. Assemble Final Structure
    final_structure = {
        "source_file": source_file,
        "document_title": doc_title,
        "title_id": title_id, # Keep for reference
        "sections_list": output_sections,
        "references_list": output_references
    }

    # 6. Save Final Output
    try:
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        with open(output_file_path, 'w', encoding='utf-8') as f_out:
            json.dump(final_structure, f_out, ensure_ascii=False, indent=4)
        # logging.info(f"Successfully saved final reconstructed JSON to: {output_file_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to save final JSON output to {output_file_path}: {e}")
        return False


# --- Execution ---
def start_reconstruction(FULL_TEXT_JSON_DIR, ANALYSIS_JSON_DIR, FINAL_OUTPUT_DIR):

    if not os.path.isdir(ANALYSIS_JSON_DIR):
        logging.error(f"Analysis JSON directory not found: {ANALYSIS_JSON_DIR}")
    elif not os.path.isdir(FULL_TEXT_JSON_DIR):
        logging.error(f"Full text JSON directory not found: {FULL_TEXT_JSON_DIR}")
    else:
        os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

    processed_count = 0
    error_count = 0
    
    # Iterate through analysis files, assuming corresponding full text file exists
    for base_name in os.listdir(ANALYSIS_JSON_DIR):

        analysis_path = os.path.join(ANALYSIS_JSON_DIR, base_name)
        full_text_path = os.path.join(FULL_TEXT_JSON_DIR, base_name)
        
        # Construct the final output filename
        output_filename = base_name
        output_path = os.path.join(FINAL_OUTPUT_DIR, output_filename)

        if not os.path.exists(full_text_path):
                logging.warning(f"Skipping {base_name}: Corresponding full text file not found at {full_text_path}")
                error_count += 1
                continue

        if reconstruct_document(analysis_path, full_text_path, output_path):
            processed_count += 1
        else:
            error_count += 1
        
        logging.info(f"Processed {base_name}")
    
    # logging.info(f"Finished reconstruction. Processed: {processed_count}, Errors/Skipped: {error_count}")


if __name__ == "__main__":

    # Directory containing the JSON files with hierarchical IDs (_with_ids.json)
    FULL_TEXT_JSON_DIR = "./LawsDocs/for_processing/JSONs/Legge federale_in" 
    # Directory containing the JSON files with analysis results (_analysis.json)
    ANALYSIS_JSON_DIR = "./LawsDocs/for_processing/JSONs/Legge federale_out" 
    # Directory to save the final reconstructed JSON files (_final.json)
    FINAL_OUTPUT_DIR = "./LawsDocs/processed/Legge federale/JSONs"

    start_reconstruction(FULL_TEXT_JSON_DIR, ANALYSIS_JSON_DIR, FINAL_OUTPUT_DIR)
