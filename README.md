# Swiss Law Graph Analysis

A comprehensive toolkit for extracting, modeling, and analyzing Swiss federal laws as a Knowledge Graph. This project transforms semi-structured legal documents (PDF/XML) from the Swiss Federal Gazette and Systematic Collection of Federal Law into a Neo4j graph database for advanced network analysis.

## 🏗️ Architecture Overview

The system follows a three-stage pipeline: **Extraction**, **Ingestion**, and **Analysis**.

1.  **Extraction Pipeline**: Downloads legal acts in multiple languages, parses complex PDF structures using hierarchical layout analysis, and extracts metadata (titles, markers, citations).
2.  **Database Ingestion**: Models the legal corpus as a Neo4j graph. It establishes nodes for Laws, Sections, and Annexes, and creates relationships for Citations (e.g., `CITES`, `MODIFIES`, `ABROGATES`).
3.  **Analysis Suite**: Leverages Graph Data Science (GDS) algorithms to identify central laws, community clusters, and temporal trends in Swiss legislation.

---

## 📂 Directory Structure

```text
.
├── notebooks/              # Jupyter notebooks for exploration and reporting
│   ├── analysis/           # Graph analysis, community detection, and language stats
│   ├── extraction/         # Interactive PDF/XML extraction development
│   └── archive/            # Historical/obsolete research notebooks
├── src/                    # Main source code (Python package)
│   ├── analysis/           # Production scripts for network metrics and comparison
│   ├── database/           # Neo4j population and graph modeling logic
│   ├── extraction/         # Multi-modal extraction pipeline
│   │   ├── pdf/            # Advanced PDF layout parsing and reconstruction
│   │   └── xml/            # XML-based metadata extraction
│   └── utils/              # Shared utilities (downloaders, logging, etc.)
├── plots/                  # Visual output from analysis
├── raw_data/               # (Not tracked) Directory for CSVs and mapping files
└── LawsDocs/               # (Not tracked) Directory for downloaded PDFs/XMLs/JSONs
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Neo4j Database (with APOC and Graph Data Science plugins)

### Installation
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your environment variables in a `.env` file:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_password
   ```

---

## 📔 Interactive Notebooks (`notebooks/`)

The project includes several Jupyter notebooks for exploratory data analysis (EDA), extraction validation, and high-level reporting.

### **1. Analysis Workflow (`notebooks/analysis/`)**
*   **`graph_analysis.ipynb`**: The primary entry point for network analysis. Includes PageRank, Betweenness centrality, and degree distributions.
*   **`community_detection.ipynb`**: Implements Louvain and Leiden algorithms to identify legislative clusters and domain-specific sub-graphs.
*   **`node_analysis.ipynb`**: Detailed statistical analysis of `Law` node attributes, including temporal trends in law enactment and validity.
*   **`legal_text_comparative_analysis.ipynb`**: Analyzes the linguistic characteristics of the legal corpus across Italian, French, and German versions.

### **2. Extraction & Ingestion Workflow (`notebooks/extraction/`)**
*   **`article_extraction_pipeline.ipynb`**: An interactive, step-by-step implementation of the PDF-to-JSON extraction process. Ideal for debugging and testing changes to the parsing logic.
*   **`analyze_footers_extractions.ipynb`**: Specifically focused on validating the accuracy of footnote and reference extraction from PDF margins.
*   **`db_prep.ipynb`**: Handles the final transformation and cleaning of extracted JSON data before it is ingested into Neo4j.
*   **`pdf_stats.ipynb`**: Generates high-level statistics about the PDF corpus, such as page counts, file sizes, and structural complexity.
*   **`nodes_from_url.ipynb`**: Demonstrates the logic for dynamically scraping law metadata from official Swiss government URLs.

---

## 📚 Useful Queries

### **SPARQL (Fedlex Metadata)**
These queries can be used at the [Fedlex SPARQL Endpoint](https://fedlex.data.admin.ch/sparqlendpoint).

#### **1. Retrieve Law Metadata by Year**
Finds all legal acts published in a specific year with their Italian labels.
```sparql
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>

SELECT DISTINCT ?act ?label ?date
WHERE {
  ?act rdf:type jolux:Act .
  ?act jolux:publicationDate ?date .
  ?act jolux:isRealizedBy ?expression .
  ?expression jolux:language <http://publications.europa.eu/resource/authority/language/ITA> .
  ?expression jolux:title ?label .
  FILTER(year(?date) = 2023)
} ORDER BY ?date LIMIT 100
```

#### **2. Find Amending Acts**
Identifies which laws amend a specific base law (e.g., the Civil Code).
```sparql
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>

SELECT ?amendingAct ?date
WHERE {
  ?amendingAct jolux:amends <http://fedlex.data.admin.ch/eli/oc/2023/154> . # Replace with Law URI
  ?amendingAct jolux:publicationDate ?date .
} ORDER BY DESC(?date)
```

---

### **Cypher (Graph Analysis)**
Run these in the Neo4j Browser or via the Python API.

#### **1. Top 10 Most Cited Laws**
Identifies the "Cornerstone" laws of the Swiss legal system based on total citations received from other sections.
```cypher
MATCH (source_law:Law)-[:HAS_ARTICLE]->(s:Section)
MATCH (s)-[r]->(target_law:Law)
WHERE type(r) IN ['CITATION', 'MODIFIES', 'ABROGATES']
RETURN target_law.lawId AS Law, count(r) AS Citations
ORDER BY Citations DESC
LIMIT 10
```

#### **2. Explore a Law's Internal Structure**
Retrieves all sections and annexes for a specific law.
```cypher
MATCH (l:Law {lawId: "RU 1999 181"})
OPTIONAL MATCH (l)-[:HAS_ARTICLE]->(s:Section)
OPTIONAL MATCH (l)-[:HAS_ANNEX]->(a:Annex)
RETURN l.title AS LawTitle, s.marker AS Article, a.title AS AnnexTitle
```

#### **3. Community Member Distribution**
If Louvain community detection has been run, this identifies the size of each legislative cluster.
```cypher
MATCH (l:Law)
WHERE l.louvain_community IS NOT NULL
RETURN l.louvain_community AS CommunityID, count(l) AS MemberCount
ORDER BY MemberCount DESC
```

---

## 🧩 Component Details

### 1. Extraction Pipeline (`src/extraction/`)

The extraction pipeline is designed to transform unstructured legal PDFs into structured JSON data by combining visual layout analysis with rule-based linguistic parsing.

#### **A. Deconstruction & Layout Analysis (`deconstruction.py`)**
*   **Visual Primitives**: Uses `PyMuPDF` (fitz) to extract text in a structured dictionary format, capturing precise coordinates (`bbox`), font styles, and formatting flags.
*   **Hierarchical ID System**: Every text fragment is assigned a unique, deterministic ID (e.g., `page-0.block-5.line-1.span-0`). This allows for precise spatial and logical referencing across the entire pipeline.
*   **Visual Feature Extraction**: Automatically detects superscripts (often used for footnote markers) by inspecting the `flags` bitmask in the PDF metadata.

#### **B. Multi-language Refined Extraction (`refined_extraction.py`)**
*   **Context-Aware Boilerplate Removal**: Implements language-specific configurations for Italian, French, and German to strip non-content elements like "Fedlex" URLs, "signée fait foi" notices, and page headers.
*   **Marker Detection**: Employs sophisticated regular expressions to identify various legal markers:
    *   **Roman Numerals**: Identifies major divisions (e.g., `I. Disposizioni generali`).
    *   **Article Markers**: Detects standard article headers (e.g., `Art. 1`, `Articolo 5`).
    *   **Digit-Dot Markers**: Recognizes numbered lists and sub-sections (e.g., `1.`, `2.`).
*   **Structural Parsing**: Titles are extracted by analyzing the spatial relationship between markers and surrounding text blocks, ensuring that only relevant headers are captured.

#### **C. Reconstruction & Contextual Mapping (`reconstruction.py`)**
*   **Span Linearization**: Flattens the hierarchical document structure into a searchable linear stream of "spans" while preserving metadata.
*   **Footnote Association**: Automatically links superscript numbers within the text to their corresponding footnote definitions at the bottom of the page or block.
*   **Reference Classification**: Identifies and labels citations to other legal bodies (e.g., `RS 173.110`, `FF 2023 154`) by searching for contextual labels in the vicinity of identified numbers.
*   **Boilerplate Filtering**: Identifies and excludes repetitive navigational elements and metadata blocks that do not belong to the primary legal text.

### 2. Database Population & Metadata Tracking
Handles the ingestion of law metadata and the reconstruction of law lifecycles.

*   **Data Sources**: 
    *   **Fedlex SPARQL endpoint** (`https://fedlex.data.admin.ch/sparqlendpoint`): Primary source for semantic metadata and relationship linking.
    *   **Elasticsearch proxy**: Used for retrieving historical versions and granular document metadata.
*   **Key Functions**:
    *   **Lifecycle Tracking**: Captures "Decision Dates", "Messages" (Botschaften/Messages), and "Abrogations" to model the temporal evolution of laws.
    *   **RS-to-RU Resolution**: Maps RS (Recueil Systématique) identifiers to RU (Recueil Officiel) numbers using `RS_RU_mapping.json`.
        *   **Logic & Implementation**: Handled by `src/extraction/rs_history.py`. It resolves RS numbers to RU identifiers by querying the Fedlex SPARQL endpoint to ensure citations point to specific, valid versions of the law.
        *   **SPARQL Query**:
          ```sparql
          PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
          PREFIX eli: <http://data.europa.eu/eli/ontology#>
          PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

          SELECT ?baseActURI ?eventDate ?sourceMemorialLabel
          WHERE {
              <RS_URI> jolux:basicAct ?baseActURI .
              OPTIONAL { ?baseActURI jolux:dateEntryInForce ?date1 . }
              OPTIONAL { ?baseActURI jolux:publicationDate ?date2 . }
              BIND(COALESCE(?date1, ?date2) AS ?eventDate)
              OPTIONAL {
                  ?baseActURI jolux:isRealizedBy ?expression .
                  ?expression jolux:language <http://publications.europa.eu/resource/authority/language/ITA> .
                  ?expression jolux:historicalLegalId ?sourceMemorialLabel .
              }
              FILTER(BOUND(?baseActURI))
          } LIMIT 1
          ```
*   **Graph Construction**: Orchestrates the creation of core nodes for `Laws`, `Articles`, and `Cantons` in Neo4j, establishing the foundational structure for network analysis.

### 3. Database Modeling (`src/database/`)

The legal corpus is modeled as a Property Graph in Neo4j, optimized for multi-hop citation analysis and domain discovery.

*   **Schema & Attributes**:
    *   **`Law` Nodes**: The primary legal entities.
        *   `act`: Permanent URI from Fedlex (e.g., `.../eli/oc/2023/154`).
        *   `lawId`: Standardized identifier (e.g., `RU 2023 154`).
        *   `title_it/fr/de`: Multilingual document titles.
        *   `validity`: Current status (In force, Repealed, etc.).
        *   `publicationDate`, `decisionDate`, `entryintoforceDate`.
    *   **`Section` Nodes**: Granular subdivisions (Articles).
        *   `marker`: The article number (e.g., `Art. 1`).
        *   `text`: The actual legal prose.
        *   `topics`: NLP-extracted thematic tags.
    *   **`Annex` Nodes**: Appendices and supplementary documents attached to laws.
*   **Relationship Semantics**:
    *   `HAS_ARTICLE` / `HAS_ANNEX`: Structural hierarchy (Law → Section/Annex).
    *   `CITES`: Standard reference from one section to another law.
    *   `AMENDS`: Direct legislative updates.
    *   `REPLACES`: Temporal succession where a new law supersedes an old one.
*   **Ingestion Pipeline**: `populate.py` implements a batched `UNWIND` pattern to handle thousands of records efficiently, ensuring idempotency via `MERGE` operations on unique act URIs.

### 4. Network Analysis (`src/analysis/`)

Utilizes the **Neo4j Graph Data Science (GDS)** library to extract insights from the legislative network.

*   **Centrality Suite**:
    *   **PageRank**: Measures the "prestige" or foundational importance of a law based on citations from other high-importance laws.
    *   **Betweenness**: Identifies "bridge" laws that connect disparate legislative domains.
    *   **Degree (In/Out)**: Identifies the most cited laws (In-degree) and the most "active" or complex amending acts (Out-degree).
*   **Community Detection**:
    *   **Louvain & Leiden**: Partitions the graph into clusters. These clusters often reveal hidden legislative domains (e.g., "Health Care Cluster", "Financial Regulations Cluster") where laws are densely interconnected despite belonging to different federal departments.
*   **Linguistic & Accuracy Analysis**:
    *   **NLP Topics**: Every `Section` is tagged with topics using NLP models, allowing for semantic search across the graph.
    *   **Accuracy Benchmarking**: `compare_accuracy.py` provides a framework to compare the fidelity of PDF-extracted text against official XML sources, quantifying the error rate of the layout-aware parser.
    *   **Language Analysis**: `compare_languages.py` evaluates the consistency of legal terminology and structure across the three official national languages.

