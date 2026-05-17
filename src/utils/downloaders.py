import os
import urllib.request
import pandas as pd
import fitz
import logging
from requests_html import HTMLSession

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SwissLawDownloader:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.df = pd.read_csv(csv_path)
        self.session = HTMLSession()

    def download_pdfs(self, output_base_dir="./LawsDocs/PDFs"):
        for index, row in self.df.iterrows():
            try:
                # This part depends on the CSV structure which seems to vary
                # I'll use a flexible approach or a mapping
                type_doc = row.get('typeDoc', 'General')
                pdf_url = row.get('fileUrl_it_pdf') or row.get('fileUrl')
                filename = row.get('itId') or row.get('ruLabel')
                
                if not pdf_url or pd.isna(pdf_url):
                    continue

                output_dir = os.path.join(output_base_dir, str(type_doc))
                os.makedirs(output_dir, exist_ok=True)
                
                pdf_path = os.path.join(output_dir, f"{filename}.pdf")
                urllib.request.urlretrieve(pdf_url, pdf_path)
                logging.info(f"Downloaded PDF: {filename}")
                
            except Exception as e:
                logging.error(f"Error downloading PDF at index {index}: {e}")

    def download_xmls(self, output_base_dir="./LawsDocs/XMLs"):
        for index, row in self.df.iterrows():
            try:
                type_doc = row.get('typeDoc', 'General')
                xml_url = row.get('fileUrl_it_xml')
                filename = row.get('ruLabel')
                
                if not xml_url or pd.isna(xml_url):
                    continue

                output_dir = os.path.join(output_base_dir, str(type_doc))
                os.makedirs(output_dir, exist_ok=True)
                
                xml_path = os.path.join(output_dir, f"{filename}.xml")
                urllib.request.urlretrieve(xml_url, xml_path)
                logging.info(f"Downloaded XML: {filename}")
                
            except Exception as e:
                logging.error(f"Error downloading XML at index {index}: {e}")

    def extract_text_from_pdfs(self, pdf_dir, txt_dir):
        for filename in os.listdir(pdf_dir):
            if filename.endswith(".pdf"):
                pdf_path = os.path.join(pdf_dir, filename)
                try:
                    doc = fitz.open(pdf_path)
                    text = "".join(page.get_text() for page in doc)
                    doc.close()
                    
                    os.makedirs(txt_dir, exist_ok=True)
                    txt_path = os.path.join(txt_dir, filename.replace(".pdf", ".txt"))
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    logging.info(f"Extracted text: {filename}")
                except Exception as e:
                    logging.error(f"Error extracting text from {filename}: {e}")

    def close(self):
        self.session.close()

if __name__ == "__main__":
    # Example usage
    # downloader = SwissLawDownloader("./raw_data/complete_DB.csv")
    # downloader.download_pdfs()
    # downloader.close()
    pass
