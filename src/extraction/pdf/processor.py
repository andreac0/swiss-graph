# --- START OF FILE pdf_processor.py ---

import fitz  # PyMuPDF
import re
import os
from collections import defaultdict
import json

# --- Helper Functions ---

def normalize_whitespace(text):
    """Replaces all whitespace runs with a single space and strips."""
    if not text: return ""
    # Replace various whitespace chars (including non-breaking space) with standard space
    text = re.sub(r'[\s\u00A0]+', ' ', str(text))
    return text.strip()

def format_section_text(text_lines):
    """Applies basic paragraph formatting based on line breaks."""
    # Join lines with single newlines, assuming structure comes from line list
    full_text = "\n".join(text_lines)
    # Normalize multiple newlines (keep max 2) after joining
    formatted_text = re.sub(r'\n{3,}', '\n\n', full_text)
    return formatted_text.strip()

# --- Main PDF Processing Function ---

def process_pdf_file(pdf_path, law_identifier):
    """
    Processes a single PDF file to extract sections and raw footnote codes.

    Args:
        pdf_path (str): Path to the input PDF file.
        law_identifier (str): An identifier for the law (e.g., pageId) used for section IDs.

    Returns:
        list: A list of section dictionaries [{'id':..., 'title':..., 'text':..., 'references':...}]
              or None if processing fails.
    """
    print(f"--- Processing PDF: {os.path.basename(pdf_path)} ---")
    sections = []
    footnotes_by_page = defaultdict(dict) # {page_num: {marker_num_str: text}}
    all_text_blocks = [] # Store tuples of (page_num, y0, text_content) for sorting

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  Error opening PDF: {e}")
        return None

    # --- Pass 1: Extract all text blocks and identify footnotes ---
    # (Keep Pass 1 logic exactly the same as the previous version - it worked correctly)
    print(f"  Extracting text and footnotes from {len(doc)} pages...")
    footnote_marker_start_pattern = re.compile(r"^\s*(\d+)\s*(.*)")
    superscript_chars = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    digit_map = str.maketrans(superscript_chars, "0123456789")

    for page_num, page in enumerate(doc):
        try:
            blocks = page.get_text("blocks", sort=True)
        except Exception as e:
            print(f"  Error getting text blocks from page {page_num + 1}: {e}")
            continue

        page_height = page.rect.height
        footnote_zone_threshold = page_height * 0.85
        current_page_marker = None
        current_page_fn_lines = []

        for block in blocks:
            x0, y0, x1, y1, original_block_text, block_no, block_type = block
            is_in_footnote_zone = y0 > footnote_zone_threshold
            block_lines = original_block_text.split('\n')
            block_fully_consumed_by_footnote = True

            if is_in_footnote_zone:
                for line in block_lines:
                    cleaned_line = line.strip();
                    if not cleaned_line: continue
                    marker_match = footnote_marker_start_pattern.match(cleaned_line)
                    superscript_marker_num_str = ""
                    superscript_footnote_text = ""
                    if cleaned_line and cleaned_line[0] in superscript_chars:
                         marker_num_str_ss = ""; idx_ss = 0
                         for i, char in enumerate(cleaned_line):
                             if char in superscript_chars: marker_num_str_ss += char.translate(digit_map); idx_ss = i + 1
                             else: break
                         if marker_num_str_ss:
                             superscript_marker_num_str = marker_num_str_ss
                             superscript_footnote_text = cleaned_line[idx_ss:].strip()

                    if marker_match or superscript_marker_num_str:
                        if current_page_marker is not None:
                            fn_text = normalize_whitespace(" ".join(current_page_fn_lines))
                            if fn_text: footnotes_by_page[page_num][current_page_marker] = fn_text
                        if marker_match:
                            current_page_marker = marker_match.group(1); text_part = marker_match.group(2).strip()
                            current_page_fn_lines = [text_part] if text_part else []
                        else:
                            current_page_marker = superscript_marker_num_str; current_page_fn_lines = [superscript_footnote_text] if superscript_footnote_text else []
                    elif current_page_marker is not None:
                        current_page_fn_lines.append(cleaned_line)
                    elif cleaned_line: block_fully_consumed_by_footnote = False
            else: block_fully_consumed_by_footnote = False

            if not block_fully_consumed_by_footnote and original_block_text.strip():
                 all_text_blocks.append((page_num, y0, original_block_text))

        if current_page_marker is not None:
            fn_text = normalize_whitespace(" ".join(current_page_fn_lines))
            if fn_text: footnotes_by_page[page_num][current_page_marker] = fn_text

    doc.close()
    print(f"  Finished extraction. Found footnotes on {len(footnotes_by_page)} pages.")

    if not all_text_blocks:
        print(f"  Error: No main text blocks extracted.")
        return None

    # --- Pass 2: Segment into Sections --- REVISED LOGIC ---
    print(f"  Segmenting text into sections...")
    sections = []
    current_section = None # Holds the dictionary of the section currently being built
    current_section_text_lines = [] # Holds text lines for the current section

    # Section Start Patterns (same as before)
    article_pattern = re.compile(r"^\s*(Art\.|Articolo)\s+([\w\d\.\-]+)\b", re.IGNORECASE)
    chapter_pattern = re.compile(r"^\s*(Capitolo)\s+([IVXLCDM\d]+)\b\.?", re.IGNORECASE)
    section_header_pattern = re.compile(r"^\s*(Sezione)\s+(\d+)\b\.?", re.IGNORECASE)
    title_header_pattern = re.compile(r"^\s*(Titolo)\s+([IVXLCDM\d]+(?:[\s_]?bis|[\s_]?ter|[\s_]?quater)?|terzo\s+a)\b\.?", re.IGNORECASE)
    annex_header_pattern = re.compile(r"^\s*(Allegato)\s+(\d+)\b\.?", re.IGNORECASE)
    roman_numeral_pattern = re.compile(r"^\s*([IVXLCDM]+)\.?\s*$", re.IGNORECASE)

    # Footnote Reference Patterns (same as before)
    year_footnote_pattern = re.compile(r"((?:19|20)\d{2})(\d)(?=[\s.,;!?:)]|$)")
    general_footnote_ref_pattern = re.compile(r"(?<=\S)(\d+)(?=[\s.,;!?:)]|$)")

    all_text_blocks.sort(key=lambda b: (b[0], b[1]))

    for page_num, y0, block_text in all_text_blocks:
        lines = block_text.split('\n')
        for line_content in lines:
            normalized_line = normalize_whitespace(line_content)
            if not normalized_line: continue

            # --- 1. Check if line starts a new section ---
            is_section_start = False
            new_section_title = None
            new_section_marker_suffix = None # e.g., Art_1, Capitolo_I
            art_match = article_pattern.match(normalized_line); chap_match = chapter_pattern.match(normalized_line)
            sec_match = section_header_pattern.match(normalized_line); tit_match = title_header_pattern.match(normalized_line)
            ann_match = annex_header_pattern.match(normalized_line); rom_match = roman_numeral_pattern.match(normalized_line)

            def create_marker_id(keyword, identifier):
                clean_id = re.sub(r'[.\s]+', '_', str(identifier))
                if keyword == "Titolo" and 'terzo a' in identifier.lower(): clean_id = 'terzo_a'
                elif keyword == "Titolo": clean_id = re.sub(r'_+', '_', clean_id)
                return f"{keyword}_{clean_id}"

            if art_match: is_section_start = True; new_section_marker_suffix = create_marker_id("Art", art_match.group(2)); new_section_title = normalized_line
            elif chap_match: is_section_start = True; new_section_marker_suffix = create_marker_id("Capitolo", chap_match.group(2)); new_section_title = normalized_line
            elif sec_match: is_section_start = True; new_section_marker_suffix = create_marker_id("Sezione", sec_match.group(2)); new_section_title = normalized_line
            elif tit_match: is_section_start = True; new_section_marker_suffix = create_marker_id("Titolo", tit_match.group(2)); new_section_title = normalized_line
            elif ann_match: is_section_start = True; new_section_marker_suffix = create_marker_id("Allegato", ann_match.group(2)); new_section_title = normalized_line
            elif rom_match and not any([chap_match, sec_match, tit_match, ann_match]): is_section_start = True; new_section_marker_suffix = create_marker_id("Roman", rom_match.group(1)); new_section_title = normalized_line

            # --- 2. Process the line for markers (do this *before* deciding where the line goes) ---
            markers_on_this_line = []
            modified_line = normalized_line # Start with original normalized

            # Pass A: Find YYYYM markers
            year_matches = list(year_footnote_pattern.finditer(normalized_line))
            for m in reversed(year_matches):
                marker = m.group(2); start, end = m.span(2)
                if 0 < int(marker) < 500: markers_on_this_line.append((marker, page_num))
                modified_line = modified_line[:start] + modified_line[end:]

            # Pass B: Find general markers on modified line
            general_matches = general_footnote_ref_pattern.finditer(modified_line)
            for m in general_matches:
                marker = m.group(1)
                if 0 < int(marker) < 500: markers_on_this_line.append((marker, page_num))

            # --- 3. Handle section logic based on whether it's a start line ---
            if is_section_start:
                # --- Finalize Previous Section (if exists) ---
                if current_section is not None:
                    current_section['text'] = format_section_text(current_section_text_lines)
                    linked_footnotes = []; seen_refs = set()
                    section_markers_list = current_section.get('_markers', [])
                    unique_markers = sorted(list(set(section_markers_list)), key=lambda x: (x[1], int(x[0])))
                    for marker_num, marker_page_lookup in unique_markers: # Renamed to avoid confusion
                        footnote_text = footnotes_by_page.get(marker_page_lookup, {}).get(marker_num)
                        if footnote_text and footnote_text not in seen_refs:
                            linked_footnotes.append(footnote_text); seen_refs.add(footnote_text)
                    current_section['references'] = linked_footnotes
                    del current_section['_markers'] # Clean up
                    sections.append(current_section)

                # --- Start New Section ---
                current_section_id = f"{law_identifier}/{new_section_marker_suffix}"
                current_section = { # Assign to the main current_section variable
                    'id': current_section_id,
                    'title': new_section_title,
                    'text': None,
                    'references': [],
                    '_markers': markers_on_this_line # Initialize markers with those from title line
                }
                current_section_text_lines = [modified_line] # Start text with modified title line
                print(f"    Started Section: {current_section_id} ('{new_section_title}')")

            elif current_section is not None:
                # --- Append line to Current Section ---
                current_section_text_lines.append(modified_line)
                # Add markers found on this line to the *current section's* list
                current_section['_markers'].extend(markers_on_this_line)

            else:
                # --- Handle Preamble or Trailing Text ---
                if not sections: # Preamble Case
                     current_section_id = f"{law_identifier}/Preamble"
                     current_section = { 'id': current_section_id, 'title': 'Preamble', 'text': None, 'references': [], '_markers': markers_on_this_line}
                     current_section_text_lines = [modified_line] # Initialize text lines
                     print(f"    Started Section: {current_section_id} ('Preamble')")
                elif sections: # Trailing Text Case
                    # Append the original, unmodified line to the *previous* section's text
                    # Do not add any markers found on this line to any section
                    print(f"    Appending trailing text to section {sections[-1]['id']}: '{normalized_line[:60]}...'")
                    last_section_lines = sections[-1]['text'].split('\n')
                    last_section_lines.append(normalized_line) # Use original line
                    sections[-1]['text'] = format_section_text(last_section_lines)
                else: # Should not happen
                    print(f"    Warning: Orphan text line: {normalized_line[:100]}...")

    # --- Finalize the very last section ---
    if current_section is not None:
        current_section['text'] = format_section_text(current_section_text_lines)
        linked_footnotes = []; seen_refs = set()
        section_markers_list = current_section.get('_markers', [])
        unique_markers = sorted(list(set(section_markers_list)), key=lambda x: (x[1], int(x[0])))
        for marker_num, marker_page_lookup in unique_markers:
            footnote_text = footnotes_by_page.get(marker_page_lookup, {}).get(marker_num)
            if footnote_text and footnote_text not in seen_refs:
                linked_footnotes.append(footnote_text); seen_refs.add(footnote_text)
        current_section['references'] = linked_footnotes
        if '_markers' in current_section: del current_section['_markers']
        sections.append(current_section)
        # print(f"    Finalized Last Section: {current_section['id']}") # Debug

    print(f"  Finished segmentation. Found {len(sections)} sections.")
    if not sections:
        print(f"  Warning: No sections could be segmented.")
        return None

    return sections


# --- Standalone Execution / Testing (Optional) ---
if __name__ == "__main__":
    print("Running pdf_processor.py standalone for testing...")

    # --- Configuration for Testing ---
    test_pdf_files = [
        # Italian Examples
        "./LawsDocs/PDFs_URLCodes_entryDate/2021/9_15.01_Legge federale.pdf", # Has YYYYM pattern
        "./LawsDocs/PDFs_URLCodes_entryDate/2006/33_31.01_Ordinanza del Consiglio federale.pdf", # Standard markers
        "./LawsDocs/PDFs_URLCodes_entryDate/1998/10_01.11_Trattato internazionale multilaterale.pdf", # Standard markers
        # Add more complex PDFs if available
    ]
    test_output_dir = "./extracted_pdf_sections_TEST"
    os.makedirs(test_output_dir, exist_ok=True)
    # --- End Configuration ---

    all_results = {} # Store results for comparison or combined output

    for pdf_file in test_pdf_files:
        if not os.path.exists(pdf_file):
            print(f"\nTest Error: PDF file not found at {pdf_file}")
            continue

        base_name = os.path.splitext(os.path.basename(pdf_file))[0]
        cleaned_base_name = re.sub(r'[.\s\-]+', '_', base_name)
        law_id_for_test = f"TEST_{cleaned_base_name}"

        processed_sections = process_pdf_file(pdf_file, law_id_for_test)

        if processed_sections:
            output_data = {
                "law_identifier_used": law_id_for_test,
                "processed_pdf": os.path.basename(pdf_file),
                "sections": processed_sections
            }
            all_results[pdf_file] = output_data # Store result

            output_json_file = os.path.join(test_output_dir, f"{law_id_for_test}_output.json")
            try:
                with open(output_json_file, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                print(f"Test output saved successfully to: {output_json_file}")
            except Exception as e:
                print(f"\nError saving test output JSON for {pdf_file}: {e}")
        else:
            print(f"\nProcessing failed for {pdf_file}, no test output generated.")
            all_results[pdf_file] = {"error": "Processing failed"}

    # Optional: Save all results to a single file
    combined_output_file = os.path.join(test_output_dir, "___COMBINED_PDF_TEST_RESULTS.json")
    try:
        with open(combined_output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\nCombined test results saved to: {combined_output_file}")
    except Exception as e:
        print(f"\nError saving combined test output JSON: {e}")

# --- END OF FILE pdf_processor.py ---