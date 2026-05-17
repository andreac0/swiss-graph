import dis
import os
import json

# Global flag to track preamble state across function calls
preamble_flag = False

def get_distinct_references(references_list, filter_unknown_type=False):
    """
    Extracts a set of distinct (type, text) tuples from a list of reference objects.
    """
    distinct_refs = set()
    if not references_list:
        return distinct_refs

    for ref in references_list:
        ref_type = ref.get("type")
        ref_text = ref.get("text")

        if ref_type and ref_text:  # Both type and text must be present
            # Normalize to string and strip whitespace
            ref_type_str = str(ref_type).strip()
            ref_text_str = str(ref_text).strip()

            if filter_unknown_type and ref_type_str.upper() == "UNKNOWN":
                continue
            
            # Ensure type and text are not empty after stripping
            if ref_type_str and ref_text_str:
                distinct_refs.add((ref_type_str, ref_text_str))
            
    return distinct_refs

def get_distinct_sections(sections_list, source_type="xml"):
    """
    Extracts a set of distinct section identifiers from a list of section objects.
    For XML: uses 'title' field
    For PDF: uses 'marker' field
    """
    global preamble_flag
    
    distinct_sections = set()
    if not sections_list:
        return distinct_sections

    field_name = "title" if source_type == "xml" else "marker"
    
    for section in sections_list:
        section_identifier = section.get(field_name)
        
        if section_identifier:
            # Normalize to string and strip whitespace
            section_id_str = str(section_identifier).strip()
            if source_type == "xml" and section_identifier == "Preamble":
                if section.get("text") == "":
                    continue

            
            # Ensure identifier is not empty after stripping
            if section_id_str:
                distinct_sections.add(section_id_str)
    
    if source_type == "xml":
        if distinct_sections == {"Preamble"}:
            preamble_flag = True
    if source_type == "pdf":
        if preamble_flag:
            if distinct_sections == {'Content'}:
                distinct_sections.add("Preamble")
            preamble_flag = False
            
            
    return distinct_sections

def compare_law_files(pdf_json_path, xml_json_path, output_file_obj):
    """
    Compares references and sections in a PDF-derived JSON file and an XML-derived JSON file.
    Returns a tuple (found_references_count, total_xml_references_count, found_sections_count, total_xml_sections_count).
    Writes debug info to console.
    """
    try:
        with open(pdf_json_path, 'r', encoding='utf-8') as f:
            pdf_data = json.load(f)
        with open(xml_json_path, 'r', encoding='utf-8') as f:
            xml_data = json.load(f)
    except FileNotFoundError:
        message = f"Error: One or both files not found: {pdf_json_path}, {xml_json_path}"
        print(message)
        output_file_obj.write(message + "\n")
        return 0, 0, 0, 0
    except json.JSONDecodeError as e:
        message = f"Error decoding JSON for {os.path.basename(pdf_json_path)} or {os.path.basename(xml_json_path)}: {e}"
        print(message)
        output_file_obj.write(message + "\n")
        return 0, 0, 0, 0
    except Exception as e:
        message = f"An unexpected error occurred while loading files {os.path.basename(pdf_json_path)} or {os.path.basename(xml_json_path)}: {e}"
        print(message)
        output_file_obj.write(message + "\n")
        return 0, 0, 0, 0

    # Compare references
    xml_references_list = xml_data.get("references_list", [])
    pdf_references_list = pdf_data.get("references_list", [])

    xml_distinct_refs = get_distinct_references(xml_references_list, filter_unknown_type=True)
    pdf_distinct_refs = get_distinct_references(pdf_references_list, filter_unknown_type=False)

    total_xml_refs_in_doc = len(xml_distinct_refs)
    found_refs_in_doc = 0

    if total_xml_refs_in_doc > 0:
        for xml_ref_tuple in xml_distinct_refs:
            if xml_ref_tuple in pdf_distinct_refs:
                found_refs_in_doc += 1

    # Compare sections
    xml_sections_list = xml_data.get("sections_list", [])
    pdf_sections_list = pdf_data.get("sections_list", [])

    xml_distinct_sections = get_distinct_sections(xml_sections_list, source_type="xml")
    pdf_distinct_sections = get_distinct_sections(pdf_sections_list, source_type="pdf")

    # total_xml_sections_in_doc = len(xml_distinct_sections)
    # found_sections_in_doc = 0

    # if total_xml_sections_in_doc > 0:
    #     for xml_section in xml_distinct_sections:
    #         if xml_section in pdf_distinct_sections:
    #             found_sections_in_doc += 1
    
    # return found_refs_in_doc, total_xml_refs_in_doc, found_sections_in_doc, total_xml_sections_in_doc
    return found_refs_in_doc, total_xml_refs_in_doc, len(pdf_distinct_sections), len(xml_distinct_sections)

def process_folder(pdf_json_base_folder, xml_json_base_folder, output_file_obj):
    """
    Processes a single folder of PDF JSONs and compares them against XML JSONs.
    Writes document-specific results to the output_file_obj.
    Returns counts for this folder: 
    (folder_total_xml_refs, folder_total_found_refs, folder_total_xml_sections, folder_total_found_sections, folder_files_contrib, folder_files_attempted)
    """
    folder_total_xml_references = 0
    folder_total_found_references = 0
    folder_total_xml_sections = 0
    folder_total_found_sections = 0
    folder_files_contributing_to_stats = 0 
    folder_files_attempted_processing = 0

    doc_specific_header = "Document-specific results:"
    print(doc_specific_header)
    output_file_obj.write(doc_specific_header + "\n")
    separator = "--------------------------"
    print(separator)
    output_file_obj.write(separator + "\n")

    if not os.path.isdir(pdf_json_base_folder):
        message = f"Error: PDF JSON folder not found: {pdf_json_base_folder}"
        print(message)
        output_file_obj.write(message + "\n")
        return 0, 0, 0, 0, 0, 0
    if not os.path.isdir(xml_json_base_folder):
        message = f"Error: XML JSON folder not found: {xml_json_base_folder}"
        print(message)
        output_file_obj.write(message + "\n")
        return 0, 0, 0, 0, 0, 0

    for filename in sorted(os.listdir(pdf_json_base_folder)):
        if not filename.endswith(".json"):
            continue
        
        if "Allegato" in filename:
            continue

        pdf_json_filepath = os.path.join(pdf_json_base_folder, filename)
        xml_json_filepath = os.path.join(xml_json_base_folder, filename)

        if not os.path.exists(xml_json_filepath):
            continue
        
        folder_files_attempted_processing += 1
        found_refs_count, xml_refs_count, found_sections_count, xml_sections_count = compare_law_files(pdf_json_filepath, xml_json_filepath, output_file_obj)

        if found_sections_count > xml_sections_count:
            found_sections_count = xml_sections_count

        if xml_refs_count > 0 or xml_sections_count > 0:
            folder_total_xml_references += xml_refs_count
            folder_total_found_references += found_refs_count
            folder_total_xml_sections += xml_sections_count
            folder_total_found_sections += found_sections_count
            folder_files_contributing_to_stats += 1
            
            # Calculate percentages
            ref_percentage = (found_refs_count / xml_refs_count) * 100 if xml_refs_count > 0 else 100.0
            section_percentage = (found_sections_count / xml_sections_count) * 100 if xml_sections_count > 0 else 0
            
            result_line = f"{filename}: References {found_refs_count}/{xml_refs_count} ({ref_percentage:.2f}%), Sections {found_sections_count}/{xml_sections_count} ({section_percentage:.2f}%)"
            print(result_line)
            output_file_obj.write(result_line + "\n")
        else:
            result_line = f"{filename}: References {found_refs_count}/{xml_refs_count}, Sections {found_sections_count}/{xml_sections_count} (N/A - No valid XML data to compare or error in processing)"
            print(result_line)
            output_file_obj.write(result_line + "\n")
            
    return (folder_total_xml_references, folder_total_found_references, 
            folder_total_xml_sections, folder_total_found_sections,
            folder_files_contributing_to_stats, folder_files_attempted_processing)

def main():
    pdf_json_root_folder = "./LawsDocs/processed/JSONs_split_with_fn_placeholders_in"
    xml_json_base_folder = "./LawsDocs/processed/XMLs/Final"
    output_filename = "comparison_accuracy_results.txt"

    grand_total_xml_references = 0
    grand_total_found_references = 0
    grand_total_xml_sections = 0
    grand_total_found_sections = 0
    grand_total_files_contributing = 0
    grand_total_files_attempted = 0

    with open(output_filename, 'w', encoding='utf-8') as output_file_obj:
        if not os.path.isdir(pdf_json_root_folder):
            message = f"Error: PDF JSON root folder not found: {pdf_json_root_folder}"
            print(message)
            output_file_obj.write(message + "\n")
            return
        
        for folder_name in sorted(os.listdir(pdf_json_root_folder)):
            current_pdf_folder_path = os.path.join(pdf_json_root_folder, folder_name)
            if os.path.isdir(current_pdf_folder_path):
                processing_message = f"\nProcessing folder: {folder_name}"
                #print(processing_message)
                output_file_obj.write(processing_message + "\n" + "="*len(processing_message) + "\n")
                
                (folder_xml_refs, folder_found_refs, folder_xml_sections, folder_found_sections,
                 folder_contrib, folder_attempted) = process_folder(current_pdf_folder_path, 
                                                                    xml_json_base_folder, 
                                                                    output_file_obj)
                grand_total_xml_references += folder_xml_refs
                grand_total_found_references += folder_found_refs
                grand_total_xml_sections += folder_xml_sections
                grand_total_found_sections += folder_found_sections
                grand_total_files_contributing += folder_contrib
                grand_total_files_attempted += folder_attempted
            else:
                skip_message = f"Skipping non-directory item: {folder_name}"
                print(skip_message)
                output_file_obj.write(skip_message + "\n")
                continue
        
        overall_header = "\nOverall results (across all processed folders):"
        separator = "----------------------------------------------"
        print(overall_header)
        output_file_obj.write(overall_header + "\n")
        print(separator)
        output_file_obj.write(separator + "\n")

        if grand_total_files_attempted == 0:
            message = "No files were found to process across all folders (after filtering 'Allegato' and checking for XML counterparts)."
            print(message)
            output_file_obj.write(message + "\n")
        elif grand_total_xml_references > 0 or grand_total_xml_sections > 0:
            # References statistics
            if grand_total_xml_references > 0:
                ref_overall_percentage = (grand_total_found_references / grand_total_xml_references) * 100
                
                ref_line1 = f"REFERENCES - Total distinct XML references considered from {grand_total_files_contributing} file(s): {grand_total_xml_references}"
                ref_line2 = f"REFERENCES - Total distinct XML references found in PDF versions: {grand_total_found_references}"
                ref_line3 = f"REFERENCES - Overall accuracy: {grand_total_found_references}/{grand_total_xml_references} ({ref_overall_percentage:.2f}%)"
                
                print(ref_line1)
                output_file_obj.write(ref_line1 + "\n")
                print(ref_line2)
                output_file_obj.write(ref_line2 + "\n")
                print(ref_line3)
                output_file_obj.write(ref_line3 + "\n")
            else:
                ref_message = "REFERENCES - No valid XML references were found to compare."
                print(ref_message)
                output_file_obj.write(ref_message + "\n")
            
            # Sections statistics
            if grand_total_xml_sections > 0:
                section_overall_percentage = (grand_total_found_sections / grand_total_xml_sections) * 100
                
                section_line1 = f"SECTIONS - Total distinct XML sections considered from {grand_total_files_contributing} file(s): {grand_total_xml_sections}"
                section_line2 = f"SECTIONS - Total distinct XML sections found in PDF versions: {grand_total_found_sections}"
                section_line3 = f"SECTIONS - Overall accuracy: {grand_total_found_sections}/{grand_total_xml_sections} ({section_overall_percentage:.2f}%)"
                
                print(section_line1)
                output_file_obj.write(section_line1 + "\n")
                print(section_line2)
                output_file_obj.write(section_line2 + "\n")
                print(section_line3)
                output_file_obj.write(section_line3 + "\n")
            else:
                section_message = "SECTIONS - No valid XML sections were found to compare."
                print(section_message)
                output_file_obj.write(section_message + "\n")
        else: # grand_total_files_attempted > 0 but both totals are 0
            message1 = f"Processed {grand_total_files_attempted} file(s) across all folders, but no valid XML references or sections were found to compare."
            message2 = f"Total distinct XML references considered: 0"
            message3 = f"Total distinct XML references found in PDF versions: 0"
            message4 = f"Total distinct XML sections considered: 0"
            message5 = f"Total distinct XML sections found in PDF versions: 0"
            message6 = f"Overall accuracy: 0/0 (N/A)"
            
            print(message1)
            output_file_obj.write(message1 + "\n")
            print(message2)
            output_file_obj.write(message2 + "\n")
            print(message3)
            output_file_obj.write(message3 + "\n")
            print(message4)
            output_file_obj.write(message4 + "\n")
            print(message5)
            output_file_obj.write(message5 + "\n")
            print(message6)
            output_file_obj.write(message6 + "\n")

    print(f"\nResults also saved to {output_filename}")

if __name__ == "__main__":
    main()