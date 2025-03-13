import csv
import json
import time
import requests

# Funzione per timeout e retry della query
def query_with_retry(query_function, max_retries=3, timeout=5, *args, **kwargs):
    for attempt in range(max_retries):
        try:
            return query_function(*args, **kwargs)
        except Exception as e:
            print(f"Errore durante il tentativo {attempt + 1}: {e}")
            time.sleep(timeout)
    raise Exception("Numero massimo di tentativi superato")

# Funzione per interrogare CrossRef
def query_crossref(title, year):
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "filter": f"from-pub-date:{year},until-pub-date:{year + 1}",
        "rows": 5
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

# Funzione per selezionare il DOI migliore basandosi sui criteri:
# 1. Anno uguale al file di input +1
# 2. Almeno uno degli autori in comune
def select_best_doi(input_data, crossref_results):
    input_year = input_data.get("year")
    input_authors = {author["name"] for author in input_data.get("authors", [])}

    best_doi = None
    highest_score = -1

    for item in crossref_results.get("message", {}).get("items", []):
        score = 0

        if "published-print" in item and "date-parts" in item["published-print"]:
            year = item["published-print"]["date-parts"][0][0]
            if year == input_year + 1:
                score += 1

        crossref_authors = {author.get("family") for author in item.get("author", []) if "family" in author}
        if input_authors & crossref_authors:  # Intersezione tra autori
            score += 1

        if score > highest_score:
            highest_score = score
            best_doi = item.get("DOI")

    return best_doi

# Funzione principale per processare il JSON di input
def process_json(input_json, max_keys=5):
    results = {}

    # Elaborare solo un sottoinsieme del file
    keys_to_process = list(input_json.keys())[:max_keys]

    for key in keys_to_process:
        item = input_json[key]
        title = item.get("title")
        year = item.get("year")

        if title and year:
            print(f"Interrogazione di CrossRef per il titolo '{title}' e anno '{year}'...")

            # Recupero risultati da CrossRef
            try:
                crossref_results = query_with_retry(query_crossref, title=title, year=year)
                
                # Seleziona il DOI migliore
                best_doi = select_best_doi(item, crossref_results)
                
                results[key] = {
                    "title": title,
                    "best_doi": best_doi
                }
            except Exception as e:
                print(f"Errore nell'interrogazione per la chiave {key}: {e}")
                results[key] = {
                    "title": title,
                    "error": str(e)
                }
        else:
            print(f"Titolo o anno mancanti per la chiave {key}")
            results[key] = {
                "title": item.get("title", ""),
                "error": "Titolo o anno mancanti"
            }

    return results

# Funzione per elaborare il CSV di input
def process_csv_and_json(csv_file, input_json, output_csv):
    with open(csv_file, "r", encoding="ISO-8859-1") as f:  
        reader = csv.reader(f, delimiter=";")
        header = next(reader)  
        print(f"Intestazione CSV: {header}")  

        header = [col.strip() for col in header]

        if "Key" not in header:
            raise ValueError("Il file CSV deve contenere una colonna 'Key'")

        key_index = header.index("Key")  # Modifica qui per la colonna "Key"
        rows = [row for row in reader]

    results = []

    for row in rows:
        key = row[key_index]
        if key in input_json:
            item = input_json[key]
            title = item.get("title")
            year = item.get("year")

            if title and year:
                print(f"Interrogazione di CrossRef per la chiave '{key}', titolo '{title}' e anno '{year}'...")

                try:
                    crossref_results = query_with_retry(query_crossref, title=title, year=year)
                    best_doi = select_best_doi(item, crossref_results)
                    results.append({"Key": key, "title": title, "best_doi": best_doi})
                except Exception as e:
                    print(f"Errore nell'interrogazione per la chiave {key}: {e}")
                    results.append({"Key": key, "title": title, "error": str(e)})
            else:
                print(f"Titolo o anno mancanti per la chiave {key}")
                results.append({"Key": key, "title": item.get("title", ""), "error": "Titolo o anno mancanti"})

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Key", "title", "best_doi", "error"])  # Modifica qui per "Key"
        writer.writeheader()
        writer.writerows(results)

def save_results_to_file(results, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    input_file = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\Bondvalidation.json"  # Sostituisci con il percorso del tuo file
    output_file = "results.json"
    csv_input_file = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Documents\my_projects\BONDperOC\data\gold_standard.csv"  # Sostituisci con il percorso del tuo file CSV
    csv_output_file = "gold_crossref_response.csv"

    with open(input_file, "r", encoding="utf-8") as f:
        input_json = json.load(f)

    # Elaborare il JSON (solo un sottoinsieme di chiavi per il test)
    results = process_json(input_json, max_keys=2)  # max_keys per elaborare più o meno chiavi

    save_results_to_file(results, output_file)
    print(f"Risultati salvati in {output_file}")

    process_csv_and_json(csv_input_file, input_json, csv_output_file)
    print(f"Risultati salvati in {csv_output_file}")
