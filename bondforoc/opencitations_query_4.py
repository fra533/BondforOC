from flask import Flask, jsonify
import requests
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any

app = Flask(__name__)

OPENCITATION_API_URL = "https://opencitations.net/api/v1/metadata/"
INPUT_FILENAME = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\Bond_crossref_validated\validated_keys_dois.csv"
CACHE_FILENAME = "opencitations_cache.json"
NOT_FOUND_FILENAME = "final_batch_notfound.json"
OPENCITATIONS_ACCESS_TOKEN = "234538a5-b679-4f83-846a-c3e7ebaedec0 "

logging.basicConfig(level=logging.INFO)

cache = {}

def load_cache():
    """Carica la cache dal file se esiste."""
    global cache
    if os.path.exists(CACHE_FILENAME):
        try:
            with open(CACHE_FILENAME, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logging.info(f"Cache caricata con {len(cache)} elementi")
        except Exception as e:
            logging.error(f"Errore nel caricamento della cache: {e}")
            cache = {}
    else:
        cache = {}

def save_cache():
    """Salva la cache su file."""
    try:
        with open(CACHE_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4)
        logging.info(f"Cache salvata con {len(cache)} elementi")
    except Exception as e:
        logging.error(f"Errore nel salvataggio della cache: {e}")

def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalizza un DOI per il confronto."""
    if not doi or doi == "None":
        return None
    
    if isinstance(doi, str):
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]
        elif doi.startswith("doi.org/"):
            doi = doi[8:]
        elif doi.startswith("DOI:"):
            doi = doi[4:].strip()
    
        return doi.lower()

    return doi

def query_with_retry(query_function, max_retries=3, timeout=5, *args, **kwargs) -> Dict:
    """Esegue una query con tentativi di ripetizione in caso di errore."""
    for attempt in range(max_retries):
        try:
            return query_function(*args, **kwargs)
        except Exception as e:
            logging.error(f"Errore durante il tentativo {attempt + 1}: {e}")
            if attempt < max_retries - 1:  
                time.sleep(timeout)
    raise Exception("Numero massimo di tentativi superato")

def query_opencitations(doi: str) -> Dict:
    """Interroga l'API di OpenCitations per un DOI specifico."""
    prefix = "doi:"  # Prefisso richiesto dall'API
    full_doi = f"{prefix}{doi}"
    headers = {"authorization": OPENCITATIONS_ACCESS_TOKEN}
    
    try:
        response = requests.get(f"{OPENCITATION_API_URL}{full_doi}", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Errore nell'interrogazione di OpenCitations per DOI {full_doi}: {e}")
        raise

def check_doi_in_opencitation(doi: str) -> Tuple[bool, Dict]:
    """
    Verifica se il DOI esiste in OpenCitation e recupera i metadati se disponibili.
    Restituisce una tupla (esiste, metadati)
    """
    # Verifica prima nella cache
    if doi in cache:
        logging.info(f"DOI {doi} trovato nella cache")
        return cache[doi].get("exists", False), cache[doi].get("metadata", {})
    
    prefix = "doi:"  # Prefisso richiesto dall'API
    full_doi = f"{prefix}{doi}"
    headers = {"authorization": OPENCITATIONS_ACCESS_TOKEN}
    
    try:
        response = requests.get(f"{OPENCITATION_API_URL}{full_doi}", headers=headers, timeout=10)
        
        if response.status_code == 200:
            metadata = response.json()
            cache[doi] = {
                "exists": True,
                "metadata": metadata
            }
            return True, metadata
        else:
            logging.info(f"Ricevuto status code {response.status_code} per DOI {full_doi}")
            cache[doi] = {
                "exists": False,
                "metadata": {}
            }
            return False, {}
    except requests.RequestException as e:
        logging.error(f"Errore nel controllo del DOI {full_doi}: {e}")
        cache[doi] = {
            "exists": False,
            "metadata": {},
            "error": str(e)
        }
        return False, {}

def read_input_file():
    """Legge il file di input nel formato specificato."""
    try:
        with open(INPUT_FILENAME, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            # Se il file ha un'intestazione, rimuovila
            if lines and "key,doi" in lines[0]:
                lines = lines[1:]
                
            doi_entries = []
            for line in lines:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    doi_entries.append({
                        "key": parts[0],
                        "doi": parts[1]
                    })
            
            return doi_entries
    except Exception as e:
        logging.error(f"Errore nella lettura del file di input: {e}")
        raise

@app.route('/check_opencitation', methods=['POST'])
def check_opencitation():
    try:
        # Carica la cache all'inizio
        load_cache()
        
        # Leggi il file di input
        entries = read_input_file()
        if not entries:
            return jsonify({"error": "Nessun DOI trovato nel file di input"}), 400
        
        results = []
        opencitation_success = 0
        opencitation_failure = 0
        not_found_dois = []
        metadata_collected = []  
        
        # Esegui richieste in parallelo
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_doi = {executor.submit(check_doi_in_opencitation, entry.get('doi')): entry for entry in entries}
            
            for future in as_completed(future_to_doi):
                entry = future_to_doi[future]
                key = entry.get('key')
                doi = entry.get('doi')
                
                try:
                    exists, metadata = future.result()
                    
                    if exists:
                        opencitation_success += 1
                        results.append({'key': key, 'doi': doi, 'status': 'found', 'metadata': metadata})
                        metadata_collected.append({'key': key, 'doi': doi, 'metadata': metadata})
                    else:
                        opencitation_failure += 1
                        results.append({'key': key, 'doi': doi, 'status': 'not found'})
                        not_found_dois.append({'key': key, 'doi': doi})
                except Exception as e:
                    logging.error(f"Errore nell'elaborazione del DOI {doi}: {e}")
                    opencitation_failure += 1
                    results.append({'key': key, 'doi': doi, 'status': 'error', 'error': str(e)})
                    not_found_dois.append({'key': key, 'doi': doi})
        
        save_cache()
        
        summary = {
            'total_dois': len(entries),
            'opencitation_success': opencitation_success,
            'opencitation_failure': opencitation_failure,
            'success_percentage': round((opencitation_success / len(entries)) * 100, 2) if entries else 0
        }
        
        with open(NOT_FOUND_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(not_found_dois, f, indent=4)
        
        with open("opencitations_metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata_collected, f, indent=4)
        
        return jsonify({
            'results': results, 
            'summary': summary
        })
    
    except FileNotFoundError:
        return jsonify({"error": f"File {INPUT_FILENAME} non trovato"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Errore nella decodifica del file JSON"}), 400
    except Exception as e:
        return jsonify({"error": f"Errore nell'elaborazione: {str(e)}"}), 500

if __name__ == '__main__':
    load_cache()
    app.run(debug=True)