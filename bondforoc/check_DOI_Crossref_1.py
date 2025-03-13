import csv
import requests
import os
import chardet

def detect_file_encoding(file_path):
    """
    Rileva la codifica di un file e restituisce il tipo di codifica rilevata.
    """
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
        return result['encoding']

def check_doi_on_crossref(doi):
    """
    Verifica se un DOI è presente su Crossref.
    Restituisce True se trovato, altrimenti False.
    """
    url = f"https://api.crossref.org/works/{doi}"
    try:
        response = requests.get(url, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

def process_csv(input_csv_path, output_csv_path):
    """
    Legge un CSV, controlla i DOI su Crossref e salva i risultati in un nuovo CSV.
    Gestisce colonne vuote o extra.
    """
    if not os.path.exists(input_csv_path):
        print(f"Il file {input_csv_path} non esiste.")
        return

    # Rileva la codifica del file
    encoding = detect_file_encoding(input_csv_path)
    print(f"Codifica rilevata per il file: {encoding}")

    try:
        with open(input_csv_path, mode='r', encoding=encoding, errors='replace') as infile:
            reader = csv.DictReader(infile, delimiter=';')
            
            # Pulisce i nomi delle colonne e ignora quelle vuote
            fieldnames = [field.strip() for field in reader.fieldnames if field.strip()]
            print("Nomi delle colonne trovate nel file CSV (senza spazi e colonne vuote):", fieldnames)

            if 'DOI' not in fieldnames:
                print("La colonna 'DOI' non è presente nel file CSV.")
                return

            if 'Cinese_title' not in fieldnames:
                print("La colonna 'Cinese_title' non è presente nel file CSV.")
                return

            # Aggiungere la colonna 'ID_on_Crossref'
            fieldnames.append('ID_on_Crossref')

            total_rows = 0
            doi_count = 0
            doi_on_crossref_count = 0
            chinese_title_count = 0
            chinese_with_doi_not_on_crossref = 0
            chinese_with_doi_on_crossref = 0
            chinese_without_doi = 0

            rows = []
            for row in reader:
                total_rows += 1

                # Filtra i campi extra dal dizionario in base a fieldnames
                row = {key: row[key].strip() if key in row and row[key] else '' for key in fieldnames[:-1]}

                # Verifica DOI
                doi = row.get('DOI', '').strip()
                chinese_title = row.get('Cinese_title', '').strip()

                if doi and doi != 'None':
                    doi_count += 1
                    found_on_crossref = check_doi_on_crossref(doi)
                    row['ID_on_Crossref'] = found_on_crossref

                    # Aggiorna i contatori basati sul titolo cinese
                    if chinese_title:
                        if found_on_crossref:
                            chinese_with_doi_on_crossref += 1
                        else:
                            chinese_with_doi_not_on_crossref += 1

                    if found_on_crossref:
                        doi_on_crossref_count += 1
                else:
                    row['ID_on_Crossref'] = False

                    # Conta le risorse senza DOI e con titolo cinese
                    if chinese_title:
                        chinese_without_doi += 1

                # Conta tutte le risorse con titolo cinese
                if chinese_title:
                    chinese_title_count += 1

                rows.append(row)

        with open(output_csv_path, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"Resoconti:")
        print(f"- Numero totale di risorse: {total_rows}")
        print(f"- Numero di risorse con DOI: {doi_count} ({doi_count / total_rows:.2%})")
        print(f"- Numero di DOI presenti su Crossref: {doi_on_crossref_count} ({doi_on_crossref_count / doi_count:.2%})")
        print(f"- Numero di risorse con titolo cinese: {chinese_title_count} ({chinese_title_count / total_rows:.2%})")
        print(f"- Risorse con DOI ma non trovate su Crossref e con titolo cinese: {chinese_with_doi_not_on_crossref}")
        print(f"- Risorse con DOI trovate su Crossref e con titolo cinese: {chinese_with_doi_on_crossref}")
        print(f"- Risorse senza DOI e con titolo cinese: {chinese_without_doi}")

        print(f"File salvato con i risultati in: {output_csv_path}")

    except UnicodeDecodeError as e:
        print(f"Errore di decodifica del file CSV: {e}")
        print("Verifica la codifica del file e riprova.")
    except Exception as e:
        print(f"Errore imprevisto durante l'elaborazione del file: {e}")

if __name__ == "__main__":
    input_csv = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\gold_standard.csv"
    output_csv = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\gold_standard_with_results.csv"
    process_csv(input_csv, output_csv)
