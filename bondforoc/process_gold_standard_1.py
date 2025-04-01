import csv
import requests
import os
import chardet
import random
import time

random.seed(42)  # Per riproducibilità dei risultati

MAX_RETRIES = 3  # Numero massimo di tentativi per ogni richiesta
RETRY_DELAY = 5  # Secondi di attesa tra i retry

def detect_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
        return result['encoding']

def check_doi_on_crossref(doi, max_retries=MAX_RETRIES):
    """
    Verifica se un DOI è presente su Crossref con un meccanismo di retry.
    Restituisce True se trovato, False se non trovato e None in caso di errore API.
    """
    url = f"https://api.crossref.org/works/{doi}"
    attempt = 0

    while attempt < max_retries:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                return False
            else:
                attempt += 1
                print(f"⚠️ Tentativo {attempt}/{max_retries} fallito per DOI {doi}. Codice HTTP: {response.status_code}")
                time.sleep(RETRY_DELAY)
        except requests.RequestException as e:
            attempt += 1
            print(f"⚠️ Errore di connessione per DOI {doi} (Tentativo {attempt}/{max_retries}): {e}")
            time.sleep(RETRY_DELAY)

    print(f"❌ Errore definitivo per DOI {doi} dopo {max_retries} tentativi.")
    return None  # Se tutti i retry falliscono

def split_dataset(rows, training_size=300):
    """
    Divide i dati in training e validation set in modo casuale.
    """
    random.shuffle(rows)
    return rows[:training_size], rows[training_size:]

def process_csv(input_csv_path):
    """
    Legge un CSV, controlla i DOI su Crossref con retry e salva i risultati in 'results'.
    """
    if not os.path.exists(input_csv_path):
        print(f"❌ Il file {input_csv_path} non esiste.")
        return

    # Crea la cartella results se non esiste
    os.makedirs("results", exist_ok=True)

    # Rileva la codifica del file
    encoding = detect_file_encoding(input_csv_path)
    print(f"✅ Codifica rilevata per il file: {encoding}")

    try:
        with open(input_csv_path, mode='r', encoding=encoding, errors='replace') as infile:
            reader = csv.DictReader(infile, delimiter=';')
            
            # Pulisce i nomi delle colonne e ignora quelle vuote
            fieldnames = [field.strip() for field in reader.fieldnames if field.strip()]
            print("📋 Nomi delle colonne trovate nel file CSV:", fieldnames)

            if 'DOI' not in fieldnames:
                print("❌ La colonna 'DOI' non è presente nel file CSV.")
                return

            if 'Cinese_title' not in fieldnames:
                print("❌ La colonna 'Cinese_title' non è presente nel file CSV.")
                return

            # Aggiungi la colonna 'ID_on_Crossref'
            fieldnames.append('ID_on_Crossref')

            rows = []
            failed_requests = []

            for row in reader:
                # Filtra i campi extra dal dizionario in base a fieldnames
                row = {key: row[key].strip() if key in row and row[key] else '' for key in fieldnames[:-1]}

                # Verifica DOI con retry
                doi = row.get('DOI', '').strip()
                if doi and doi != 'None':
                    found_on_crossref = check_doi_on_crossref(doi)

                    if found_on_crossref is None:  # Se anche con retry fallisce
                        row['ID_on_Crossref'] = "Errore API"
                        failed_requests.append(row)
                    else:
                        row['ID_on_Crossref'] = found_on_crossref
                else:
                    row['ID_on_Crossref'] = False

                rows.append(row)

        # Divisione in training e validation set
        training_set, validation_set = split_dataset(rows)

        # Salvataggio dei risultati
        with open("results/training_set.csv", mode='w', encoding='utf-8', newline='') as train_file:
            writer = csv.DictWriter(train_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(training_set)

        with open("results/validation_set.csv", mode='w', encoding='utf-8', newline='') as val_file:
            writer = csv.DictWriter(val_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(validation_set)

        # Salvataggio dei fallimenti
        if failed_requests:
            with open("results/failed_requests.csv", mode='w', encoding='utf-8', newline='') as failed_file:
                writer = csv.DictWriter(failed_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(failed_requests)
            print(f"⚠️ Sono stati rilevati errori API: salvati in results/failed_requests.csv")

        print(f"✅ Training Set salvato in: results/training_set.csv ({len(training_set)} esempi)")
        print(f"✅ Validation Set salvato in: results/validation_set.csv ({len(validation_set)} esempi)")

    except UnicodeDecodeError as e:
        print(f"❌ Errore di decodifica del file CSV: {e}")
    except Exception as e:
        print(f"❌ Errore imprevisto durante l'elaborazione del file: {e}")

if __name__ == "__main__":
    input_csv = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\gold_standard.csv"
    process_csv(input_csv)
