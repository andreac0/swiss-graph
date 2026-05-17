import os
import fitz  # PyMuPDF: install via pip install pymupdf

# Define the source and destination directories
src_dir = "./LawsDocs/PDFs_TypeDoc"
dst_dir = "./LawsDocs/PDFs_transcripts"

# Ensure the base destination directory exists
os.makedirs(dst_dir, exist_ok=True)

# Walk through the directory tree in the source folder
for root, dirs, files in os.walk(src_dir):
    # --- FIX: Calculate relative path based on src_dir ---
    # Get the relative directory path (to recreate the same structure under dst_dir)
    # root = current directory being visited (e.g., /home/.../PDFs_TypeDoc/Subfolder)
    # src_dir = starting directory (e.g., /home/.../PDFs_TypeDoc)
    # rel_path = path relative to src_dir (e.g., Subfolder)
    rel_path = os.path.relpath(root, src_dir)

    # Construct the corresponding target directory path within the destination folder
    # If root == src_dir, rel_path will be '.', os.path.join handles this correctly
    target_dir = os.path.join(dst_dir, rel_path)

    # Create the corresponding directory in the destination folder
    # No need to create '.' if target_dir is just dst_dir
    if target_dir != dst_dir:
        os.makedirs(target_dir, exist_ok=True)

    for file in files:
        # Process only PDF files
        if file.lower().endswith(".pdf"):
            # Construct full file paths
            pdf_path = os.path.join(root, file)
            txt_filename = os.path.splitext(file)[0] + ".txt"
            txt_path = os.path.join(target_dir, txt_filename)

            try:
                # --- IMPROVEMENT: Use 'with' statement for automatic closing ---
                extracted_text = ""
                with fitz.open(pdf_path) as doc: # Open the PDF file
                    # Loop over the pages and extract text
                    for page_num, page in enumerate(doc): # Use enumerate if page number is needed later
                        extracted_text += page.get_text("text") # Specify text format explicitly
                        extracted_text += "\npage_break\n"
                    # No need for manual doc.close() when using 'with'

                # Save the extracted text into a text file
                with open(txt_path, "w", encoding="utf-8") as f_out:
                    f_out.write(extracted_text)

                print(f"Processed: {pdf_path} -> {txt_path}")
            except Exception as e:
                # Print specific error for better debugging
                print(f"Error processing file {pdf_path}: {type(e).__name__} - {e}")

print("\nProcessing complete.")