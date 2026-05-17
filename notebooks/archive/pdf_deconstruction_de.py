import fitz  # PyMuPDF
import json
import os
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# add logs to a file

def extract_and_add_ids(pdf_path, output_json_path):
    """
    Extracts text data from a PDF using PyMuPDF's 'dict' format
    and adds hierarchical IDs to each page, block, line, and span.

    Args:
        pdf_path (str): Path to the input PDF file.
        output_json_path (str): Path to save the output JSON file with IDs.
    """
    # logging.info(f"Processing PDF: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
        all_pages_data_with_ids = []

        for page_idx, page in enumerate(doc):
            page_id = f"page-{page_idx}"
            # logging.debug(f"Processing {page_id}")

            # Extract text with detailed information
            # TEXTFLAGS_TEXT (0) is default and usually sufficient if we check flags later
            # Add other flags if needed, e.g., fitz.TEXTFLAGS_PRESERVE_LIGATURES etc.
            page_dict = page.get_text("dict", flags=0) 

            # --- Add Hierarchical IDs ---
            page_data_with_ids = {
                "page_number": page.number + 1, # User-friendly 1-based index
                "hierarchical_id": page_id,      # Add ID to the page level
                "blocks": []
            }

            for block_idx, block in enumerate(page_dict.get("blocks", [])):
                block_id = f"{page_id}.block-{block_idx}"
                block_data_with_ids = {
                    "hierarchical_id": block_id, # Add ID to block
                    "bbox": block.get("bbox"),
                    "lines": []
                    # Add other block keys if needed ('type', 'number')
                }

                for line_idx, line in enumerate(block.get("lines", [])):
                    line_id = f"{block_id}.line-{line_idx}"
                    line_data_with_ids = {
                        "hierarchical_id": line_id, # Add ID to line
                        "bbox": line.get("bbox"),
                        "spans": []
                        # Add other line keys if needed ('wmode', 'dir')
                    }

                    for span_idx, span in enumerate(line.get("spans", [])):
                        span_id = f"{line_id}.span-{span_idx}"
                        # Create a new span dictionary including the ID and original keys
                        span_data_with_ids = {
                            "hierarchical_id": span_id, # Add ID to span
                            **span # Unpack all original span keys (text, font, size, flags, color, etc.)
                        }
                        
                        # Explicitly add the is_superscript check result here for convenience later
                        span_data_with_ids["is_superscript"] = bool(span.get('flags', 0) & fitz.TEXT_FONT_SUPERSCRIPT)

                        line_data_with_ids["spans"].append(span_data_with_ids)

                    block_data_with_ids["lines"].append(line_data_with_ids)

                page_data_with_ids["blocks"].append(block_data_with_ids)

            all_pages_data_with_ids.append(page_data_with_ids)

        doc.close()

        # Save the enhanced JSON data
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(all_pages_data_with_ids, f, ensure_ascii=False, indent=4)

        logging.info(f"Successfully extracted text with IDs to: {output_json_path}")
        return True

    except Exception as e:
        logging.critical(f"CRITICAL ERROR processing {pdf_path}: {e}", exc_info=True)
        return False


# --- Example Usage ---
def start_processing(PDF_INPUT_DIR, JSON_OUTPUT_DIR):

    if not os.path.isdir(PDF_INPUT_DIR):
        logging.error(f"Input PDF directory not found: {PDF_INPUT_DIR}")
    else:
        if not os.path.isdir(JSON_OUTPUT_DIR):
            # logging.warning(f"Output JSON directory '{JSON_OUTPUT_DIR}' not found. Creating it.")
            os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)
            
    processed_count = 0
    error_count = 0
    for filename in os.listdir(PDF_INPUT_DIR):
        if filename.lower().endswith(".pdf"):
            pdf_file_path = os.path.join(PDF_INPUT_DIR, filename)
            # Create a corresponding output filename
            json_filename = os.path.splitext(filename)[0] + ".json"
            output_file_path = os.path.join(JSON_OUTPUT_DIR, json_filename)

            if extract_and_add_ids(pdf_file_path, output_file_path):
                    processed_count += 1
            else:
                    error_count += 1

    if error_count > 0:
        logging.error(f"Finished processing with errors. Successfully processed: {processed_count}, Errors: {error_count}")


if __name__ == "__main__":
    # --- Configuration ---
    # Directory containing the PDF files you want to process
    PDF_INPUT_DIR = "./LawsDocs/for_processing/PDFs/Legge federale" 
    # Directory where the JSON files with hierarchical IDs will be saved
    JSON_OUTPUT_DIR = "./LawsDocs/for_processing/JSONs/Legge federale_in" 
    
    start_processing(PDF_INPUT_DIR, JSON_OUTPUT_DIR)