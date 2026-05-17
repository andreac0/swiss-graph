import json
import re
import os
import logging
from collections import namedtuple

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constants and Patterns ---

LANG_CONFIGS = {
    "it": {
        "HEADER_END_PATTERNS": [
            "www.droitfederal.admin.ch",
            "www.fedlex.admin.ch",
            "La versione elettronica",
            "signée fait foi"
        ],
        "PATTERNS_TO_IGNORE": ["Titre", "Chapitre", "Section"]
    },
    "fr": {
        "HEADER_END_PATTERNS": [
            "www.droitfederal.admin.ch",
            "www.fedlex.admin.ch",
            "La version électronique",
            "signée fait foi"
        ],
        "PATTERNS_TO_IGNORE": ["Titre", "Chapitre", "Section"]
    },
    "de": {
        "HEADER_END_PATTERNS": [
            "www.droitfederal.admin.ch",
            "www.fedlex.admin.ch",
            "Massgebend ist die signierte",
            "elektronische Fassung"
        ],
        "PATTERNS_TO_IGNORE": ["Titel", "Kapitel", "Abschnitt"]
    }
}

# Step 3 & 4: Marker patterns
ROMAN_NUMERAL_PATTERN = re.compile(r"^\s*(?P<marker>[IVX]+)\s*$")
ART_MARKER_PATTERN = re.compile(r"^\s*(?P<marker>(?:Art|Articolo)\.?\s*\d+[a-zA-Z]?)\b")
DIGIT_DOT_MARKER_PATTERN = re.compile(r"^\s*(?P<marker>\d+\.)(?=\s)(?P<title>.*\S.*|)\s*$")

# Step 4d: Reference patterns
BASE_REF_PATTERN = re.compile(r"^\s*(?P<text>\d{1,4})\s*$")
SYSTEMATIC_REF_PATTERN = re.compile(r"^\s*(?P<text>\d+\.\d+(?:[\.\d]*)?)\s*$")

# Simple Element Structure
Element = namedtuple("Element", ["id", "text", "font", "flags", "bbox", "is_bold", "page_num", "block_num", "line_num", "span_num"])

def is_bold_from_font(font_name):
    return font_name.endswith(('-BoldMT', '-Bold', 'bold', 'Bold'))

def parse_hierarchical_id(h_id):
    parts = {}
    try:
        components = h_id.split('.')
        for comp in components:
            key, value = comp.split('-', 1)
            parts[key] = int(value)
        return parts
    except Exception:
         logging.warning(f"Could not parse hierarchical ID: {h_id}")
         return {} 

def get_element_context(element):
     page = element.page_num
     block = element.block_num
     if page is None or block is None:
          parsed = parse_hierarchical_id(element.id)
          page = parsed.get('page')
          block = parsed.get('block')
     return page, block

def build_element_list(pages_data):
    element_list = []
    for page in pages_data:
        page_num = page.get("page_number") - 1
        for block_idx, block in enumerate(page.get("blocks", [])):
            for line_idx, line in enumerate(block.get("lines", [])):
                for span_idx, span in enumerate(line.get("spans", [])):
                    text = span.get("text", "").strip()
                    font = span.get("font", "")
                    is_bold = is_bold_from_font(font)
                    is_roman = bool(ROMAN_NUMERAL_PATTERN.match(text))
                    
                    if text and (is_bold or is_roman):
                         element_list.append(Element(
                              id=span.get("hierarchical_id"),
                              text=text,
                              font=font,
                              flags=span.get("flags"),
                              bbox=span.get("bbox"),
                              is_bold=is_bold,
                              page_num=page_num,
                              block_num=block_idx,
                              line_num=line_idx,
                              span_num=span_idx
                         ))
    return element_list

def filter_header_elements(element_list, header_patterns):
    cutoff_index = 0
    for i, element in enumerate(element_list):
        for pattern in header_patterns:
            if pattern in element.text:
                cutoff_index = i + 1
                break
    return element_list[cutoff_index:]

def extract_title_and_prepare_body(element_list, ignore_patterns):
    title_text_parts = []
    title_id = None
    title_marker_index = -1
    first_title_element_block_num = None
    first_title_element_page_num = None
    first_marker_index = -1

    if not element_list:
        return {"title_text": "", "title_id": None}, -1

    for i, element in enumerate(element_list):
        is_roman_marker = bool(ROMAN_NUMERAL_PATTERN.match(element.text))
        is_art_marker = bool(ART_MARKER_PATTERN.match(element.text)) and element.is_bold
        is_digit_dot_marker = bool(DIGIT_DOT_MARKER_PATTERN.match(element.text)) and element.is_bold
        is_to_ignore = any(pattern in element.text for pattern in ignore_patterns)
        
        is_marker = is_roman_marker or is_art_marker or is_digit_dot_marker

        if is_marker:
            first_marker_index = i
            break
        elif not is_to_ignore:
            current_element_page_num = element.page_num
            current_element_block_num = element.block_num

            if not title_text_parts:
                first_title_element_page_num = current_element_page_num
                first_title_element_block_num = current_element_block_num
                title_text_parts.append(element.text)
                title_id = element.id
            elif (current_element_page_num == first_title_element_page_num and
                  current_element_block_num == first_title_element_block_num):
                title_text_parts.append(element.text)
                title_id = element.id
                title_marker_index = i
            else:
                break

    doc_title_text_joined = " ".join(title_text_parts).strip()
    doc_title_text_joined = re.sub(r"^\W+|\W+$", "", doc_title_text_joined) 
    doc_title_text_joined = re.sub(r"\s+", " ", doc_title_text_joined)

    doc_title = {"title_text": doc_title_text_joined, "title_id": title_id}
    
    if first_marker_index == -1 and element_list:
        first_marker_index = title_marker_index + 1

    return doc_title, first_marker_index

def process_body_elements(element_list, start_index, ignore_patterns, filename):
    sections_list = []
    references_list = []
    
    if start_index == -1:
         return sections_list, references_list

    for i in range(start_index, len(element_list)):
        element = element_list[i]
        processed = False

        roman_match = ROMAN_NUMERAL_PATTERN.match(element.text)
        art_match = ART_MARKER_PATTERN.match(element.text)
        digit_dot_match = DIGIT_DOT_MARKER_PATTERN.match(element.text)

        if roman_match and not element.is_bold:
            marker_part = roman_match.group('marker')
            sections_list.append({'marker_id': element.id, 'marker': marker_part, 'title': ''})
            processed = True
        elif art_match and element.is_bold:
            marker_part = art_match.group('marker')
            sections_list.append({'marker_id': element.id, 'marker': marker_part, 'title': ''})
            processed = True
        elif digit_dot_match and element.is_bold:
            title_part = digit_dot_match.group('title').strip()
            marker_part = digit_dot_match.group('marker').strip()
            sections_list.append({'marker_id': element.id, 'marker': marker_part, 'title': title_part})
            processed = True
            
        if not processed:
            base_match = BASE_REF_PATTERN.match(element.text)
            systematic_match = SYSTEMATIC_REF_PATTERN.match(element.text)
            is_likely_systematic = '.' in element.text and element.text.replace('.', '').isdigit()

            if base_match and element.is_bold:
                references_list.append({
                    'id': element.id,
                    'kind': 'Base',
                    'text': base_match.group('text')
                })
                processed = True
            elif systematic_match and is_likely_systematic and element.is_bold:
                references_list.append({
                    'id': element.id,
                    'kind': 'Systematic',
                    'text': systematic_match.group('text')
                })
                processed = True

        if not processed and sections_list:
            for pattern in ignore_patterns:
                if pattern in element.text:
                    processed = True
                    break
            if not processed:
                last_section = sections_list[-1]
                last_marker_id = last_section['marker_id']
                
                current_page, current_block = get_element_context(element)
                parsed_marker_id = parse_hierarchical_id(last_marker_id)
                marker_page = parsed_marker_id.get('page')
                marker_block = parsed_marker_id.get('block')

                if current_page is not None and current_block is not None and \
                current_page == marker_page and current_block == marker_block:
                    title_separator = " " if last_section['title'] else ""
                    last_section['title'] += title_separator + element.text
                    processed = True

    for section in sections_list:
        section['title'] = section['title'].strip()
        
    return sections_list, references_list

def analyze_json_data(json_file_path, filename, lang="it"):
    config = LANG_CONFIGS.get(lang, LANG_CONFIGS["it"])
    header_patterns = config["HEADER_END_PATTERNS"]
    ignore_patterns = config["PATTERNS_TO_IGNORE"]

    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            pages_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON {json_file_path}: {e}")
        return None, None, None

    try:
        initial_elements = build_element_list(pages_data)
        if not initial_elements:
             return "", [], [] 

        filtered_elements = filter_header_elements(initial_elements, header_patterns)
        if not filtered_elements:
             return "", [], []

        doc_title, first_marker_idx = extract_title_and_prepare_body(filtered_elements, ignore_patterns)
        sections_list, references_list = process_body_elements(filtered_elements, first_marker_idx, ignore_patterns, filename)
        
        return doc_title, sections_list, references_list

    except Exception as e:
        logging.critical(f"CRITICAL ERROR during analysis of {os.path.basename(json_file_path)}: {e}", exc_info=True)
        return None, None, None

def start_analysis(input_dir, output_dir, lang="it"):
    if not os.path.isdir(input_dir):
        logging.error(f"Input directory not found: {input_dir}")
        return
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".json"):
            json_path = os.path.join(input_dir, filename)
            title, sections, references = analyze_json_data(json_path, filename, lang)

            if title is not None and isinstance(title, dict):
                output_data = {
                    "source_file": filename.replace(".json", ""),
                    "document_title": title.get("title_text"),
                    "title_id": title.get("title_id"),
                    "sections_list": sections,
                    "references_list": references
                }
                output_filepath = os.path.join(output_dir, filename)
                with open(output_filepath, 'w', encoding='utf-8') as f_out:
                    json.dump(output_data, f_out, ensure_ascii=False, indent=4)
