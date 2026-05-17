import re
import os
import json

import re
import os
import json

def classify_document_type_arabic(text):
    """
    Classifies the document type as 'Base', 'Modification', or 'Unknown'
    based on structure, now including numbered list modification patterns.

    Args:
        text: The full text content extracted from the document.

    Returns:
        'Base': If the primary structure seems to be Articles (Art. X) or Sezioni.
        'Modification': If primary structure uses Roman Numerals (I, II, ...),
                        contains explicit modification phrases, or uses a numbered
                        list format to modify other laws (like 1. Legge del...).
        'Unknown': If the type cannot be reliably determined.
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    if not lines:
        return "Unknown"

    preamble_end_index = -1
    preamble_enders = ['decreta:', 'ordina:', 'stabilisce:']
    first_section_markers = [
        r'^\s*Sezione\s+\d+',
        r'^\s*Art\.\s*\d+',
        r'^\s*(I|II|III|IV|V|VI|VII|VIII|IX|X)($|\s|\.)' # Roman numeral section
    ]

    # --- Preamble Detection (same as before) ---
    in_preamble = True
    for i, line in enumerate(lines):
        l_lower = line.lower()
        is_section_marker = any(re.match(pattern, line, re.IGNORECASE) for pattern in first_section_markers)
        looks_like_preamble_list = line.strip().startswith(('visti', 'vista', 'visto'))

        if is_section_marker and not looks_like_preamble_list :
            if i > 0:
                 prev_line = lines[i-1]
                 if any(ender in prev_line.lower() for ender in preamble_enders) or len(prev_line.split()) < 7:
                     preamble_end_index = i -1
                     in_preamble = False
                     break
            if i > 10:
                preamble_end_index = i - 1
                in_preamble = False
                break

        if any(ender in l_lower for ender in preamble_enders):
             preamble_end_index = i
             in_preamble = False
             break

        if i > 50 and preamble_end_index == -1:
             preamble_end_index = i
             in_preamble = False
             break

    if preamble_end_index == -1 and len(lines) > 0 :
         if len(lines[0].split()) > 10:
              preamble_end_index = -1
         else:
              preamble_end_index = 0

    start_search_index = preamble_end_index + 1
    full_relevant_text = "\n".join(lines[start_search_index:]) # Use full text post-preamble

    # --- Define Patterns ---
    mod_phrase_pattern = re.compile(r"è modificat[ao]\s+come\s+segue:", re.IGNORECASE)
    roman_section_pattern = re.compile(r"^\s*(?:(?:I|V|X){1,5}|L|C|D|M)\.?\s*$", re.IGNORECASE | re.MULTILINE)
    article_section_pattern = re.compile(r"^\s*Art\.\s*\d+[a-z]?\.?\s*$", re.IGNORECASE | re.MULTILINE)
    sezione_section_pattern = re.compile(r"^\s*(Sezione|Capitolo|Chapter|Section|Titel|Abschnitt)\s+\d+", re.IGNORECASE | re.MULTILINE)
    # New pattern for numbered lists modifying laws
    arabic_mod_list_pattern = re.compile(r"^\s*\d+\.\s+(Legge|Codice|Ordinanza|Procedura|Regolamento|Costituzione)\b", re.IGNORECASE | re.MULTILINE)

    # --- Classification Logic ---

    # 1. Strongest indicator: Explicit modification phrase
    if mod_phrase_pattern.search(full_relevant_text):
        return "Modification"

    # 2. Check for dominant structural markers (Roman vs Article/Sezione)
    # Use findall on the *whole relevant text* now for better context
    roman_matches = roman_section_pattern.findall(full_relevant_text)
    article_matches = article_section_pattern.findall(full_relevant_text)
    sezione_matches = sezione_section_pattern.findall(full_relevant_text)
    arabic_mod_matches = arabic_mod_list_pattern.findall(full_relevant_text)

    # 2a. If Roman numerals are present and likely the primary structure
    if len(roman_matches) > 0 and len(roman_matches) >= len(article_matches):
         # Check if "I" is followed by modification phrase (already covered by mod_phrase check)
         # Assume Modification if Roman numerals dominate
         if not (len(sezione_matches) > 0 or len(article_matches) > len(roman_matches)):
              return "Modification"

    # 2b. NEW: If the numbered list modification pattern is present
    if len(arabic_mod_matches) > 0:
         # This pattern is strong for annexes or specific modification laws.
         # Classify as Modification, unless a clear "Base" structure dominates.
         if not (len(sezione_matches) > 0 or len(article_matches) > len(roman_matches) + len(arabic_mod_matches)): # Check if Art/Sez substantially outnumber Roman+Arabic
              return "Modification"

    # 2c. If Article or Sezione markers are present and likely primary structure
    if len(sezione_matches) > 0 or len(article_matches) > 0 :
         # Check if it's not outweighed by Roman/Arabic modification markers
         if not roman_matches or len(article_matches) >= len(roman_matches):
             if not arabic_mod_matches or len(article_matches) >= len(arabic_mod_matches):
                 return "Base"

    # 3. Fallback: If only Roman found, but not dominant initially, still likely Modification
    if len(roman_matches) > 0:
        return "Modification"

    # 4. Default to Unknown if no clear pattern identified
    return "Unknown"

# --- Classification Function (remains the same) ---
def classify_document_type(text):
    """
    Classifies the document type as 'Base' or 'Modification' based on structure.
    (Implementation remains the same as the previous version)
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    if not lines:
        return "Unknown"

    preamble_end_index = -1
    preamble_enders = ['decreta:', 'ordina:', 'stabilisce:']
    first_section_markers = [
        r'^\s*Sezione\s+\d+',
        r'^\s*Art\.\s*\d+',
        r'^\s*(I|II|III|IV|V|VI|VII|VIII|IX|X)($|\s|\.)' # Roman numeral section
    ]

    # Try to find end of preamble more reliably
    in_preamble = True
    for i, line in enumerate(lines):
        l_lower = line.lower()
        # Stop considering preamble if a clear section marker is found
        # Ensure marker is not part of a preamble list like "visti gli articoli..."
        is_section_marker = any(re.match(pattern, line, re.IGNORECASE) for pattern in first_section_markers)
        looks_like_preamble_list = line.strip().startswith(('visti', 'vista', 'visto'))

        if is_section_marker and not looks_like_preamble_list :
            if i > 0: # Need a line before it to check
                 prev_line = lines[i-1]
                 # If previous line looks like preamble end or simple title
                 if any(ender in prev_line.lower() for ender in preamble_enders) or len(prev_line.split()) < 7: # Slightly more words allowed
                     preamble_end_index = i -1
                     in_preamble = False
                     break
            # If it's very early, might still be preamble (e.g. title block)
            # but if we are deeper, assume preamble ended
            if i > 10: # Heuristic: stop preamble search after 10 non-empty lines if no ender found
                preamble_end_index = i - 1
                in_preamble = False
                break

        if any(ender in l_lower for ender in preamble_enders):
             preamble_end_index = i
             in_preamble = False
             break

        # Fallback if no clear ender/marker found early
        if i > 50 and preamble_end_index == -1: # Arbitrary limit
             preamble_end_index = i
             in_preamble = False
             break

    if preamble_end_index == -1 and len(lines) > 0 :
         # If no preamble enders or section markers detected early,
         # assume preamble is minimal or absent if first line doesn't look like title.
         if len(lines[0].split()) > 10: # Heuristic: if first line is long, maybe no title/preamble
              preamble_end_index = -1
         else:
              preamble_end_index = 0 # Assume just title

    start_search_index = preamble_end_index + 1

    # Scan the *start* of the main body for primary structure indicators
    scan_limit = min(start_search_index + 75, len(lines))
    relevant_lines_start = lines[start_search_index:scan_limit]

    mod_phrase_pattern = re.compile(r"è modificat[ao]\s+come\s+segue:", re.IGNORECASE)
    # Strict Roman: Start of line, numeral I-X(V...), optional dot, maybe whitespace, then EOL or newline
    # Avoids matching things like "Art. 1 cpv. I"
    roman_section_pattern = re.compile(r"^\s*(?:(?:I|V|X){1,5}|L|C|D|M)\.?\s*$", re.IGNORECASE | re.MULTILINE)
    # Strict Article: Start of line, Art., optional space, number, optional letter, maybe dot, maybe whitespace, then EOL or newline
    article_section_pattern = re.compile(r"^\s*Art\.\s*\d+[a-z]?\.?\s*$", re.IGNORECASE | re.MULTILINE)
    # Section marker: Sezione X: ..., Chapter X ... etc.
    sezione_section_pattern = re.compile(r"^\s*(Sezione|Capitolo|Chapter|Section|Titel|Abschnitt)\s+\d+", re.IGNORECASE | re.MULTILINE)


    found_mod_phrase_start = False
    found_roman_section_start = False
    found_article_section_start = False
    found_sezione_section_start = False

    # --- Initial Scan (Post Preamble) ---
    initial_body_text = "\n".join(relevant_lines_start)

    if mod_phrase_pattern.search(initial_body_text):
        return "Modification" # Strongest indicator

    # Check for dominant section type right after preamble
    # Use findall to count occurrences in the initial block
    roman_matches_start = roman_section_pattern.findall(initial_body_text)
    article_matches_start = article_section_pattern.findall(initial_body_text)
    sezione_matches_start = sezione_section_pattern.findall(initial_body_text)

    # Heuristic: If Roman numerals appear frequently near the start, assume Modification structure
    # Or if 'Sezione X' appears followed by 'Art Y' which is typical for Base laws
    if len(roman_matches_start) > 0 and len(roman_matches_start) >= len(article_matches_start):
         # If "I" is immediately followed by "è modificata come segue:", very likely Modification
         first_roman_match_index = -1
         for i, line in enumerate(relevant_lines_start):
             if roman_section_pattern.match(line):
                 first_roman_match_index = i
                 break
         if first_roman_match_index != -1 and first_roman_match_index + 1 < len(relevant_lines_start):
              if mod_phrase_pattern.search(relevant_lines_start[first_roman_match_index + 1]):
                   return "Modification"
         # Otherwise, could still be Modification if Roman numerals dominate structure
         if len(roman_matches_start) > 0: # Requires at least one Roman numeral
             # check if there are also article/sezione markers that indicate a base law instead
             if not (len(sezione_matches_start) > 0 or len(article_matches_start) > len(roman_matches_start)):
                  return "Modification"


    if len(sezione_matches_start) > 0 or len(article_matches_start) > 0 :
         # If "Sezione" or "Art." markers are present early and Roman are absent or fewer, likely Base
         if not roman_matches_start or len(article_matches_start) >= len(roman_matches_start):
              return "Base"

    # --- Fallback Scan (Entire Text Post Preamble) ---
    # If initial scan was inconclusive, check the whole body
    full_relevant_text = "\n".join(lines[start_search_index:])
    if mod_phrase_pattern.search(full_relevant_text):
         return "Modification"

    roman_matches_full = roman_section_pattern.findall(full_relevant_text)
    article_matches_full = article_section_pattern.findall(full_relevant_text)
    sezione_matches_full = sezione_section_pattern.findall(full_relevant_text)

    # Broader heuristic: Modification if Roman numerals exist prominently anywhere after preamble
    # Base if Articles/Sezioni exist and Roman numerals are absent or very few.
    if len(roman_matches_full) > 0 and len(roman_matches_full) >= len(article_matches_full):
         # Double check if mod phrase exists within the roman section text
         first_roman_match_index_full = -1
         for i, line in enumerate(lines[start_search_index:]):
              if roman_section_pattern.match(line):
                  first_roman_match_index_full = i
                  break
         if first_roman_match_index_full != -1 and first_roman_match_index_full + 1 < len(lines[start_search_index:]):
              if mod_phrase_pattern.search(lines[start_search_index + first_roman_match_index_full + 1]):
                   return "Modification"
         # If only roman numerals without modification phrase, might be ambiguous, check further
         if not (len(sezione_matches_full) > 0 or len(article_matches_full) > 0):
              return "Modification" # Likely modification if no other structure present

    if len(sezione_matches_full) > 0 or len(article_matches_full) > 0:
         return "Base"

    # Default to Unknown if absolutely no structure identified
    return "Unknown"


# --- Processing Function (Modified Signature & Logic) ---
def process_and_split_document(os_filename, text_content, output_folder):
    """
    Processes a single document text, splits if Allegato found, classifies,
    and saves as JSON(s). Uses the provided OS filename.

    Args:
        os_filename (str): The actual filename from the operating system (e.g., "document1.txt").
        text_content (str): The full text content of the document.
        output_folder (str): The path to the folder where JSON files should be saved.
    """
    if not text_content.strip():
        print(f"Warning: Received empty text content for OS file: {os_filename}")
        return # Skip empty text

    # 1. Find Allegato marker
    allegato_pattern = re.compile(r"^\s*Allegato\b.*$", re.IGNORECASE | re.MULTILINE)
    allegato_match = allegato_pattern.search(text_content)

    outputs = [] # List to hold data for JSON output(s)

    # Derive the base filename (without extension) from the OS filename
    # This will be used for the JSON 'filename' field and the output file naming.
    base_filename_no_ext = os.path.splitext(os_filename)[0]

    if allegato_match:
        # 2a. Split into Main and Allegato
        split_index = allegato_match.start()
        main_text = text_content[:split_index].strip()
        allegato_text = text_content[split_index:].strip() # Includes the "Allegato" line itself
        print(f"  - Found Allegato, splitting '{os_filename}'.")

        # 3a. Classify both parts
        main_classification = classify_document_type_arabic(main_text)
        allegato_classification = classify_document_type_arabic(allegato_text) # Classify annex independently

        # 4a. Prepare data for JSON outputs using derived base filename
        if main_text:
            outputs.append({
                "filename": base_filename_no_ext, # Use filename without extension
                "classification": main_classification,
                "text": main_text
            })
        if allegato_text:
             outputs.append({
                "filename": f"{base_filename_no_ext}/Allegato", # Use filename without extension + /Allegato
                "classification": allegato_classification,
                "text": allegato_text
            })
    else:
        # 2b. No Allegato found
        main_text = text_content.strip()
        # 3b. Classify the whole document
        main_classification = classify_document_type_arabic(main_text)
        # 4b. Prepare data for JSON output using derived base filename
        if main_text:
            outputs.append({
                "filename": base_filename_no_ext, # Use filename without extension
                "classification": main_classification,
                "text": main_text
            })

    # 5. Save JSON output(s)
    for output_data in outputs:
        # Sanitize derived base filename for use in OS file paths
        sanitized_base_name = re.sub(r'[\\/*?:"<>| ]', '_', base_filename_no_ext) # Replace spaces too

        # Determine final JSON filename based on sanitized base name
        if output_data["filename"].endswith("/Allegato"):
            json_filename = f"{sanitized_base_name}_Allegato.json"
        else:
            json_filename = f"{sanitized_base_name}.json"

        output_filepath = os.path.join(output_folder, json_filename)

        try:
            with open(output_filepath, 'w', encoding='utf-8') as f_out:
                json.dump(output_data, f_out, ensure_ascii=False, indent=2)
            # print(f"  - Saved: {json_filename}")
        except IOError as e:
            print(f"  - Error writing file {json_filename}: {e}")
        except Exception as e:
             print(f"  - An unexpected error occurred while writing {json_filename}: {e}")


# --- Function to process a folder (Simplified for single doc per file) ---
def process_folder(input_folder, output_folder):
    """
    Iterates through .txt files in input_folder, processes each as a single document
    using its OS filename, splits if Allegato found, classifies, and saves
    results to output_folder.
    """
    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder)
            print(f"Created output folder: {output_folder}")
        except OSError as e:
            print(f"Error creating output folder '{output_folder}': {e}")
            return

    if not os.path.isdir(input_folder):
        print(f"Error: Input folder '{input_folder}' not found or is not a directory.")
        return

    processed_count = 0
    error_count = 0
    split_count = 0 # Count how many documents were split

    print(f"Starting processing from '{input_folder}' to '{output_folder}'...")

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(".txt"):
            input_filepath = os.path.join(input_folder, filename)
            print(f"Processing file: {filename}")
            try:
                with open(input_filepath, 'r', encoding='utf-8') as f_in:
                    # Read the entire file content as one document
                    full_content = f_in.read()

                initial_outputs = len(os.listdir(output_folder))

                # Process the entire content, passing the OS filename
                if full_content.strip():
                    # Use the OS filename here
                    process_and_split_document(filename, full_content.strip(), output_folder)
                else:
                    print(f"  - Skipping empty file: {filename}")

                final_outputs = len(os.listdir(output_folder))
                docs_created = final_outputs - initial_outputs
                if docs_created > 1: # If more than one JSON was created, it was split
                    split_count += 1

                processed_count += 1

            except FileNotFoundError:
                print(f"  - Error: File not found '{input_filepath}'")
                error_count += 1
            except Exception as e:
                print(f"  - Error processing file {filename}: {e}")
                error_count += 1

    print("\n--- Processing Summary ---")
    print(f"Processed {processed_count} input text files.")
    print(f"Generated JSON files in: {output_folder}")
    print(f"Number of documents split into Main + Allegato: {split_count}")
    if error_count > 0:
        print(f"Encountered {error_count} errors during processing.")
    print("-------------------------")


# --- Main Execution ---
if __name__ == "__main__":
    # --- Configuration ---
    # >>> IMPORTANT: Replace with your actual folder paths <<<
    INPUT_DIR = "./LawsDocs/TXT_TypeDoc/Legge federale"
    OUTPUT_DIR = "./LawsDocs/for_processing/JSON_TypeDoc/Legge federale new"
    # --- ------------- ---

    # Ensure paths are absolute or correctly relative
    INPUT_DIR = os.path.abspath(INPUT_DIR)
    OUTPUT_DIR = os.path.abspath(OUTPUT_DIR)

    if not os.path.isdir(INPUT_DIR):
         print(f"Error: Input directory '{INPUT_DIR}' does not exist.")
         print("Please create the input directory and place your single-document text files inside, or update the INPUT_DIR variable in the script.")
    else:
        process_folder(INPUT_DIR, OUTPUT_DIR)