import requests
import json
import csv
import io # To read the CSV string directly if needed
import time # To add delays between requests
from datetime import datetime

# --- Configuration ---
SPARQL_ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
ELASTICSEARCH_ENDPOINT = "https://www.fedlex.admin.ch/elasticsearch/proxy/_search"
HEADERS_SPARQL = {'Accept': 'application/sparql-results+json'}
HEADERS_ES = {'Content-Type': 'application/json', 'Accept': 'application/json'}
CSV_FILE_PATH = './raw_data/RS_list.csv' # Path to your input CSV file
OUTPUT_JSON_PATH = './raw_data/RS_history_output.json' # Path for the output JSON file
REQUEST_DELAY = 1 # Seconds to wait between processing each RS number

# --- Helper Functions (Mostly unchanged from previous version) ---

def run_sparql_query(query):
    """Sends a SPARQL query and returns the parsed JSON response."""
    try:
        # Increased timeout for potentially complex queries
        response = requests.post(SPARQL_ENDPOINT, data={'query': query}, headers=HEADERS_SPARQL, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"SPARQL request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response status: {e.response.status_code}")
             print(f"Response text: {e.response.text[:500]}...")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to decode SPARQL JSON response: {e}")
        # Check if response object exists before accessing .text
        if 'response' in locals() and response is not None:
            print(f"Response text: {response.text[:500]}...")
        return None

def run_elasticsearch_query(payload):
    """Sends a query payload to Elasticsearch and returns the parsed JSON response."""
    try:
        # Increased timeout
        response = requests.post(f"{ELASTICSEARCH_ENDPOINT}?index=data", json=payload, headers=HEADERS_ES, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Elasticsearch request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response status: {e.response.status_code}")
             print(f"Response text: {e.response.text[:500]}...")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to decode Elasticsearch JSON response: {e}")
         # Check if response object exists before accessing .text
        if 'response' in locals() and response is not None:
            print(f"Response text: {response.text[:500]}...")
        return None

def get_rs_info_from_number(rs_number):
    """Gets the RS URI (ConsolidationAbstract) and Taxonomy URI for a given RS number."""
    print(f"Fetching RS Info for {rs_number}...")
    query = f"""
        PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

        SELECT DISTINCT ?rsURI ?taxonomyConcept
        WHERE {{
          # Find the concept first via notation
          ?taxonomyConcept skos:notation "{rs_number}"^^<https://fedlex.data.admin.ch/vocabulary/notation-type/id-systematique> .
          # Then find the RS URI linked to it
          ?rsURI jolux:classifiedByTaxonomyEntry ?taxonomyConcept .
          ?rsURI rdf:type jolux:ConsolidationAbstract .
        }}
        LIMIT 1
    """
    result = run_sparql_query(query)
    if result and result['results']['bindings']:
        binding = result['results']['bindings'][0]
        rs_uri = binding.get('rsURI', {}).get('value')
        tax_uri = binding.get('taxonomyConcept', {}).get('value')
        print(f"  Found RS URI: {rs_uri}")
        print(f"  Found Taxonomy URI: {tax_uri}")
        if rs_uri and tax_uri:
            return {'rs_uri': rs_uri, 'taxonomy_uri': tax_uri}
    print(f"  Could not find complete info for RS {rs_number} via SPARQL.")
    return None # Return None if info is incomplete

def get_base_act_and_entry_info(rs_uri):
    """Gets Base Act URI, its Entry into Force date and Italian Memorial Label."""
    if not rs_uri:
        print("  Cannot fetch Base Act info without RS URI.")
        return None
    print(f"  Fetching Base Act info for RS URI {rs_uri}...")
    query = f"""
        PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
        PREFIX eli: <http://data.europa.eu/eli/ontology#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

        SELECT ?baseActURI ?eventDate ?sourceMemorialLabel
        WHERE {{
            <{rs_uri}> jolux:basicAct ?baseActURI .

            OPTIONAL {{ ?baseActURI jolux:dateEntryInForce ?date1 . }}
            OPTIONAL {{ ?baseActURI jolux:publicationDate ?date2 . }}
            BIND(COALESCE(?date1, ?date2) AS ?eventDate)

            OPTIONAL {{
                ?baseActURI jolux:isRealizedBy ?expression .
                ?expression jolux:language <http://publications.europa.eu/resource/authority/language/ITA> .
                ?expression jolux:historicalLegalId ?sourceMemorialLabel .
            }}
            FILTER(BOUND(?baseActURI)) # We need at least the baseActURI
        }}
        LIMIT 1
    """
    result = run_sparql_query(query)
    if result and result['results']['bindings']:
        binding = result['results']['bindings'][0]
        print("  Found Base Act info.")
        return {
            'base_act_uri': binding.get('baseActURI', {}).get('value'),
            'event_date': binding.get('eventDate', {}).get('value'),
            'memorial_label': binding.get('sourceMemorialLabel', {}).get('value')
        }
    else:
        print(f"  Could not find Base Act info via SPARQL for {rs_uri}")
        return None

def get_pre_publication_history(base_act_uri):
    """Gets pre-publication history (Message, Decision) for a Base Act URI."""
    if not base_act_uri:
        print("  Skipping pre-publication history: No Base Act URI provided.")
        return []
    print(f"  Fetching pre-publication history for Base Act {base_act_uri}...")

    query = f"""
        PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
        PREFIX eli: <http://data.europa.eu/eli/ontology#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

        SELECT DISTINCT ?eventTypeLabel ?eventDate ?sourceMemorialLabel ?sourceURI
        WHERE {{
            ?draft jolux:hasResultingLegalResource <{base_act_uri}> .
            ?draft rdf:type jolux:InitialDraft .
            ?draft jolux:draftHasLegislativeTask ?event .

            ?event jolux:legislativeTaskType ?eventType .
            OPTIONAL {{ ?eventType skos:prefLabel ?label_it . FILTER(lang(?label_it) = 'it') }}
            OPTIONAL {{ ?eventType skos:prefLabel ?label_any . }}
            BIND(COALESCE(?label_it, ?label_any, "Evento Legislativo Sconosciuto") AS ?eventTypeLabel)

            ?event jolux:decisionDate ?eventDate .

            OPTIONAL {{
              ?event jolux:legislativeTaskHasResultingLegalResource ?sourceURI_opt .
              OPTIONAL {{
                  ?sourceURI_opt jolux:isRealizedBy ?sourceExpression .
                  ?sourceExpression jolux:language <http://publications.europa.eu/resource/authority/language/ITA> .
                  ?sourceExpression jolux:historicalLegalId ?sourceMemorialLabel_opt .
              }}
              FILTER(STRSTARTS(STR(?sourceURI_opt), "https://fedlex.data.admin.ch/eli/fga/"))
              BIND(?sourceURI_opt AS ?sourceURI)
              BIND(COALESCE(?sourceMemorialLabel_opt, "") AS ?sourceMemorialLabel)
            }}
        }}
        ORDER BY DESC(?eventDate)
    """
    result = run_sparql_query(query)
    history_events = []
    if result and result['results']['bindings']:
        print(f"  Found {len(result['results']['bindings'])} pre-publication events.")
        for binding in result['results']['bindings']:
            history_events.append({
                'type': binding.get('eventTypeLabel', {}).get('value'),
                'date': binding.get('eventDate', {}).get('value'), # This is the decision date for these events
                'source_label': binding.get('sourceMemorialLabel', {}).get('value', ''),
                'source_uri': binding.get('sourceURI', {}).get('value', '')
            })
    else:
        print("  No pre-publication history found via SPARQL.")
    return history_events


def get_modification_history_from_es(taxonomy_uri):
    """Gets modification history from Elasticsearch data."""
    if not taxonomy_uri:
        print("  Cannot fetch ES history without Taxonomy URI.")
        return []
    print(f"  Fetching consolidation data from Elasticsearch for {taxonomy_uri}...")
    payload = {
      "size": 10000,
      "query": {
        "bool": {
          "must": [
            { "multi_match": { "query": taxonomy_uri, "fields": ["data.references.classifiedByTaxonomyEntry.keyword", "facets.classifiedByTaxonomyEntry.keyword"] }},
            { "term": { "data.type.keyword": "Consolidation" } }
          ]
        }
      },
       "_source": ["data.attributes.dateApplicability", "facets.consolidates", "data.uri", "facets.impacts.processType"] # Request more fields
    }

    result = run_elasticsearch_query(payload)
    history_events = []
    processed_source_uris_for_date = {}

    if result and 'hits' in result and 'hits' in result['hits']:
        print(f"  Found {len(result['hits']['hits'])} consolidation versions in ES.")
        for hit in result['hits']['hits']:
            source_data = hit.get('_source', {}).get('data', {})
            consolidation_uri = source_data.get('uri')
            consolidation_date = source_data.get('attributes', {}).get('dateApplicability', {}).get('xsd:date')

            if not consolidation_date:
                print(f"  Skipping consolidation version {consolidation_uri}: No applicability date.")
                continue

            facets = hit.get('_source', {}).get('facets', {})
            consolidates_info = facets.get('consolidates', [])

            if not consolidates_info:
                 print(f"  No 'consolidates' info found for version {consolidation_uri} (date: {consolidation_date}).")
                 continue

            if consolidation_date not in processed_source_uris_for_date:
                processed_source_uris_for_date[consolidation_date] = set()

            for mod_info in consolidates_info:
                source_uri = mod_info.get('uri')
                if not source_uri:
                    continue

                if source_uri in processed_source_uris_for_date[consolidation_date]:
                    continue
                processed_source_uris_for_date[consolidation_date].add(source_uri)

                decision_date = mod_info.get('dateDocument')
                event_date = consolidation_date # Date the change *applies*

                expression_info = mod_info.get('expression', {}).get('http://publications.europa.eu/resource/authority/language/ITA', {})
                source_label = expression_info.get('memorialLabel', '')

                # Determine event type more accurately
                process_type_uri = mod_info.get('processType')
                event_type = "Modifica" # Default
                if process_type_uri:
                    # Use last part of URI as a hint
                    type_hint = process_type_uri.split('/')[-1].lower()
                    if "scope" in type_hint or "geltungsbereich" in type_hint:
                        event_type = "Campo d'applicazione"
                    elif "repeal" in type_hint or "abrogation" in type_hint or "aufhebung" in type_hint:
                         event_type = "Abrogazione"
                    # Add more mappings if needed
                elif source_label and ("Abrogazione" in source_label or "Aufhebung" in source_label or "Abrogation" in source_label): # Check label if type is missing
                    event_type = "Abrogazione"

                history_events.append({
                    'type': event_type,
                    'date': event_date,
                    'decision_date': decision_date,
                    'source_label': source_label,
                    'source_uri': source_uri
                })
    else:
        print(f"  No consolidation versions found in Elasticsearch or error fetching for {taxonomy_uri}.")

    print(f"  Extracted {len(history_events)} distinct modification events from ES.")
    return history_events

# --- Main Function ---
def process_rs_laws(csv_filepath):
    all_histories = {}
    processed_rs_numbers = set()

    try:
        with open(csv_filepath, mode='r', encoding='utf-8') as infile:
            # Skip the triple quote delimiter line if present
            first_line = infile.readline()
            if '"""' in first_line:
                pass # Skip it
            else:
                infile.seek(0) # Rewind if it wasn't the delimiter

            reader = csv.DictReader(infile)
            # Clean field names if they have extra spaces
            reader.fieldnames = [name.strip() for name in reader.fieldnames]

            print(f"CSV Headers: {reader.fieldnames}") # Debug print

            # --- Check required headers ---
            required_headers = ['rsNumber', 'rsURI']
            if not all(h in reader.fieldnames for h in required_headers):
                missing = [h for h in required_headers if h not in reader.fieldnames]
                print(f"Error: CSV file missing required headers: {missing}")
                return None
            # --- End Check ---

            for row in reader:
                # Clean up spaces around values
                rs_number = row.get('rsNumber', '').strip()
                rs_uri_from_csv = row.get('rsURI', '').strip()

                if not rs_number or not rs_uri_from_csv:
                    print(f"Skipping row due to missing data: {row}")
                    continue

                if rs_number in processed_rs_numbers:
                    print(f"Skipping duplicate RS Number: {rs_number}")
                    continue

                print(f"\nProcessing RS: {rs_number} (URI from CSV: {rs_uri_from_csv})")

                current_rs_history = []
                base_act_uri_found = None
                taxonomy_uri = None

                # 1. Get Taxonomy URI (still needed for ES query)
                rs_info = get_rs_info_from_number(rs_number)
                if rs_info:
                    # Validate if rs_uri from SPARQL matches CSV (optional but good sanity check)
                    if rs_info['rs_uri'] != rs_uri_from_csv:
                         print(f"  Warning: RS URI mismatch for {rs_number}. CSV='{rs_uri_from_csv}', SPARQL='{rs_info['rs_uri']}'. Using CSV URI for consistency.")
                    taxonomy_uri = rs_info['taxonomy_uri']
                else:
                    print(f"  Skipping further processing for {rs_number} as RS info couldn't be fetched.")
                    processed_rs_numbers.add(rs_number) # Mark as processed even if failed
                    time.sleep(REQUEST_DELAY)
                    continue # Skip to next RS number

                # 2. Get Base Act Info (use URI from CSV as it's provided)
                base_act_info = get_base_act_and_entry_info(rs_uri_from_csv)
                if base_act_info:
                    base_act_uri_found = base_act_info.get('base_act_uri')
                    if base_act_info.get('event_date'):
                        current_rs_history.append({
                            'type': "Entrata in vigore (Atto base)",
                            'date': base_act_info['event_date'],
                            'decision_date': None, # Base act entry doesn't have a separate decision date in this context
                            'source_label': base_act_info.get('memorial_label', ''),
                            'source_uri': base_act_uri_found or ''
                        })
                    else:
                        print(f"  Warning: Base Act {base_act_uri_found} found, but no entry/publication date retrieved via SPARQL.")

                # 3. Get Pre-Publication History
                pre_pub_history = get_pre_publication_history(base_act_uri_found)
                current_rs_history.extend([{**evt, 'decision_date': evt['date']} for evt in pre_pub_history])


                # 4. Get Modification History from ES
                mod_history = get_modification_history_from_es(taxonomy_uri)
                current_rs_history.extend(mod_history)

                # 5. Sort and Deduplicate Events for this RS
                if current_rs_history:
                    unique_events = []
                    seen_event_keys = set()
                    # Sort primarily by effective date, secondarily by decision date (if available)
                    current_rs_history.sort(key=lambda x: (
                        datetime.strptime(x['date'], '%Y-%m-%d') if x.get('date') else datetime.min,
                        datetime.strptime(x['decision_date'], '%Y-%m-%d') if x.get('decision_date') else datetime.min
                        ), reverse=True)

                    for event in current_rs_history:
                         # Create a key to identify duplicates based on essential fields
                         event_key = (
                             event.get('type'),
                             event.get('date'),
                             event.get('decision_date'),
                             event.get('source_label'),
                             event.get('source_uri')
                         )
                         if event_key not in seen_event_keys:
                             unique_events.append(event)
                             seen_event_keys.add(event_key)
                    all_histories[rs_number] = unique_events
                else:
                     all_histories[rs_number] = [] # Store empty list if no history found


                processed_rs_numbers.add(rs_number)
                print(f"Finished processing {rs_number}. Waiting {REQUEST_DELAY}s...")
                time.sleep(REQUEST_DELAY) # Be polite to the servers

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_filepath}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during CSV processing: {e}")
        return None

    return all_histories


# --- Execution ---
if __name__ == "__main__":
    print("Starting history extraction...")
    final_data = process_rs_laws(CSV_FILE_PATH)

    if final_data is not None:
        print(f"\nSaving combined history to {OUTPUT_JSON_PATH}...")
        try:
            with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as outfile:
                json.dump(final_data, outfile, ensure_ascii=False, indent=2)
            print("Save complete.")
        except IOError as e:
            print(f"Error saving JSON file: {e}")
    else:
        print("Processing failed. No JSON file saved.")