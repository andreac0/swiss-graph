import xml.etree.ElementTree as ET
import os
import json
import datetime
import re

try:
    # Requires: pip install beautifulsoup4 lxml
    from bs4 import BeautifulSoup, Tag, NavigableString
except ImportError:
    print("---")
    print("Warning: BeautifulSoup module not found.")
    print("Install with: pip install beautifulsoup4 lxml")
    print("Accurate Annex processing and text cleaning requires BeautifulSoup.")
    print("---")
    BeautifulSoup = None # Flag that BS4 is not available

# --- Helper Functions ---

def get_element_raw_text(element):
    """Get raw concatenated text from an element and its children."""
    if element is None:
        return ""
    # itertext() efficiently gets all text nodes, including children and tail text
    try:
        return "".join(element.itertext())
    except Exception as e:
        print(f"Warning: Error in itertext for element {getattr(element, 'tag', 'N/A')}: {e}")
        # Attempt fallback for common ET issue
        try:
            text_content = element.text or ""
            for child in element:
                text_content += get_element_raw_text(child) # Recursive call
                if child.tail:
                    text_content += child.tail
            return text_content
        except Exception as e2:
            print(f"  Fallback failed for element {getattr(element, 'tag', 'N/A')}: {e2}")
            return "" # Final fallback

def normalize_whitespace(text):
    """Replaces all whitespace runs with a single space and strips."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

# --- Metadata Extraction ---

def extract_law_metadata(root, ns):
    """Extracts law URL and decision date from the XML metadata."""
    metadata = {
        'law_url': None,
        'decision_date': None
    }
    if root is None:
        print("Error: Cannot extract metadata from None root.")
        return metadata

    try:
        # Namespace path helper
        def make_path(path_string):
            # Safely get namespace URI, handle potential KeyError
            ns_uri = ns.get('akn', '')
            if not ns_uri: # If no namespace defined, remove prefix attempt
                return path_string.replace('akn:', '')
            return path_string.replace('akn:', '{' + ns_uri + '}')

        # Find Identification block
        identification = root.find(make_path('.//akn:identification'))
        if identification is None:
            print("Warning: <identification> block not found in XML meta.")
            # Attempt search without namespace if identification fails
            identification = root.find('.//identification')
            if identification is None:
                print("  Also not found without namespace.")
                return metadata
            else:
                print("  Found <identification> without namespace.")
                # If found without namespace, assume no namespace for subsequent finds
                ns = {} # Clear namespace for subsequent searches within this function

        
        # Extract URL (Prefer FRBRWork/FRBRthis @value)
        work_uri_path = make_path('.//akn:FRBRWork/akn:FRBRuri')
        work_uri = identification.find(work_uri_path)
        if work_uri is not None and work_uri.get('value'):
            metadata['law_url'] = work_uri.get('value')
        else:
            # Fallback: Try FRBRExpression/FRBRuri @value
            work_this_path = make_path('.//akn:FRBRWork/akn:FRBRthis')
            work_this = identification.find(work_this_path)
            if work_this is not None and work_this.get('value'):
                metadata['law_url'] = work_this.get('value')
            else:
                 # Fallback: Try FRBRExpression/FRBRthis @value
                 expression_this_path = make_path('.//akn:FRBRExpression/akn:FRBRthis')
                 expression_this = identification.find(expression_this_path)
                 if expression_this is not None and expression_this.get('value'):
                    metadata['law_url'] = expression_this.get('value')
                 else:
                     print(f"Warning: Law URL not found in expected locations ({expression_this_path}, etc.).")


        # Extract Decision Date
        date_path = make_path(".//akn:FRBRWork/akn:FRBRdate[@name='jolux:dateDocument']")
        work_date = identification.find(date_path)
        if work_date is not None and work_date.get('date'):
            metadata['decision_date'] = work_date.get('date')
        else:
             print(f"Warning: Decision date not found at {date_path}.")
             # Fallback: Try finding any date with name containing 'dateDocument'
             all_dates = identification.findall(make_path(".//akn:FRBRWork/akn:FRBRdate"))
             found_date = False
             for dt in all_dates:
                  if dt.get('name') and 'dateDocument' in dt.get('name') and dt.get('date'):
                       metadata['decision_date'] = dt.get('date')
                       print(f"  Found date using fallback search: {dt.get('name')}")
                       found_date = True
                       break
             if not found_date:
                   print("  Decision date fallback search also failed.")


    except Exception as e:
        print(f"Error extracting metadata: {e}")
        import traceback
        traceback.print_exc()


    return metadata

# --- Href Extraction and Validation ---

def extract_hrefs_from_authorial_notes(element, ns):
    """Extract all hrefs from authorialNote elements using ElementTree."""
    hrefs = []
    # Define paths with namespace placeholder
    authorial_notes_xpath = ".//akn:authorialNote"
    ref_xpath = ".//akn:ref[@href]"

    # Replace placeholder with actual namespace URI for ET findall
    try:
        ns_uri = ns.get('akn', '') # Use .get for safety
        if not ns_uri:
            print("Warning: Namespace 'akn' not found in ns map for href extraction.")
            authorial_notes_xpath_ns = authorial_notes_xpath.replace('akn:', '') # Try without ns
            ref_xpath_ns = ref_xpath.replace('akn:', '')
        else:
            authorial_notes_xpath_ns = authorial_notes_xpath.replace('akn:', '{' + ns_uri + '}')
            ref_xpath_ns = ref_xpath.replace('akn:', '{' + ns_uri + '}')
    except Exception as e:
        print(f"Error preparing namespace paths for href extraction: {e}")
        return []


    try:
        notes = element.findall(authorial_notes_xpath_ns)
    except Exception as e:
        print(f"Warning: Failed to find authorialNote elements with path '{authorial_notes_xpath_ns}'. Error: {e}")
        notes = []

    for note in notes:
        try:
            refs = note.findall(ref_xpath_ns)
        except Exception:
             refs = []

        for ref in refs:
            href = ref.get("href")
            if href:
                # Get the raw text content of the ref tag itself
                ref_text = get_element_raw_text(ref)
                hrefs.append({
                    'href': href,
                    'text': normalize_whitespace(ref_text) # Clean ref text here too
                })

    return hrefs # Returns list of dicts in order of appearance

def validate_hrefs_in_content(hrefs, xml_content_string):
    """
    Validate that extracted hrefs are present as href attributes
    within the provided XML content string. Returns only the valid href dicts,
    preserving the relative order of matched hrefs.

    Args:
        hrefs (list): List of dictionaries {'href': URL, 'text': TEXT}.
        xml_content_string (str): The XML content string of the section (potentially trimmed).

    Returns:
        list: List of href dictionaries that were found as attributes in the content string.
    """
    matched_hrefs = []
    if not xml_content_string: # Skip if content is empty
        return []

    for href_info in hrefs: # Iterates in original order
        href_url = href_info.get('href')
        if not href_url: continue

        try:
            escaped_url = re.escape(href_url)
        except TypeError:
             print(f"Warning: Invalid type for href URL: {href_url}. Skipping validation.")
             continue

        pattern_double_quote = rf'\bhref\s*=\s*"{escaped_url}"'
        pattern_single_quote = rf"\bhref\s*=\s*'{escaped_url}'"

        try:
            # Use re.search for potentially better performance on large strings
            if re.search(pattern_double_quote, xml_content_string, re.IGNORECASE) or \
               re.search(pattern_single_quote, xml_content_string, re.IGNORECASE): # Added IGNORECASE
                matched_hrefs.append(href_info)
            # else: # Optional: Log missing hrefs for debugging
            #     print(f"Debug: Href '{href_url}' not found in content for validation.")
        except re.error as e:
            print(f"Warning: Regex error checking href '{href_url}'. Skipping. Error: {e}")
            continue
        except Exception as e:
             print(f"Warning: Unexpected error validating href '{href_url}'. Skipping. Error: {e}")
             continue

    return matched_hrefs # Preserves relative order of matches

# --- Content Scoping and Cleaning ---

def get_direct_xml_content(element, ns):
    """Extract XML content string without nested levels, using ElementTree."""
    try:
        element_copy = ET.fromstring(ET.tostring(element, encoding='unicode'))
    except Exception as e:
        print(f"Error copying element {getattr(element, 'tag', 'N/A')} for get_direct_xml_content: {e}")
        return ""

    nested_levels_xpath = ".//akn:level"
    try:
        ns_uri = ns.get('akn', '')
        if not ns_uri:
            nested_levels_xpath_ns = nested_levels_xpath.replace('akn:', '')
        else:
            nested_levels_xpath_ns = nested_levels_xpath.replace('akn:', '{' + ns_uri + '}')
    except Exception as e:
        print(f"Error preparing namespace path for level removal: {e}")
        nested_levels_xpath_ns = nested_levels_xpath.replace('akn:', '') # Fallback


    try:
        all_nested_levels = element_copy.findall(nested_levels_xpath_ns)
    except Exception as e:
        print(f"Warning: Failed to find nested levels with path '{nested_levels_xpath_ns}'. Error: {e}")
        all_nested_levels = []


    if all_nested_levels:
         try:
             parent_map = {c: p for p in element_copy.iter() for c in p}
         except Exception as e:
             print(f"Warning: Could not build parent map in get_direct_xml_content. Error: {e}")
             parent_map = {}

         for level_to_remove in all_nested_levels:
            parent = parent_map.get(level_to_remove)
            if parent is not None:
                try:
                    parent.remove(level_to_remove)
                except ValueError:
                     pass # Already removed

    try:
        return ET.tostring(element_copy, encoding='unicode')
    except Exception as e:
        print(f"Error converting modified element back to string: {e}")
        return ""

def clean_xml_text(xml_text_string):
    """
    Clean XML text using BeautifulSoup to preserve structure like paragraphs
    and lists with appropriate newlines.

    Args:
        xml_text_string (str): XML string fragment to process.

    Returns:
        str: Cleaned text with structural formatting.
    """
    if not xml_text_string:
        return ""

    if not BeautifulSoup:
        print("Warning: BeautifulSoup not available. Using basic text cleaning.")
        try:
            text = re.sub(r'<[^>]+>', ' ', xml_text_string)
            text = normalize_whitespace(text) # Use helper
            text = re.sub(r'\n\s*\n', '\n\n', text)
            return text
        except Exception as e:
            print(f"Error during basic text cleaning: {e}")
            return ""

    try:
        soup = BeautifulSoup(xml_text_string, 'xml')
        output = []

        # --- Recursive function to traverse and format ---
        def process_element(element):
            nonlocal output
            if not isinstance(element, Tag):
                 if isinstance(element, NavigableString):
                     cleaned_text = normalize_whitespace(element.string) # Use helper
                     if cleaned_text:
                         if output and not output[-1].endswith(('\n', ' ')):
                             output.append(" ")
                         output.append(cleaned_text)
                 return

            tag_name = element.name.lower()

            # --- Block-level elements ---
            block_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                          'title', 'chapter', 'part', 'book', 'article', 'section', 'subsection',
                          'level', 'doc', 'mainbody', 'component', 'preface', 'preamble',
                          'body', 'components', 'conclusions', 'attachment', 'annex',
                          'listintroduction', 'blocklist', 'item', 'paragraph', 'heading', 'subheading',
                          'content', 'num'] # Treat num as block

            if tag_name in block_tags:
                needs_leading_newline = output and not output[-1].endswith('\n')
                needs_paragraph_spacing = output and output[-1].endswith('\n') and not output[-1].endswith('\n\n')

                # --- Spacing BEFORE block ---
                major_breaks = ['level', 'article', 'chapter', 'part', 'book', 'annex', 'doc', 'component', 'h1', 'h2', 'h3']
                if tag_name in major_breaks:
                     if output and not output[-1].endswith('\n\n'): output.append("\n\n")
                     elif needs_paragraph_spacing: output.append("\n")
                elif tag_name in ['listintroduction', 'item', 'blocklist']:
                     if needs_leading_newline: output.append("\n")
                elif tag_name in ['p', 'h4', 'h5', 'h6', 'heading', 'subheading', 'paragraph', 'num', 'content']:
                    if needs_leading_newline: output.append("\n\n")
                    elif needs_paragraph_spacing: output.append("\n")

                # --- Process Children ---
                for content in element.contents:
                    process_child(content)

                # --- Spacing AFTER block ---
                double_newline_after = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'level', 'article',
                                        'paragraph', 'heading', 'subheading', 'blocklist', 'item', 'num', 'content']
                if tag_name in double_newline_after:
                     if output and not output[-1].endswith('\n\n'):
                         if output[-1].endswith('\n'): output.append("\n")
                         else: output.append("\n\n")
                     # Add newline even if output is empty (e.g. single paragraph document)
                     elif not output: output.append("\n\n")
                elif tag_name == 'listintroduction':
                     if output and not output[-1].endswith('\n'): output.append("\n")

            elif tag_name == 'authorialnote': pass # Skip
            elif tag_name == 'br':
                 if output and not output[-1].endswith('\n'): output.append("\n")
            else: # --- Inline elements ---
                 for content in element.contents:
                     process_child(content)

        # --- Helper to process child nodes ---
        def process_child(content):
             nonlocal output
             if isinstance(content, NavigableString):
                cleaned_text = normalize_whitespace(content.string) # Use helper
                if cleaned_text:
                    if output and not output[-1].endswith(('\n', ' ')) : output.append(" ")
                    output.append(cleaned_text)
             elif isinstance(content, Tag):
                  process_element(content) # Recurse

        # --- Start processing ---
        # Find the main content if possible, otherwise process everything
        body_content = soup.find(['mainBody', 'conclusions', 'body', 'doc'])
        start_node = body_content if body_content else soup

        for element in start_node.contents:
             process_element(element)

        full_text = "".join(output)

        # --- Final cleanup ---
        full_text = re.sub(r'[ \t]+\n', '\n', full_text) # Space before newline
        full_text = re.sub(r'\n{3,}', '\n\n', full_text) # Max 2 consecutive newlines

        return full_text.strip()

    except Exception as e:
        print(f"Error cleaning XML with BeautifulSoup: {e}")
        import traceback
        traceback.print_exc()
        # Basic fallback
        try:
            text = re.sub(r'<[^>]+>', ' ', xml_text_string)
            text = normalize_whitespace(text) # Use helper
            text = re.sub(r'\n\s*\n', '\n\n', text)
            return text
        except Exception as e2:
             print(f"Error during basic fallback text cleaning: {e2}")
             return ""


# --- Main Section Processing Logic ---

def process_xml_sections(root, ns):
    """
    Processes XML root to extract sections (annexes and levels)
    with cleaned text and validated, ordered references.
    """
    if not BeautifulSoup:
         raise ImportError("BeautifulSoup is required for accurate processing.")

    processed_sections = []

    # Helper function for ET findall
    def findall_et_ns(element, path):
        try:
            ns_uri = ns.get('akn', '')
            if not ns_uri: path_ns = path.replace('akn:', '')
            else: path_ns = path.replace('akn:', '{' + ns_uri + '}')
            return element.findall(path_ns)
        except Exception as e:
             print(f"Warning: ElementTree findall failed for path '{path}'. Error: {e}")
             return []


    # --- Process Annexes ---
    annex_docs = findall_et_ns(root, ".//akn:component/akn:doc[@name='annex']")
    if not annex_docs: annex_docs = findall_et_ns(root, ".//akn:doc[@name='annex']")
    print(f"Debug: Found {len(annex_docs)} annex doc(s).")

    for i, annex_element in enumerate(annex_docs):
        annex_id = f"annex_{i+1}"
        print(f"Processing {annex_id}...")

        # --- Get Title ---
        raw_title = f"Allegato {i+1}" # Default title

        # 1. Look for <h1> specifically within preface or direct children
        title_h1 = None
        preface_h1_list = findall_et_ns(annex_element, "./akn:preface//akn:h1") # h1 inside preface
        if preface_h1_list:
            title_h1 = preface_h1_list[0]
        else:
             # Fallback: Look for direct child h1 (less common in Akoma Ntoso annexes)
             direct_h1_list = findall_et_ns(annex_element, "./akn:h1")
             if direct_h1_list:
                  title_h1 = direct_h1_list[0]

        if title_h1 is not None:
            raw_title = get_element_raw_text(title_h1)
            print(f"  Debug: Found title in h1: '{normalize_whitespace(raw_title)}'")
        else:
            # 2. If no h1, look for <num> inside standard preface header structure
            # Path: ./preface/container[@name='headerOfAnnex']/block[@name='num']/num
            # Simplification: Look for num inside preface/container or just preface
            specific_num = None
            preface_cont_num_list = findall_et_ns(annex_element, "./akn:preface/akn:container/akn:block[@name='num']/akn:num")
            if preface_cont_num_list:
                specific_num = preface_cont_num_list[0]
            else:
                 # Fallback: Look for num anywhere under preface
                 preface_num_list = findall_et_ns(annex_element, "./akn:preface//akn:num")
                 if preface_num_list:
                     specific_num = preface_num_list[0] # Use the first one found in preface

            if specific_num is not None:
                raw_title = get_element_raw_text(specific_num)
                print(f"  Debug: Found title in specific preface num: '{normalize_whitespace(raw_title)}'")
            # Removed the broad .//akn:num search and heuristic as it was causing issues

        cleaned_title = normalize_whitespace(raw_title) # Clean the title *after* finding the best source

        # --- Scope Content (Trim) ---
        try: annex_full_xml_str = ET.tostring(annex_element, encoding='unicode')
        except Exception as e:
            print(f"Error converting Annex {annex_id} element to string: {e}"); continue
        xml_content_scoped = annex_full_xml_str

        try:
            soup = BeautifulSoup(annex_full_xml_str, 'xml')
            container_candidates = ['mainBody', 'conclusions', 'body', 'doc']
            main_container = None
            for tag_name in container_candidates:
                 container = soup.find(tag_name, recursive=False)
                 if not container: container = soup.find(tag_name)
                 if container: main_container = container; break
            if not main_container: main_container = soup

            # Find first 'level' or 'component' direct child to mark end of annex content
            first_terminator = main_container.find(['level', 'component'], recursive=False)

            if first_terminator:
                print(f"Debug: Trimming Annex {annex_id} content before tag '{first_terminator.name}'.")
                elements_to_remove = [first_terminator] + list(first_terminator.find_next_siblings())
                parent_of_terminator = first_terminator.parent
                for elem in elements_to_remove:
                    if elem.parent == parent_of_terminator: elem.decompose()
                xml_content_scoped = str(main_container)
            else:
                 xml_content_scoped = str(main_container)

        except Exception as e:
            print(f"Error during Annex {annex_id} scoping/trimming: {e}")
            xml_content_scoped = annex_full_xml_str


        # --- Hrefs ---
        href_dicts = extract_hrefs_from_authorial_notes(annex_element, ns)
        matched_href_dicts = validate_hrefs_in_content(href_dicts, xml_content_scoped)

        # --- Clean Text ---
        cleaned_text = clean_xml_text(xml_content_scoped)

        # --- Format Ordered Unique References ---
        references_list = []
        seen_hrefs = set()
        for h_info in matched_href_dicts: # Iterate in order of validation
            href_url = h_info.get('href')
            if href_url and href_url not in seen_hrefs:
                references_list.append(href_url)
                seen_hrefs.add(href_url)

        processed_sections.append({
            'id': annex_id, # Simple ID for annex
            'title': cleaned_title, # Use cleaned title
            'text': cleaned_text,
            'references': references_list # Use ordered unique list
        })


    # --- Process Levels ---
    all_levels = findall_et_ns(root, ".//akn:level[@eId]")
    print(f"Debug: Found {len(all_levels)} level element(s).")

    for level_element in all_levels:
        level_id = level_element.get("eId")
        if not level_id: print("Warning: Skipping level without eId."); continue
        print(f"Processing level {level_id}...")

        # --- Get Title ---
        raw_title = f"Level {level_id}" # Default
        num_elem_list = findall_et_ns(level_element, "./akn:num") # Direct child num
        if num_elem_list and num_elem_list[0] is not None:
             raw_title = get_element_raw_text(num_elem_list[0])

        # Fallback title logic if num is empty or default
        if not raw_title or raw_title.isspace() or raw_title == f"Level {level_id}":
             heading_elem_list = findall_et_ns(level_element, "./akn:heading") # Direct child heading
             if heading_elem_list and heading_elem_list[0] is not None:
                  raw_title = get_element_raw_text(heading_elem_list[0])
             # If still no title, keep the default "Level {level_id}"

        cleaned_title = normalize_whitespace(raw_title) # Clean the title

        # --- Scope Content ---
        xml_content_scoped = get_direct_xml_content(level_element, ns)

        # --- Hrefs ---
        href_dicts = extract_hrefs_from_authorial_notes(level_element, ns)
        matched_href_dicts = validate_hrefs_in_content(href_dicts, xml_content_scoped)

        # --- Clean Text ---
        cleaned_text = clean_xml_text(xml_content_scoped)

        # --- Format Ordered Unique References ---
        references_list = []
        seen_hrefs = set()
        for h_info in matched_href_dicts: # Iterate in order of validation
            href_url = h_info.get('href')
            if href_url and href_url not in seen_hrefs:
                references_list.append(href_url)
                seen_hrefs.add(href_url)

        processed_sections.append({
            'id': level_id, # Use eId for levels
            'title': cleaned_title, # Use cleaned title
            'text': cleaned_text,
            'references': references_list # Use ordered unique list
        })

    # Sort sections (Annexes first, then Levels by ID)
    processed_sections.sort(key=lambda x: (0 if x['id'].startswith('annex_') else 1, x['id']))

    return processed_sections

# --- Main Processing Function ---

def process_xml_file(xml_input_path):
    """
    Processes a single XML file to extract metadata and section data.

    Args:
        xml_input_path (str): Path to the input XML file.

    Returns:
        dict: A dictionary containing 'law_url', 'decision_date', and 'sections',
              or None if processing fails.
    """
    if not BeautifulSoup:
        print("ERROR: BeautifulSoup library is required but not installed.")
        return None

    print(f"\n--- Processing file: {xml_input_path} ---")

    # Parse XML
    try:
        tree = ET.parse(xml_input_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"  Error parsing XML file: {e}")
        return None
    except FileNotFoundError:
         print(f"  Error: XML file not found at {xml_input_path}")
         return None
    except Exception as e:
         print(f"  Unexpected error parsing XML: {e}")
         return None

    # Determine Namespace
    ns_uri = None
    if root is not None and '}' in root.tag: ns_uri = root.tag.split('}')[0][1:]
    if not ns_uri: ns_uri = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0" # Default fallback
    ns = {'akn': ns_uri}
    print(f"  Using namespace: {ns_uri}")

    # Extract Law Metadata
    print("  Extracting law metadata...")
    law_metadata = extract_law_metadata(root, ns)
    print(f"  Metadata extracted: URL='{law_metadata.get('law_url')}', Date='{law_metadata.get('decision_date')}'")

    # Process Sections (Annexes and Levels)
    print("  Processing sections...")
    try:
        sections_data = process_xml_sections(root, ns)
        print(f"  Processed {len(sections_data)} sections.")
    except Exception as e:
        print(f"\n  --- ERROR during section processing for {os.path.basename(xml_input_path)} ---")
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        print("  --- Section processing stopped due to error ---")
        return None # Indicate failure

    # Assemble Final Data Structure
    final_data = {
        "law_url": law_metadata.get('law_url'),
        "decision_date": law_metadata.get('decision_date'),
        "sections": sections_data
    }

    print(f"--- Successfully processed {os.path.basename(xml_input_path)} ---")
    return final_data


# --- Standalone Execution / Testing (Optional) ---

if __name__ == "__main__":
    print("Running xml_processor.py as standalone script for testing...")

    # --- Configuration for Testing ---
    test_xml_file = "./LawsDocs/for_processing/XMLs/it/Legge federale/RU 2022 352.xml" # Example file
    test_output_dir = "./scripts/PDF_articles" # Test output dir
    # --- End Configuration ---

    if not os.path.exists(test_xml_file):
        print(f"Test Error: XML file not found at {test_xml_file}")
    else:
        # Process the file
        processed_data = process_xml_file(test_xml_file)

        # Save the output if successful
        if processed_data:
            os.makedirs(test_output_dir, exist_ok=True)
            base_filename = os.path.splitext(os.path.basename(test_xml_file))[0]
            output_json_file = os.path.join(test_output_dir, f"{base_filename}_TEST.json")

            try:
                with open(output_json_file, 'w', encoding='utf-8') as f:
                    json.dump(processed_data, f, ensure_ascii=False, indent=2)
                print(f"\nTest output saved successfully to: {output_json_file}")
            except Exception as e:
                print(f"\nError saving test output JSON: {e}")
        else:
            print("\nProcessing failed, no test output generated.")

# --- END OF FILE xml_processor.py ---