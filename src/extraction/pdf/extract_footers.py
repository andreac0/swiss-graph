import fitz  # PyMuPDF for PDF processing
import re    # Regular expressions for pattern matching
import json  # For JSON output
import logging # For logging progress and issues
from pathlib import Path # For modern path handling
import sys   # For directing log output to console
import os    # Used indirectly by pathlib
# No longer need statistics import

# --- Configuration ---
PARENT_FOLDER = Path("./LawsDocs/PDFs_TypeDoc")
OUTPUT_JSON_FILE = Path("0.60_swiss_law_footers_pdf_min_x0_margin.json") # Updated filename
FILE_PATTERN = "*.pdf"

# --- Adaptive Threshold Configuration ---
DEFAULT_FOOTER_AREA_THRESHOLD_PERCENT = 0.60
THRESHOLD_ADJUSTMENT_STEP = 0.05
MIN_FOOTER_AREA_THRESHOLD_PERCENT = 0.60

# --- Filtering & Validation Configuration ---
MAX_ALLOWED_FOOTNOTE_GAP = 3
# Tolerance (in points) for how close a footnote's x0 must be to the page's effective margin
MARGIN_X0_TOLERANCE_POINTS = 10 # Keep a small tolerance
# Default margin assumed if page analysis fails
DEFAULT_EFFECTIVE_MARGIN = 30.0
# Vertical margins (as percentage) to exclude blocks when calculating effective margin
HEADER_FOOTER_MARGIN_PERCENT = 0.10 # Exclude top 10% and bottom 10%

# --- Regex Configuration ---
NUMBERED_LINE_REGEX = re.compile(r"^\s*(\d+)\s+(.*)")
STARTS_WITH_DIGITS_REGEX = re.compile(r"^\s*\d+")
PAGE_NUMBER_REGEX = re.compile(r"^\s*\/\s*\d+(\s*\/\s*\d+)?\s*$")

# --- Setup Logging ---
log_file_path = Path("footer_extraction_pdf_min_x0_margin.log") # Updated filename
if log_file_path.exists():
    log_file_path.unlink()

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path, encoding='utf-8'),
                        logging.StreamHandler(sys.stdout)
                    ])

# --- Helper Functions ---

def clean_text(text):
    """Cleans extracted text."""
    if text is None: return ""
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

def determine_effective_left_margin(page, blocks):
    """
    Analyzes text blocks on a page to determine the effective left margin (x0)
    by finding the minimum x0 among significant content blocks.
    Excludes headers, footers, very wide blocks, and very short blocks.
    """
    page_height = page.rect.height
    page_width = page.rect.width
    # Define vertical boundaries to exclude headers/footers
    header_y_limit = page_height * HEADER_FOOTER_MARGIN_PERCENT
    footer_y_limit = page_height * (1 - HEADER_FOOTER_MARGIN_PERCENT)

    content_x0_coords = [] # List to store x0 values of potential content blocks
    # Iterate through all blocks extracted from the page
    for (x0, y0, x1, y1, block_text, block_no, block_type) in blocks:
        # Filter 1: Check if block is within the vertical content area (not header/footer)
        if y0 > header_y_limit and y1 < footer_y_limit:
            # Filter 2: Check if block width is less than 90% of page width (exclude full-width titles/etc.)
            if (x1 - x0) < (page_width * 0.9):
                 # Filter 3: Check if block has a minimum amount of text (exclude noise)
                 if len(block_text.strip()) > 10:
                     # If all filters pass, add the block's starting x-coordinate
                     content_x0_coords.append(x0)

    # Calculate minimum x0 if any valid content blocks were found
    if content_x0_coords:
        try:
            # Find the minimum x0 value among the filtered content blocks
            effective_margin = min(content_x0_coords)
            logging.debug(f"Page {page.number + 1}: Effective margin (min x0) calculated: {effective_margin:.2f} from {len(content_x0_coords)} candidate blocks.")
            return effective_margin
        except Exception as e:
            # Log error if min calculation fails unexpectedly
            logging.warning(f"Page {page.number + 1}: Error calculating min margin: {e}. Using default.")
            return DEFAULT_EFFECTIVE_MARGIN
    else:
        # If no blocks passed the filters, log a warning and return the default margin
        logging.warning(f"Page {page.number + 1}: Could not find significant content blocks to determine margin. Using default {DEFAULT_EFFECTIVE_MARGIN}.")
        return DEFAULT_EFFECTIVE_MARGIN

# --- Core Processing Function ---
# (No changes needed inside extract_and_validate_footers itself,
# as it just uses the value returned by determine_effective_left_margin)
def extract_and_validate_footers(pdf_path, current_threshold_percent):
    """Core logic using dynamic margin detection (now based on min x0)."""
    logging.info(f"Processing {pdf_path.name} with threshold {current_threshold_percent:.2f}")
    potential_footers_this_pdf = []
    gaps_detected_this_run = False
    warnings_list_for_this_run = []

    try: category = pdf_path.parent.name
    except Exception as e:
        logging.warning(f"Could not determine category for {pdf_path.name}: {e}")
        warnings_list_for_this_run.append("Category determination failed")
        category = "unknown"

    try:
        with fitz.open(pdf_path) as doc:
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                footer_y_threshold = page.rect.height * current_threshold_percent

                try: blocks = page.get_text("blocks", sort=True)
                except Exception as e:
                    log_msg = f"Block extraction failed on page {page_num + 1}: {e}"
                    logging.warning(log_msg); warnings_list_for_this_run.append(f"Block extraction failed on page {page_num + 1}"); continue

                # Determine effective margin using the MINIMUM x0 method
                page_effective_margin_x0 = determine_effective_left_margin(page, blocks)

                for (x0, y0, x1, y1, block_text, block_no, block_type) in blocks:
                    if y0 >= footer_y_threshold:
                        lines = block_text.strip().split('\n')
                        line_idx = 0
                        while line_idx < len(lines):
                            line = lines[line_idx]
                            match = NUMBERED_LINE_REGEX.match(line)
                            processed_multiline_or_skipped = False

                            if match:
                                # Dynamic Margin Check (using min x0)
                                if abs(x0 - page_effective_margin_x0) < MARGIN_X0_TOLERANCE_POINTS:
                                    try:
                                        number = int(match.group(1))
                                        current_footer_lines = [match.group(2).strip()]
                                        next_line_idx = line_idx + 1
                                        while next_line_idx < len(lines):
                                            next_line = lines[next_line_idx].strip()
                                            if next_line and not STARTS_WITH_DIGITS_REGEX.match(next_line):
                                                current_footer_lines.append(next_line); next_line_idx += 1
                                            else: break
                                        full_text = " ".join(current_footer_lines)
                                        cleaned_full_text = clean_text(full_text)

                                        if PAGE_NUMBER_REGEX.match(cleaned_full_text):
                                            logging.info(f"Skipping likely page number '{cleaned_full_text}' for number {number} on page {page_num+1}")
                                        else:
                                            potential_footers_this_pdf.append({
                                                "number": number, "text": cleaned_full_text,
                                                "page": page_num + 1, "y_coord": y0, "x_coord": x0,
                                                "raw_block": block_text.strip()
                                            })
                                        line_idx = next_line_idx; processed_multiline_or_skipped = True
                                    except ValueError:
                                        log_msg = f"Number parsing failed on page {page_num+1} for line: '{line}'"
                                        logging.warning(log_msg); warnings_list_for_this_run.append(f"Number parsing failed on page {page_num+1}")
                                    except Exception as e:
                                        log_msg = f"Line processing error on page {page_num+1} for line '{line}': {e}"
                                        logging.warning(log_msg); warnings_list_for_this_run.append(f"Line processing error on page {page_num+1}")
                                else: # Margin check failed
                                    log_msg = f"Skipping potential footnote {match.group(1)} on page {page_num+1} because x-coordinate {x0:.2f} is not close to page's effective margin {page_effective_margin_x0:.2f} (tolerance: {MARGIN_X0_TOLERANCE_POINTS})"
                                    logging.warning(log_msg); warnings_list_for_this_run.append(f"Footnote number {match.group(1)} skipped on page {page_num+1} (X-margin check)")

                            if not processed_multiline_or_skipped: line_idx += 1

    except Exception as e:
        logging.error(f"Critical error processing PDF {pdf_path.name}: {e}")
        return None, False, ["Critical PDF processing error"]

    # --- Sequence Validation (Identical logic) ---
    if not potential_footers_this_pdf:
        logging.info(f"No potential footers found/kept for {pdf_path.name} at threshold {current_threshold_percent:.2f}")
        result_data = { "filename": pdf_path.name, "category": category, "number_of_references": 0, "references": [] }
        return result_data, False, warnings_list_for_this_run

    sorted_potential_footers = sorted(potential_footers_this_pdf, key=lambda x: (x["number"], x["page"], x["y_coord"]))
    final_references_this_pdf = []
    last_valid_number = 0

    for p_footer in sorted_potential_footers:
        current_num = p_footer["number"]; page_found = p_footer['page']
        if current_num == last_valid_number + 1:
            final_references_this_pdf.append({str(current_num): p_footer["text"]}); last_valid_number = current_num
        elif last_valid_number < current_num <= last_valid_number + 1 + MAX_ALLOWED_FOOTNOTE_GAP:
            gaps_detected_this_run = True; gap_msg = f"Acceptable gap detected: expected {last_valid_number + 1}, found {current_num} on page {page_found}"
            logging.warning(f"{gap_msg} in {pdf_path.name} (Thresh: {current_threshold_percent:.2f}). Accepting.")
            warnings_list_for_this_run.append(gap_msg); final_references_this_pdf.append({str(current_num): p_footer["text"]}); last_valid_number = current_num
        else:
            if current_num <= last_valid_number: reason = f"out of order (expected > {last_valid_number})"
            else: reason = f"gap too large (expected <= {last_valid_number + 1 + MAX_ALLOWED_FOOTNOTE_GAP})"
            seq_err_msg = f"Sequence error: found {current_num} on page {page_found}, reason: {reason}"
            logging.warning(f"{seq_err_msg} in {pdf_path.name} (Thresh: {current_threshold_percent:.2f}). Skipping.")
            warnings_list_for_this_run.append(seq_err_msg)

    num_refs = len(final_references_this_pdf)
    logging.info(f"Validation complete for {pdf_path.name} (Thresh: {current_threshold_percent:.2f}). Found {num_refs} refs. Gaps Detected: {gaps_detected_this_run}")
    result_data = { "filename": pdf_path.name, "category": category, "number_of_references": num_refs, "references": final_references_this_pdf }
    return result_data, gaps_detected_this_run, warnings_list_for_this_run


# --- Adaptive Processing Wrapper (Identical logic) ---

def process_pdf_adaptively(pdf_path):
    """Processes PDF with adaptive threshold, collecting concise warnings."""
    current_threshold = DEFAULT_FOOTER_AREA_THRESHOLD_PERCENT
    last_result_data = None
    last_run_warnings = []

    while True:
        result_data, gaps_found, current_run_warnings = extract_and_validate_footers(pdf_path, current_threshold)

        # Store results from the latest attempt
        last_run_warnings = current_run_warnings
        if result_data is not None:
            last_result_data = result_data

        # Handle critical errors first
        if result_data is None:
             logging.error(f"Adaptive processing failed for {pdf_path.name} due to critical error. Warnings from last attempt: {last_run_warnings}")
             try: category = pdf_path.parent.name
             except: category = "unknown"
             return {"filename": pdf_path.name, "category": category, "number_of_references": 0, "references": [], "warnings": ["Critical PDF processing error"]}

        # --- Check Stop Conditions ---
        # Condition 1: No gaps found AND references were actually found
        if not gaps_found and last_result_data["references"]:
            logging.info(f"Successful processing for {pdf_path.name} at threshold {current_threshold:.2f} (no gaps, references found).")
            # Filter out any "Acceptable gap" warnings (though none should exist if gaps_found is False)
            final_warnings = [w for w in last_run_warnings if not w.startswith("Acceptable gap detected:")]
            last_result_data["warnings"] = sorted(list(set(final_warnings)))
            return last_result_data

        # --- Conditions to Continue Adapting ---
        # Condition 2: Gaps were found OR (No gaps were found BUT no references were found)
        if gaps_found:
             logging.warning(f"Gaps detected for {pdf_path.name} at threshold {current_threshold:.2f}. Attempting lower threshold.")
        else: # Implies not gaps_found and not last_result_data["references"]
             logging.warning(f"No gaps found, but also no references found at threshold {current_threshold:.2f}. Attempting lower threshold to find potential single footnotes.")

        # --- Lower Threshold Logic ---
        current_threshold -= THRESHOLD_ADJUSTMENT_STEP

        # Check if minimum threshold is reached
        if current_threshold < MIN_FOOTER_AREA_THRESHOLD_PERCENT:
            min_thresh_msg = f"Minimum threshold ({MIN_FOOTER_AREA_THRESHOLD_PERCENT:.2f}) reached"
            # Add specific warning based on whether the *last* attempt still had gaps
            if gaps_found:
                min_thresh_msg += " without resolving gaps"
            else:
                 min_thresh_msg += " without finding references"

            logging.error(f"{min_thresh_msg} for {pdf_path.name}. Using results from last attempt (Thresh: {current_threshold + THRESHOLD_ADJUSTMENT_STEP:.2f}).")
            # Filter out acceptable gap warnings from the *last* run's warnings
            final_warnings = [w for w in last_run_warnings if not w.startswith("Acceptable gap detected:")]
            final_warnings.insert(0, min_thresh_msg) # Add the specific failure reason
            last_result_data["warnings"] = sorted(list(set(final_warnings)))
            # Make sure references list exists, even if empty
            if "references" not in last_result_data: last_result_data["references"] = []
            if "number_of_references" not in last_result_data: last_result_data["number_of_references"] = 0

            return last_result_data
        # Otherwise, the loop continues with the new, lower threshold


# --- Main Execution (Identical logic) ---
def main():
    """Main workflow orchestrator."""
    if not PARENT_FOLDER.is_dir(): logging.error(f"Parent folder not found: {PARENT_FOLDER}"); return
    logging.info(f"Starting PDF footer extraction from: {PARENT_FOLDER}")
    logging.info(f"Default Threshold: {DEFAULT_FOOTER_AREA_THRESHOLD_PERCENT:.2f}, Min Threshold: {MIN_FOOTER_AREA_THRESHOLD_PERCENT:.2f}, Step: {THRESHOLD_ADJUSTMENT_STEP:.2f}")
    logging.info(f"Max Allowed Gap: {MAX_ALLOWED_FOOTNOTE_GAP}, Margin Tolerance: {MARGIN_X0_TOLERANCE_POINTS} points")
    all_files_data = []; processed_files = 0; failed_files = 0
    pdf_paths = list(PARENT_FOLDER.rglob(FILE_PATTERN))
    logging.info(f"Found {len(pdf_paths)} files matching '{FILE_PATTERN}'"); total_files = len(pdf_paths)
    for i, pdf_path in enumerate(pdf_paths):
        logging.info(f"--- Processing file {i+1}/{total_files}: {pdf_path.name} ---")
        if pdf_path.is_file():
            file_data = process_pdf_adaptively(pdf_path)
            if file_data is not None:
                if "warnings" not in file_data: file_data["warnings"] = []
                all_files_data.append(file_data); processed_files += 1
                if file_data.get("warnings") == ["Critical PDF processing error"]: failed_files += 1
        else: logging.warning(f"Skipping non-file item: {pdf_path}")
    logging.info(f"--- Processing Summary ---")
    logging.info(f"Total files found: {total_files}"); logging.info(f"Files processed (result generated): {processed_files}"); logging.info(f"Files with critical processing errors: {failed_files}")
    try:
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f: json.dump(all_files_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Successfully wrote results to {OUTPUT_JSON_FILE}")
    except Exception as e: logging.error(f"Error writing JSON output to {OUTPUT_JSON_FILE}: {e}")

if __name__ == "__main__":
    OUTPUT_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    main()