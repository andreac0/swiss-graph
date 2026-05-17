# BERT Department Model: Italian Legal Document Classification

This repository contains notebooks for fine-tuning and using a BERT-based model for multi-label classification of Italian legal documents (laws) into various ministerial domains.

## Overview

The goal of this project is to automatically categorize Italian law titles into one or more of 16 predefined domains. This is implemented as a multi-label classification task using a specialized BERT model pre-trained on Italian legal text.

## Model

The project uses **[Italian-Legal-BERT](https://huggingface.co/dlicari/Italian-Legal-BERT)** (`dlicari/Italian-Legal-BERT`), which is a BERT model specifically trained on Italian legal documents to better capture the nuances of legal terminology.

## Dataset

- **Source**: `ft_train_encoded.csv`
- **Size**: 71,823 samples
- **Input**: Law titles (`TitleLaw`)
- **Output**: Multi-label domains (`label`)
- **Split**: 80% Training (57,458 samples), 20% Validation (14,365 samples)

### Classification Domains (16)
- agricoltura
- comunicazioni
- cultura,ambiente
- difesa
- economia
- esteri
- giustizia
- interno
- istituzioni
- istruzione
- lavoro
- presidenza
- pubblica amministrazione
- sanita
- spettacolo,sport,turismo
- trasporti

## Training Configuration

- **Maximum Sequence Length**: 449 (up to 512)
- **Batch Size**: 32
- **Optimizer**: AdamW
- **Learning Rate**: 2e-5
- **Epochs**: 4
- **Hardware**: Trained on Google Colab using GPU (CUDA)

## Results

The model achieved steady improvement across 4 epochs:

| Epoch | Avg Training Loss | F1 Micro | F1 Macro |
|-------|-------------------|----------|----------|
| 1     | 0.16              | 0.7945   | 0.6625   |
| 2     | 0.11              | 0.8116   | 0.7076   |
| 3     | 0.10              | 0.8220   | 0.7272   |
| 4     | 0.09              | **0.8255** | **0.7338** |

- **Total Training Time**: 3:55:35

## Files in this Repository

- `fine-tuning.ipynb`: The main notebook containing the data preprocessing, training loop, and evaluation.
- `inference.ipynb`: Notebook for running predictions using the fine-tuned model.

## Getting Started

### Installation

To install the required dependencies, run:

```bash
pip install transformers torch pandas scikit-learn numpy
```

### Data Setup

Place your training data in a `data` folder at the root of the repository:

```text
BERT-Department-Model/
├── data/
│   └── ft_train_encoded.csv
├── fine-tuning.ipynb
├── inference.ipynb
└── README.md
```

## Usage

1. **Fine-tuning**: Run `fine-tuning.ipynb` to train the model. 
   - The notebook expects the dataset at `./data/ft_train_encoded.csv`.
   - After training, the fine-tuned model and label encoder will be saved to the `./saved_model` directory.
2. **Inference**: Use `inference.ipynb` to perform predictions.
   - It automatically loads the model and tokenizer from `./saved_model`.
   - It uses the `label_encoder.pkl` to decode predicted indices into ministerial domain names.
