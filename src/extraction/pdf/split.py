import os
import re
import shutil # Used for copying files if no split is needed

# --- Configuration ---
# >>> IMPORTANT: Set your input and output folder paths here <<<
INPUT_FOLDER_RAW_TEXT = "./LawsDocs/TXT_TypeDoc/Legge federale" # Folder with original .txt files
OUTPUT_FOLDER_SPLIT = "./LawsDocs/TXT_TypeDoc/Legge federale_split" # Folder for potentially split .txt files
# --- ------------- ---

# Regex to find "Allegato" at the beginning of a line, case-insensitive
# Matches the whole line to ensure it's the primary marker for the section
ALLEGATO_REGEX = re.compile(r"^\s*Allegato\b.*$", re.MULTILINE)

def split_allegato_file(input_filepath, output_folder):
    """
    Reads a text file, splits it if an 'Allegato' marker is found,
    and saves the resulting part(s) as separate text files.

    Args:
        input_filepath (str): Path to the input text file.
        output_folder (str): Path to the folder where output files will be saved.

    Returns:
        bool: True if the file was split, False otherwise.
    """
    was_split = False
    try:
        # Derive base filename and extension
        base_name, ext = os.path.splitext(os.path.basename(input_filepath))

        with open(input_filepath, 'r', encoding='utf-8') as f_in:
            text_content = f_in.read()

        if not text_content or not text_content.strip():
            print(f"  - Skipping empty file: {os.path.basename(input_filepath)}")
            # Optionally copy the empty file if desired, otherwise just skip
            # output_filepath = os.path.join(output_folder, os.path.basename(input_filepath))
            # shutil.copy2(input_filepath, output_filepath) # Example of copying
            return False # Treat as not split

        # Search for the Allegato marker
        allegato_match = ALLEGATO_REGEX.search(text_content)

        if allegato_match:
            was_split = True
            split_index = allegato_match.start()
            main_text = text_content[:split_index].strip()
            allegato_text = text_content[split_index:].strip() # Includes the Allegato line
            print(f"  - Found Allegato marker. Splitting into _Main and _Allegato files.")

            # Define output filenames
            main_output_filename = f"{base_name}_Main{ext}"
            allegato_output_filename = f"{base_name}_Allegato{ext}"
            main_output_filepath = os.path.join(output_folder, main_output_filename)
            allegato_output_filepath = os.path.join(output_folder, allegato_output_filename)

            # Save the main part (only if it has content)
            if main_text:
                with open(main_output_filepath, 'w', encoding='utf-8') as f_out:
                    f_out.write(main_text)
                # print(f"    - Saved: {main_output_filename}")
            else:
                 print(f"    - Warning: Main part was empty after split for {base_name}{ext}.")


            # Save the Allegato part (should always have content if matched)
            with open(allegato_output_filepath, 'w', encoding='utf-8') as f_out:
                f_out.write(allegato_text)
            # print(f"    - Saved: {allegato_output_filename}")

        else:
            # No split needed, simply copy the original file to the output directory
            # print(f"  - No Allegato marker found. Copying original file.")
            output_filepath = os.path.join(output_folder, os.path.basename(input_filepath))
            # Use shutil.copy2 to preserve metadata like modification time
            shutil.copy2(input_filepath, output_filepath)
            # print(f"    - Copied to: {os.path.basename(input_filepath)}")

    except FileNotFoundError:
        print(f"  - Error: File not found '{input_filepath}'")
        return False # Indicate error/no split
    except IOError as e:
        print(f"  - Error reading/writing file related to '{os.path.basename(input_filepath)}': {e}")
        return False
    except Exception as e:
        print(f"  - An unexpected error occurred processing '{os.path.basename(input_filepath)}': {e}")
        return False

    return was_split


def process_folder_for_allegato(input_dir, output_dir):
    """
    Iterates through .txt files in input_dir, calls split_allegato_file for each,
    and saves results to output_dir.
    """
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output folder: {output_dir}")
        except OSError as e:
            print(f"Error creating output folder '{output_dir}': {e}")
            return

    if not os.path.isdir(input_dir):
        print(f"Error: Input folder '{input_dir}' not found or is not a directory.")
        return

    processed_count = 0
    split_count = 0
    error_count = 0

    print(f"Starting Allegato splitting from '{input_dir}' to '{output_dir}'...")

    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".txt"):
            input_filepath = os.path.join(input_dir, filename)
            # print(f"Processing file: {filename}") # Less verbose for large folders
            try:
                if split_allegato_file(input_filepath, output_dir):
                    split_count += 1
                processed_count += 1
            except Exception as e: # Catch errors during the call itself
                print(f"  - CRITICAL Error during call for file {filename}: {e}")
                error_count += 1


    print("\n--- Allegato Splitting Summary ---")
    print(f"Processed {processed_count} input text files.")
    print(f"Files split into Main/Allegato: {split_count}")
    print(f"Total output files created/copied in: {output_dir}")
    if error_count > 0:
        print(f"Encountered {error_count} critical errors during processing.")
    print("--------------------------------")


# --- Main Execution ---
if __name__ == "__main__":
    # --- Configuration ---
    # Ensure these are set correctly
    INPUT_FOLDER = os.path.abspath(INPUT_FOLDER_RAW_TEXT)
    OUTPUT_FOLDER = os.path.abspath(OUTPUT_FOLDER_SPLIT)
    # --- ------------- ---

    if not os.path.isdir(INPUT_FOLDER):
         print(f"Error: Input directory '{INPUT_FOLDER}' does not exist.")
    else:
        process_folder_for_allegato(INPUT_FOLDER, OUTPUT_FOLDER)