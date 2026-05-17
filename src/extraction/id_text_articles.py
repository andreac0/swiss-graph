import csv

def find_longest_text_in_csv(filepath):
    """
    Finds the longest text in the 'text' column of a CSV file and its length.

    Args:
        filepath (str): The path to the CSV file.

    Returns:
        tuple: (longest_text_content, length_of_longest_text, id_of_longest_text)
               Returns (None, 0, None) if the file is not found, 'text' column is missing,
               or no text data is found.
    """
    longest_text_content = ""
    max_length = 0
    id_of_longest_text = None

    try:
        with open(filepath, mode='r', encoding='utf-8', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            
            if 'text' not in reader.fieldnames:
                print(f"Error: 'text' column not found in the CSV header: {reader.fieldnames}")
                return None, 0, None

            for row_number, row in enumerate(reader, start=2): # start=2 for 1-based indexing + header
                # Get the text from the 'text' column.
                # Use .get() with a default to handle cases where 'text' might be missing
                # in a specific row, though DictReader usually ensures all keys are present
                # (with None value if cell was empty).
                current_text = row.get('text')

                if current_text is None: # Handle if a text cell is explicitly None or empty
                    current_text = ""
                
                current_length = len(current_text)
                
                if current_length > max_length:
                    max_length = current_length
                    longest_text_content = current_text
                    id_of_longest_text = row.get('id', f"Row {row_number}") # Use 'id' if available, else row number

    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return None, 0, None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None, 0, None

    return longest_text_content, max_length, id_of_longest_text

# --- Main execution ---
if __name__ == "__main__":
    # The path to your CSV file
    # Make sure this path is correct for your environment
    csv_file_path = './LawsDocs/processed/CSVs_from_JSONs_split/Legge federale.csv'
    
    longest_text, length, text_id = find_longest_text_in_csv(csv_file_path)
    
    if longest_text is not None:
        if length > 0:
            print(f"The longest text is from ID/Row: {text_id}")
            print(f"Length of the longest text: {length} characters")
            print("\nContent of the longest text:")
            # To avoid printing an extremely long string directly to the console,
            # you might want to print a snippet or just confirm its existence.
            # For this example, we'll print it if it's not excessively long.
            if length < 2000: # Arbitrary limit for console output
                 print(longest_text)
            else:
                 print(f"(Content is too long to display here, starts with: '{longest_text[:200]}...')")
        else:
            print("No text data found in the 'text' column or all text entries were empty.")
