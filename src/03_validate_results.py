import csv

def sanitize_title(title):
    return title.strip().lower()

def clean_doi(doi):
    # Funzione per pulire il DOI rimuovendo il prefisso 'https://doi.org/'
    return doi.replace('https://doi.org/', '').strip()

def analyze_doi_matches(gold_standard_file, crossref_response_file):
    with open(gold_standard_file, "r", encoding="utf-8") as gs_file:
        gs_reader = csv.DictReader(gs_file)
        gold_standard = {row["Key"]: row for row in gs_reader}

    with open(crossref_response_file, "r", encoding="utf-8") as cr_file:
        cr_reader = csv.DictReader(cr_file)
        crossref_responses = {row["Key"]: row for row in cr_reader}

    total_with_doi = 0  # Quanti DOI hanno "True" nella colonna ID_on_Crossref
    total_matches = 0  # Quanti DOI corrispondono

    # Ciclo sulle chiavi del gold standard
    for key, gs_row in gold_standard.items():
        id_on_crossref = gs_row.get("ID_on_Crossref", "").strip().lower() == "true"
        correct_doi = clean_doi(gs_row.get("DOI", ""))  # Pulizia del DOI corretto
        sanitized_title_gs = sanitize_title(gs_row.get("title", ""))  # Sanitizzazione del titolo

        # Conta i DOI presenti
        if id_on_crossref:
            total_with_doi += 1

            # Controlla se il DOI restituito da CrossRef è corretto
            crossref_row = crossref_responses.get(key)
            if crossref_row:
                best_doi = clean_doi(crossref_row.get("best_doi", ""))  # Pulizia del DOI da CrossRef
                sanitized_title_cr = sanitize_title(crossref_row.get("title", ""))  # Sanitizzazione del titolo da CrossRef
                
                # Controlla se i DOI corrispondono 
                if best_doi == correct_doi:
                    total_matches += 1

    print(f"Totale chiavi con DOI su CrossRef (ID_on_Crossref = True): {total_with_doi}")
    print(f"Totale DOI corretti restituiti dalla query CrossRef: {total_matches}")
    print(f"Percentuale di match: {total_matches / total_with_doi * 100:.2f}%" if total_with_doi > 0 else "Nessun DOI da confrontare.")

gold_standard_file = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\gold_standard_with_results.csv"
crossref_response_file = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\gold_crossref_response.csv"

analyze_doi_matches(gold_standard_file, crossref_response_file)
