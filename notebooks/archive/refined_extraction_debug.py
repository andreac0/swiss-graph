from article_reconstruction import start_reconstruction
from refined_extraction import start_analysis
from pdf_deconstruction import start_processing
# cycle through every subdirectory of "./LawsDocs/for_processing/PDFs/"
from split_allegato import start_splitting
import os
import subprocess

def process_directory(directory):
    
    JSON_OUTPUT_TEMPLATE = f"./LawsDocs/for_processing/fr/JSON_in/{directory.split("/")[-1]}"
    start_processing(directory, JSON_OUTPUT_TEMPLATE)

    JSON_INPUT_DIR_WITH_IDS = f"./LawsDocs/for_processing/fr/JSON_in/{directory.split("/")[-1]}"
    ANALYSIS_OUTPUT_DIR = f"./LawsDocs/for_processing/fr/JSON_in_split/{directory.split("/")[-1]}"
    start_splitting(JSON_INPUT_DIR_WITH_IDS, ANALYSIS_OUTPUT_DIR)

    JSON_INPUT_DIR_WITH_IDS = f"./LawsDocs/for_processing/fr/JSON_in_split/{directory.split("/")[-1]}"
    ANALYSIS_OUTPUT_DIR = f"./LawsDocs/for_processing/fr/JSON_out_split/{directory.split("/")[-1]}"
    start_analysis(JSON_INPUT_DIR_WITH_IDS, ANALYSIS_OUTPUT_DIR)

    FULL_TEXT_JSON_DIR = f"./LawsDocs/for_processing/fr/JSON_in_split/{directory.split("/")[-1]}"
    ANALYSIS_JSON_DIR = f"./LawsDocs/for_processing/fr/JSON_out_split/{directory.split("/")[-1]}"
    FINAL_OUTPUT_DIR = f"./LawsDocs/processed/fr/JSONs_split_with_fn_placeholders/{directory.split("/")[-1]}"
    start_reconstruction(FULL_TEXT_JSON_DIR, ANALYSIS_JSON_DIR, FINAL_OUTPUT_DIR)

def main():
    # Define the base directory
    base_directory = "./LawsDocs/for_processing/PDFs_fr/"
    
    # Walk through the directory tree
    for root, dirs, files in os.walk(base_directory):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            print(f"Entering directory: {dir_path}")
            process_directory(dir_path)


if __name__ == "__main__":
    main()