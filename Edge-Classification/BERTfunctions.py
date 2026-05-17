import numpy as np
import torch
from transformers import BertTokenizer
import pandas as pd

labels = pd.read_csv("./ClassifyEdges/edge_labels.csv", sep=";")

class BERTedgeReclassifier:

    def __init__(self):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.tokenizer = BertTokenizer.from_pretrained('dlicari/Italian-Legal-BERT', do_lower_case=True, clean_up_tokenization_spaces = True)
        if torch.cuda.is_available():
            self.model = torch.load('./ClassifyEdges/bert_edges', weights_only=False)
        else:
            self.model = torch.load('./ClassifyEdges/bert_edges', map_location=torch.device('cpu'))
    
    def textWithRef(self, text, labels):
        
            encoded_dict = self.tokenizer.encode_plus(
                                text,
                                add_special_tokens = True,
                                max_length = 512,
                                truncation=True,
                                padding='max_length',
                                return_attention_mask = True,
                                return_tensors = 'pt',
                            )
            test_input_ids = torch.cat([encoded_dict['input_ids']], dim=0)
            test_attention_masks = torch.cat([encoded_dict['attention_mask']], dim=0)

            b_input_ids = test_input_ids.to(self.device)
            b_input_mask = test_attention_masks.to(self.device)
            

            with torch.no_grad():
                output= self.model(b_input_ids,
                                        token_type_ids=None,
                                        attention_mask=b_input_mask)
                logits = output.logits
                logits = logits.detach().cpu().numpy()
                pred_flat = np.argmax(logits, axis=1).flatten()[0]
            
            return labels[labels['label'] == pred_flat]['RefType'].iloc[0]
    
    def predict_label(self, text):
         
            encoded_dict = self.tokenizer.encode_plus(
                                text,
                                add_special_tokens = True,
                                max_length = 512,
                                truncation=True,
                                padding='max_length',
                                return_attention_mask = True,
                                return_tensors = 'pt',
                            )
            test_input_ids = torch.cat([encoded_dict['input_ids']], dim=0)
            test_attention_masks = torch.cat([encoded_dict['attention_mask']], dim=0)

            b_input_ids = test_input_ids.to(self.device)
            b_input_mask = test_attention_masks.to(self.device)
            

            with torch.no_grad():
                output= self.model(b_input_ids,
                                        token_type_ids=None,
                                        attention_mask=b_input_mask)
                logits = output.logits
                logits = logits.detach().cpu().numpy()
                pred_flat = np.argmax(logits, axis=1).flatten()[0]
            
            return labels[labels['label'] == pred_flat]['RefType'].iloc[0]
        