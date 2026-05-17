# Edge Classification for Swiss Law

This project focuses on the classification of relationships (edges) between legal articles and documents within the Swiss Law corpus. Using a fine-tuned BERT model, it identifies the type of reference made in a legal text, such as whether it amends, abrogates, cites, or introduces another legal provision.

## Project Structure

- **`BERTfunctions.py`**: Contains the core `BERTedgeReclassifier` class. This class handles:
    - Loading the fine-tuned BERT model (`dlicari/Italian-Legal-BERT`).
    - Tokenization and preprocessing of legal text.
    - Predicting the relationship label for a given text snippet.
- **`classify_edges.py`**: A processing pipeline for large-scale classification. It:
    - Iterates through JSON files containing legal document sections.
    - Identifies reference placeholders (e.g., `[FN_1]`).
    - Extracts context around these placeholders.
    - Enriches the context with metadata (like decision dates) from external databases (`complete_DB.csv`).
    - Uses `BERTedgeReclassifier` to classify each reference.
    - Saves the updated JSON files with the classified labels.
- **`example_classification.py`**: A demonstration script showing how to use the `BERTedgeReclassifier` for individual paragraphs.
- **`edge_labels.csv`**: A mapping file that defines the classification categories:
    - `0`: ABROGATES
    - `1`: AMENDS
    - `2`: CITES
    - `3`: INTRODUCES

## Input Requirements

To run the batch classification pipeline (`classify_edges.py`), the following inputs are required:

### 1. Source JSON Documents
A directory containing JSON files with the following structure:
```json
{
    "source_file": "document_name.pdf",
    "sections_list": [
        {
            "text": "The law [FN_1] is modified...",
            "fn_indexes": [1] 
        }
    ],
    "references_list": [
        {
            "fn_number": 1,
            "type": "RU",
            "text": "2023 123"
        }
    ]
}
```
- **`sections_list`**: Contains the text to be analyzed. Placeholders should follow the format `[FN_X]`.
- **`fn_indexes`**: A list of integers representing the footnotes in that section that require classification. After processing, this field will be converted into a dictionary mapping footnote numbers to their predicted relationship labels.
- **`references_list`**: Provides metadata for each footnote. The `type` (RS, RU, FF) and `text` are used to look up additional information.

### 2. Supporting Data Files
- **`RS_RU_mapping.json`**: A JSON file mapping Systematische Rechtssammlung (RS) numbers to their corresponding Record Unit (RU) labels.
- **`complete_DB.csv`**: A CSV database containing metadata for the referenced laws. It must include:
    - `ruLabel`: The identifier used for lookup.
    - `decisionDate`: The date the law was passed (used to enrich the BERT prompt).
- **`edge_labels.csv`**: Defines the target classes for the BERT model (AMENDS, ABROGATES, CITES, INTRODUCES).

### 3. Model Files
- **BERT Model**: A fine-tuned model file named `bert_edges` (saved via `torch.save`). The path is currently configured in `BERTfunctions.py`.
- **Tokenizer**: Uses `dlicari/Italian-Legal-BERT` from the Hugging Face Model Hub.

## Technical Details

- **Model**: The project utilizes `dlicari/Italian-Legal-BERT`, a BERT model specifically pre-trained on Italian legal documents, which has been further fine-tuned for this specific edge classification task.
- **Input Format**: The model expects a text paragraph. For better accuracy, `classify_edges.py` formats the input to include the decision date of the referenced law followed by the context text surrounding the reference.
- **Classification Categories**:
    - **AMENDS**: The source text modifies the target legal provision.
    - **ABROGATES**: The source text repeals or cancels the target legal provision.
    - **CITES**: The source text mentions or refers to the target legal provision without modifying it.
    - **INTRODUCES**: The source text introduces a new legal provision.

## Dependencies

- Python 3.x
- `torch`: For running the BERT model.
- `transformers`: For BERT tokenization and model handling.
- `pandas`: For data manipulation and loading CSV files.
- `numpy`: For numerical operations.

## Usage

### Simple Inference
You can use `example_classification.py` as a template to classify individual paragraphs:
```python
from BERTfunctions import BERTedgeReclassifier
import pandas as pd

labels = pd.read_csv("edge_labels.csv", sep=";")
model = BERTedgeReclassifier()

paragraph = "Your legal text here..."
label = model.textWithRef(paragraph, labels)
print(label)
```

### Batch Processing
To process a directory of JSON files, configure the paths in `classify_edges.py` and run:
```bash
python classify_edges.py
```
This script expects input JSONs to have a `sections_list` and `references_list` structure, with placeholders in the text matching the `fn_number` in the references.
