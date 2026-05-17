import json
import spacy
import textstat
import pandas as pd
import os
import copy

# --- 1. Configuration and Setup ---
# Define file paths for JSON files to be processed
JSON_FILES = {
    'it': "./scripts/language_analysis/comprehensive_italian_legal_texts.json",
    'fr': "./scripts/language_analysis/comprehensive_french_legal_texts.json",
    'de': "./scripts/language_analysis/comprehensive_german_legal_texts.json"
}

# create output files for each language 
OUTPUT_FILES = {
    'it': './scripts/language_analysis/italian_legal_texts_analysis.json',
    'fr': './scripts/language_analysis/french_legal_texts_analysis.json',
    'de': './scripts/language_analysis/german_legal_texts_analysis.json'
}

# spaCy model mapping
SPACY_MODELS = {
    'it': 'it_core_news_lg',
    'fr': 'fr_core_news_lg',
    'de': 'de_core_news_lg'
}

def download_spacy_models():
    """Checks if spaCy models are installed and downloads them if not."""
    print("\n--- Checking for spaCy models ---")
    for lang, model in SPACY_MODELS.items():
        try:
            spacy.load(model)
            print(f"Model '{model}' for {lang.upper()} is already installed.")
        except OSError:
            print(f"Model '{model}' for {lang.upper()} not found. Downloading...")
            spacy.cli.download(model)
            print(f"Model '{model}' downloaded successfully.")

def analyze_text(text: str, lang: str, spacy_doc):
    """
    Analyzes a single piece of text and returns a dictionary of metrics.
    
    Args:
        text (str): The text content to analyze.
        lang (str): The language code ('it', 'fr', 'de').
        spacy_doc: The processed spaCy Doc object.

    Returns:
        dict: A dictionary containing all calculated metrics.
    """
    # --- Language-Agnostic Metrics ---
    words = [token for token in spacy_doc if not token.is_punct and not token.is_space]
    word_count = len(words)
    sentence_count = len(list(spacy_doc.sents))
    
    # Avoid division by zero for empty or very short texts
    if word_count == 0 or sentence_count == 0:
        return {
            "error": "Text section is too short or empty for analysis."
        }
        
    avg_word_length = sum(len(word.text) for word in words) / word_count
    avg_sentence_length = word_count / sentence_count

    # Lexical Diversity (TTR on lemmas) - more robust for comparison
    lemmas = [
        token.lemma_.lower() 
        for token in spacy_doc if not token.is_punct and not token.is_space and not token.is_stop
    ]
    ttr_lemmas = len(set(lemmas)) / len(lemmas) if lemmas else 0

    # --- Language-Specific Readability Index ---
    readability_score = None
    readability_index_name = "N/A"
    
    # IMPORTANT: These scores are NOT directly comparable.
    # We calculate the appropriate index for each language's context.
    if lang == 'it':
        readability_index_name = "Gulpease"
        readability_score = textstat.gulpease_index(text)
    elif lang in ['fr', 'de']:
        # Using Flesch Reading Ease as a common proxy for both
        readability_index_name = "Flesch Reading Ease"
        readability_score = textstat.flesch_reading_ease(text)

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_word_length_chars": avg_word_length,
        "avg_sentence_length_words": avg_sentence_length,
        "lexical_diversity_ttr_lemmas": ttr_lemmas,
        "readability_index": readability_index_name,
        "readability_score": readability_score
    }

def main():
    """Main function to run the full analysis pipeline."""
    
    # Perform initial setup
    download_spacy_models()
    
    # Load spaCy models into memory
    print("\n--- Loading spaCy models into memory ---")
    spacy_models = {lang: spacy.load(model) for lang, model in SPACY_MODELS.items()}
    print("All models loaded.")

    all_analyzed_data = {}
    flat_results_for_summary = []

    print("\n--- Starting Text Analysis ---")
    for lang, filepath in JSON_FILES.items():
        print(f"\nProcessing language: {lang.upper()} from file: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Could not read or parse {filepath}. Error: {e}")
            continue

        # Use a deep copy to avoid modifying the original data structure in place
        data_to_modify = copy.deepcopy(original_data)
        
        # Navigate the nested JSON structure
        for folder in data_to_modify:
            for file_obj in folder.get("file_list", []):
                for section in file_obj.get("sections_text_list", []):
                    text_content = section.get("text", "")
                    
                    if not text_content.strip():
                        section["analysis"] = {"error": "Empty text section."}
                        continue
                    
                    # Process text with the correct spaCy model
                    doc = spacy_models[lang](text_content)
                    
                    # Calculate metrics
                    analysis_results = analyze_text(text_content, lang, doc)
                    
                    # Inject the results back into the JSON structure
                    section["analysis"] = analysis_results
                    
                    # Append to our flat list for the final summary report
                    if "error" not in analysis_results:
                        flat_results_for_summary.append({
                            "language": lang.upper(),
                            "marker": section.get("marker", "N/A"),
                            **analysis_results # Unpack the results dictionary
                        })

        all_analyzed_data[lang] = data_to_modify

        # Save the enriched data to a new JSON file
        output_path = OUTPUT_FILES[lang]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_modify, f, indent=2, ensure_ascii=False)
        print(f"Analysis complete. Enriched data saved to '{output_path}'")

    # --- 5. Generate and Print Summary Report ---
    print("\n\n--- AGGREGATE ANALYSIS REPORT ---")
    if not flat_results_for_summary:
        print("No data was processed, cannot generate a report.")
        return
        
    df = pd.DataFrame(flat_results_for_summary)
    
    # Calculate average metrics per language
    # Note: Readability scores are not directly comparable but we show the average for context.
    summary_df = df.groupby('language').agg({
        'word_count': 'mean',
        'sentence_count': 'mean',
        'avg_word_length_chars': 'mean',
        'avg_sentence_length_words': 'mean',
        'lexical_diversity_ttr_lemmas': 'mean',
        'readability_score': 'mean' # Acknowledge this is comparing different scales
    }).round(2)

    print("Average Metrics per Language (based on all text sections):")
    print(summary_df)
    
    print("\n*Note on Readability Scores:")
    print("The 'readability_score' averages are shown for context but are NOT directly comparable.")
    print(" - Italian (IT) uses the Gulpease index (higher is easier).")
    print(" - French (FR) and German (DE) use the Flesch Reading Ease index (higher is easier).")
    print(" - A score of '50' for Gulpease does not mean the same as '50' for Flesch.")
    print("The most reliable comparisons are the language-agnostic metrics (word/sentence length, TTR).")


if __name__ == "__main__":
    main()