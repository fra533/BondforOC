import requests
import json
import logging
import os
import time
import signal
import sys
import re
from typing import Dict, List, Optional, Tuple, Any

# Configurazione
OPENCITATION_API_URL = "https://opencitations.net/index/api/v1/metadata/"
INPUT_FILENAME = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\Bond_crossref_validated\validated_keys_dois.csv"

# Creazione della cartella di output
OUTPUT_DIR = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\OC_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# File di output nella cartella OC_results
CACHE_FILENAME = os.path.join(OUTPUT_DIR, "opencitations_cache.json")
NOT_FOUND_FILENAME = os.path.join(OUTPUT_DIR, "final_batch_notfound.json")
METADATA_FILENAME = os.path.join(OUTPUT_DIR, "opencitations_metadata.json")
CONVERTED_FILENAME = os.path.join(OUTPUT_DIR, "converted_metadata.json")  # NUOVO
LOG_FILENAME = os.path.join(OUTPUT_DIR, "opencitations_app.log")
SUMMARY_FILENAME = os.path.join(OUTPUT_DIR, "processing_summary.json")
RETRY_FILENAME = os.path.join(OUTPUT_DIR, "retry_candidates.json")

OPENCITATIONS_ACCESS_TOKEN = "234538a5-b679-4f83-846a-c3e7ebaedec0 "
CACHE_SAVE_INTERVAL = 100  # Salva la cache ogni 100 richieste
RATE_LIMIT_DELAY = 0.3  # Tempo di attesa tra le richieste in secondi
MAX_RETRIES = 5  # Numero massimo di tentativi per richiesta
BACKOFF_FACTOR = 2  # Fattore di backoff per ritardi esponenziali
TEST_BATCH_SIZE = 100  # Numero di query per il test iniziale

# Definizione degli errori per cui vale la pena riprovare
RETRY_ERROR_CODES = [429, 500, 502, 503, 504]  # Rate limit, server errors
RETRY_EXCEPTIONS = ['Timeout', 'ConnectionError', 'ReadTimeout', 'ConnectTimeout']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILENAME),
        logging.StreamHandler()
    ]
)

cache = {}
processed_count = 0
cache_modified = False

# ===============================
# FUNZIONI DI CONVERSIONE FORMATO
# ===============================

def parse_authors(author_string: str) -> List[Dict[str, str]]:
    """
    Converte la stringa degli autori nel formato desiderato.
    Input: "Wang, Xiaonan; Zhang, Daoyong; Qian, Haifeng; ..."
    Output: [{"name": "Xiaonan Wang", "org": ""}, ...]
    """
    if not author_string:
        return []
    
    authors = []
    # Dividi per punto e virgola per separare gli autori
    author_parts = author_string.split(';')
    
    for author_part in author_parts:
        author_part = author_part.strip()
        if not author_part:
            continue
            
        # Rimuovi ORCID ID se presente (formato: 0000-0000-0000-0000)
        author_part = re.sub(r',?\s*\d{4}-\d{4}-\d{4}-\d{4}[X\d]?', '', author_part)
        
        # Se contiene una virgola, assume formato "Cognome, Nome"
        if ',' in author_part:
            parts = author_part.split(',', 1)
            if len(parts) == 2:
                surname = parts[0].strip()
                name = parts[1].strip()
                full_name = f"{name} {surname}"
            else:
                full_name = author_part.strip()
        else:
            full_name = author_part.strip()
        
        if full_name:
            authors.append({
                "name": full_name,
                "org": ""
            })
    
    return authors

def extract_keywords_from_title(title: str) -> List[str]:
    """
    Estrae parole chiave dal titolo (implementazione basilare).
    Potresti migliorare questa funzione con tecniche NLP più avanzate.
    """
    if not title:
        return []
    
    # Parole comuni da escludere
    stop_words = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 
        'to', 'was', 'were', 'will', 'with', 'between', 'using', 'through',
        'this', 'these', 'those', 'their', 'them', 'than', 'when', 'where',
        'which', 'while', 'who', 'how', 'what', 'can', 'could', 'should',
        'would', 'may', 'might', 'must', 'shall', 'study', 'analysis'
    }
    
    # Estrai parole dal titolo
    words = re.findall(r'\b[a-zA-Z]+\b', title.lower())
    keywords = [word for word in words if len(word) > 3 and word not in stop_words]
    
    # Rimuovi duplicati mantenendo l'ordine
    seen = set()
    unique_keywords = []
    for keyword in keywords:
        if keyword not in seen:
            seen.add(keyword)
            unique_keywords.append(keyword)
    
    return unique_keywords[:15]  # Limita a 15 parole chiave

def parse_year(year_string: str) -> Optional[int]:
    """
    Estrae l'anno dalla stringa anno.
    Input: "2018-02" -> Output: 2018
    """
    if not year_string:
        return None
    
    # Cerca un anno a 4 cifre
    year_match = re.search(r'\b(19|20)\d{2}\b', str(year_string))
    if year_match:
        return int(year_match.group())
    
    return None

def convert_metadata_format(opencitations_data: List[Dict]) -> Dict[str, Dict]:
    """
    Converte i dati dal formato OpenCitations al formato target.
    
    Args:
        opencitations_data: Lista di dizionari nel formato OpenCitations
        
    Returns:
        Dizionario nel formato target con chiavi = key dei paper originali
    """
    converted_data = {}
    
    for paper in opencitations_data:
        key = paper.get("key")
        if not key:
            continue
            
        metadata_list = paper.get("metadata", [])
        if not metadata_list:
            continue
            
        # Prendi il primo elemento dei metadati (dovrebbe essere solo uno)
        metadata = metadata_list[0] if isinstance(metadata_list, list) else metadata_list
        
        # Estrai i dati
        title = metadata.get("title", "")
        authors_string = metadata.get("author", "")
        year_string = metadata.get("year", "")
        venue = metadata.get("source_title", "")
        
        # Converti nel formato target
        converted_paper = {
            "id": key,
            "title": title,
            "abstract": "",  # Non disponibile nei dati OpenCitations
            "keywords": extract_keywords_from_title(title),
            "authors": parse_authors(authors_string),
            "venue": venue,
            "year": parse_year(year_string)
        }
        
        converted_data[key] = converted_paper
    
    return converted_data

# ===============================
# FUNZIONI ORIGINALI MODIFICATE
# ===============================

# Gestione per l'interruzione da tastiera
def signal_handler(sig, frame):
    logging.info("Interruzione rilevata, salvataggio della cache...")
    save_cache()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def is_retryable_error(error_code=None, exception_type=None):
    """Determina se un errore è candidato per un retry."""
    if error_code and error_code in RETRY_ERROR_CODES:
        return True
    if exception_type and any(retry_type in str(exception_type) for retry_type in RETRY_EXCEPTIONS):
        return True
    return False

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
            if os.path.exists(CACHE_FILENAME):
                backup_name = f"{CACHE_FILENAME}.bak.{int(time.time())}"
                try:
                    os.rename(CACHE_FILENAME, backup_name)
                    logging.info(f"Backup della cache creato: {backup_name}")
                except Exception as e:
                    logging.error(f"Impossibile creare backup della cache: {e}")
            cache = {}
    else:
        cache = {}

def save_cache():
    """Salva la cache su file."""
    global cache_modified
    
    if not cache_modified:
        logging.info("Nessuna modifica alla cache, salvataggio non necessario")
        return
        
    try:
        temp_filename = f"{CACHE_FILENAME}.temp"
        with open(temp_filename, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4)
        
        if os.path.exists(CACHE_FILENAME):
            os.replace(temp_filename, CACHE_FILENAME)
        else:
            os.rename(temp_filename, CACHE_FILENAME)
            
        logging.info(f"Cache salvata con {len(cache)} elementi")
        cache_modified = False
    except Exception as e:
        logging.error(f"Errore nel salvataggio della cache: {e}")

def save_retry_candidates(retry_candidates):
    """Salva i candidati per il retry."""
    try:
        with open(RETRY_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(retry_candidates, f, indent=4)
        logging.info(f"Salvati {len(retry_candidates)} candidati per retry in {RETRY_FILENAME}")
    except Exception as e:
        logging.error(f"Errore nel salvataggio dei candidati retry: {e}")

def load_retry_candidates():
    """Carica i candidati per il retry da file precedente."""
    if os.path.exists(RETRY_FILENAME):
        try:
            with open(RETRY_FILENAME, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Errore nel caricamento dei candidati retry: {e}")
    return []

def save_results(results, metadata_collected, not_found_dois, summary, retry_candidates=None):
    """Salva tutti i file di output, inclusa la versione convertita."""
    try:
        # Salva i DOI non trovati
        with open(NOT_FOUND_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(not_found_dois, f, indent=4)
        logging.info(f"Salvati {len(not_found_dois)} DOI non trovati in {NOT_FOUND_FILENAME}")
        
        # Salva i metadati raccolti (formato originale)
        with open(METADATA_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(metadata_collected, f, indent=4)
        logging.info(f"Salvati metadati per {len(metadata_collected)} DOI in {METADATA_FILENAME}")
        
        # NUOVO: Converti e salva nel formato target
        converted_count = 0
        if metadata_collected:
            converted_data = convert_metadata_format(metadata_collected)
            converted_count = len(converted_data)
            with open(CONVERTED_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(converted_data, f, indent=4)
            logging.info(f"Salvati metadati convertiti per {converted_count} DOI in {CONVERTED_FILENAME}")
        
        # Salva un riepilogo dettagliato
        with open(SUMMARY_FILENAME, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': summary,
                'timestamp': time.time(),
                'total_results': len(results),
                'converted_papers': converted_count
            }, f, indent=4)
        logging.info(f"Riepilogo salvato in {SUMMARY_FILENAME}")
        
        # Salva i candidati per retry se presenti
        if retry_candidates:
            save_retry_candidates(retry_candidates)
        
    except Exception as e:
        logging.error(f"Errore nel salvataggio dei risultati: {e}")
        raise

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
    
        return doi.lower().strip()

    return doi

def query_with_retry(doi: str, max_retries=MAX_RETRIES) -> Tuple[bool, Dict, Optional[str]]:
    """Esegue una query con backoff esponenziale in caso di errore. Restituisce anche il tipo di errore."""
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return False, {}, None
        
    headers = {"authorization": OPENCITATIONS_ACCESS_TOKEN.strip()}
    last_error_type = None
    
    for attempt in range(max_retries):
        try:
            url = f"{OPENCITATION_API_URL}{normalized_doi}"
            logging.debug(f"Richiesta a: {url}")
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 429:
                wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** attempt)
                logging.warning(f"Rate limit raggiunto. Attesa di {wait_time}s prima del tentativo {attempt + 1}")
                last_error_type = f"HTTP_{response.status_code}"
                time.sleep(wait_time)
                continue
                
            if response.status_code in [500, 502, 503, 504]:
                wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** attempt)
                logging.warning(f"Errore {response.status_code} per DOI {normalized_doi}. Attesa di {wait_time}s prima del tentativo {attempt + 1}")
                last_error_type = f"HTTP_{response.status_code}"
                time.sleep(wait_time)
                continue
                
            if response.status_code == 404:
                logging.info(f"DOI {normalized_doi} non trovato in OpenCitations (404)")
                return False, {}, "HTTP_404"
                
            response.raise_for_status()
            return True, response.json(), None
            
        except requests.exceptions.Timeout as e:
            wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** attempt)
            logging.warning(f"Timeout per DOI {normalized_doi}. Attesa di {wait_time}s prima del tentativo {attempt + 1}")
            last_error_type = "Timeout"
            time.sleep(wait_time)
            
        except requests.exceptions.ConnectionError as e:
            wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** attempt)
            logging.error(f"Errore di connessione per DOI {normalized_doi}: {e}. Attesa di {wait_time}s prima del tentativo {attempt + 1}")
            last_error_type = "ConnectionError"
            time.sleep(wait_time)
            
        except requests.exceptions.RequestException as e:
            wait_time = RATE_LIMIT_DELAY * (BACKOFF_FACTOR ** attempt)
            logging.error(f"Errore nella richiesta per DOI {normalized_doi}: {e}. Attesa di {wait_time}s prima del tentativo {attempt + 1}")
            last_error_type = str(type(e).__name__)
            time.sleep(wait_time)
    
    logging.error(f"Tutti i tentativi falliti per DOI {normalized_doi}. Ultimo errore: {last_error_type}")
    return False, {}, last_error_type

def check_doi_in_opencitation(doi: str, force_refresh=False) -> Tuple[bool, Dict, Optional[str]]:
    """Verifica se il DOI esiste in OpenCitation e recupera i metadati se disponibili."""
    global processed_count, cache_modified
    
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return False, {}, None
    
    # Verifica prima nella cache (solo se non forziamo il refresh)
    if not force_refresh and normalized_doi in cache:
        cached_entry = cache[normalized_doi]
        # Se c'è un errore nella cache e è retryable, ignora la cache
        if cached_entry.get("error_type") and is_retryable_error(exception_type=cached_entry.get("error_type")):
            logging.info(f"DOI {normalized_doi} nella cache con errore retryable, rifacendo la query")
        else:
            logging.debug(f"DOI {normalized_doi} trovato nella cache")
            return cached_entry.get("exists", False), cached_entry.get("metadata", {}), cached_entry.get("error_type")
    
    # Aggiungi un piccolo ritardo per rispettare rate limit
    time.sleep(RATE_LIMIT_DELAY)
    
    exists, metadata, error_type = query_with_retry(normalized_doi)
    
    # Aggiorna la cache
    cache[normalized_doi] = {
        "exists": exists,
        "metadata": metadata if exists else {},
        "error_type": error_type,
        "timestamp": time.time()
    }
    cache_modified = True
    
    return exists, metadata, error_type

def read_input_file():
    """Legge il file di input nel formato specificato."""
    try:
        with open(INPUT_FILENAME, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            if lines and "key,doi" in lines[0]:
                lines = lines[1:]
                
            doi_entries = []
            for line in lines:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    doi = normalize_doi(parts[1])
                    if doi:
                        doi_entries.append({
                            "key": parts[0],
                            "doi": doi
                        })
            
            return doi_entries
    except Exception as e:
        logging.error(f"Errore nella lettura del file di input: {e}")
        raise

def process_batch(entries, start_idx, end_idx, test_mode=False, retry_mode=False):
    """Elabora un batch di DOI in modo sequenziale."""
    global processed_count
    
    results = []
    opencitation_success = 0
    opencitation_failure = 0
    not_found_dois = []
    metadata_collected = []
    retry_candidates = []
    
    batch_entries = entries[start_idx:end_idx]
    total_batch = len(batch_entries)
    
    mode_text = "(MODALITÀ TEST)" if test_mode else "(MODALITÀ RETRY)" if retry_mode else ""
    logging.info(f"Elaborazione batch {start_idx+1}-{end_idx} di {len(entries)} totali {mode_text}")
    
    for i, entry in enumerate(batch_entries):
        key = entry.get('key')
        doi = entry.get('doi')
        
        current_global_idx = start_idx + i + 1
        
        if current_global_idx % 20 == 0 or current_global_idx == end_idx:
            logging.info(f"Progresso: {current_global_idx}/{end_idx} - Successi: {opencitation_success}, Fallimenti: {opencitation_failure}")
        
        try:
            # Se siamo in modalità retry, forza il refresh della cache
            exists, metadata, error_type = check_doi_in_opencitation(doi, force_refresh=retry_mode)
            processed_count += 1
            
            if exists:
                opencitation_success += 1
                results.append({'key': key, 'doi': doi, 'status': 'found', 'metadata': metadata})
                metadata_collected.append({'key': key, 'doi': doi, 'metadata': metadata})
            else:
                opencitation_failure += 1
                result_entry = {'key': key, 'doi': doi, 'status': 'not found'}
                
                # Se c'è un errore e è retryable, aggiungi ai candidati per retry
                if error_type and is_retryable_error(exception_type=error_type):
                    retry_candidates.append({
                        'key': key, 
                        'doi': doi, 
                        'error_type': error_type,
                        'timestamp': time.time()
                    })
                    result_entry['error_type'] = error_type
                    result_entry['retryable'] = True
                else:
                    result_entry['error_type'] = error_type
                    result_entry['retryable'] = False
                
                results.append(result_entry)
                not_found_dois.append({'key': key, 'doi': doi, 'error_type': error_type})
                
            # Salvataggio periodico della cache
            if processed_count % CACHE_SAVE_INTERVAL == 0:
                logging.info(f"Salvataggio periodico della cache dopo {processed_count} elementi elaborati")
                save_cache()
                
        except Exception as e:
            logging.error(f"Errore nell'elaborazione del DOI {doi}: {e}")
            opencitation_failure += 1
            
            # Determina se l'errore è retryable
            is_retryable = is_retryable_error(exception_type=str(e))
            
            if is_retryable:
                retry_candidates.append({
                    'key': key, 
                    'doi': doi, 
                    'error_type': str(e),
                    'timestamp': time.time()
                })
            
            results.append({
                'key': key, 
                'doi': doi, 
                'status': 'error', 
                'error': str(e),
                'retryable': is_retryable
            })
            not_found_dois.append({'key': key, 'doi': doi, 'error_type': str(e)})
    
    return results, metadata_collected, not_found_dois, opencitation_success, opencitation_failure, retry_candidates

def process_retry_batch():
    """Processa i DOI candidati per retry da precedenti esecuzioni."""
    retry_candidates = load_retry_candidates()
    
    if not retry_candidates:
        logging.info("Nessun candidato per retry trovato.")
        return None, None, None, 0, 0, []
    
    logging.info(f"Trovati {len(retry_candidates)} candidati per retry.")
    
    # Converti in formato compatibile
    retry_entries = []
    for candidate in retry_candidates:
        retry_entries.append({
            "key": candidate['key'],
            "doi": candidate['doi']
        })
    
    return process_batch(retry_entries, 0, len(retry_entries), retry_mode=True)

def main():
    """Funzione principale che gestisce l'intero processo."""
    global processed_count, cache_modified
    
    try:
        # Carica la cache all'inizio
        load_cache()
        processed_count = 0
        cache_modified = False
        
        # Controlla se ci sono candidati per retry da precedenti esecuzioni
        retry_candidates = load_retry_candidates()
        if retry_candidates:
            print(f"\nTrovati {len(retry_candidates)} DOI candidati per retry da precedenti esecuzioni.")
            retry_choice = input("Vuoi processare prima i retry? (s/n): ").strip().lower()
            
            if retry_choice in ['s', 'si', 'y', 'yes']:
                logging.info("="*60)
                logging.info("FASE RETRY: RIPROCESSAMENTO DOI FALLITI")
                logging.info("="*60)
                
                retry_results, retry_metadata, retry_not_found, retry_success, retry_failure, new_retry_candidates = process_retry_batch()
                
                if retry_results:
                    save_cache()
                    
                    retry_summary = {
                        'total_dois': len(retry_candidates),
                        'opencitation_success': retry_success,
                        'opencitation_failure': retry_failure,
                        'success_percentage': round((retry_success / len(retry_candidates)) * 100, 2) if retry_candidates else 0,
                        'new_retry_candidates': len(new_retry_candidates)
                    }
                    
                    save_results(retry_results, retry_metadata, retry_not_found, retry_summary, new_retry_candidates)
                    
                    logging.info("="*60)
                    logging.info("RISULTATI DEL RETRY:")
                    logging.info(f"DOI ritentati: {len(retry_candidates)}")
                    logging.info(f"Nuovi successi: {retry_success}")
                    logging.info(f"Ancora falliti: {retry_failure}")
                    logging.info(f"Nuovi candidati retry: {len(new_retry_candidates)}")
                    logging.info(f"Percentuale di successo retry: {retry_summary['success_percentage']}%")
                    logging.info("="*60)
        
        # Leggi il file di input
        entries = read_input_file()
        if not entries:
            logging.error("Nessun DOI trovato nel file di input")
            return
        
        logging.info(f"Totale DOI da elaborare: {len(entries)}")
        logging.info(f"I risultati saranno salvati in: {OUTPUT_DIR}")
        
        # FASE 1: Test con i primi 100 DOI
        logging.info("="*60)
        logging.info("FASE 1: TEST CON I PRIMI 100 DOI")
        logging.info("="*60)
        
        test_end = min(TEST_BATCH_SIZE, len(entries))
        test_results, test_metadata, test_not_found, test_success, test_failure, test_retry_candidates = process_batch(
            entries, 0, test_end, test_mode=True
        )
        
        # Salva i risultati del test
        save_cache()
        
        test_summary = {
            'total_dois': test_end,
            'opencitation_success': test_success,
            'opencitation_failure': test_failure,
            'success_percentage': round((test_success / test_end) * 100, 2) if test_end > 0 else 0,
            'retry_candidates': len(test_retry_candidates)
        }
        
        save_results(test_results, test_metadata, test_not_found, test_summary, test_retry_candidates)
        
        logging.info("="*60)
        logging.info("RISULTATI DEL TEST:")
        logging.info(f"DOI elaborati: {test_end}")
        logging.info(f"Successi: {test_success}")
        logging.info(f"Fallimenti: {test_failure}")
        logging.info(f"Candidati per retry: {len(test_retry_candidates)}")
        logging.info(f"Percentuale di successo: {test_summary['success_percentage']}%")
        logging.info("="*60)
        
        # Pausa per consentire la verifica
        print("\n" + "="*60)
        print("TEST COMPLETATO!")
        print(f"Sono stati elaborati i primi {test_end} DOI.")
        print(f"Controlla i file di output in: {OUTPUT_DIR}")
        print(f"- {os.path.basename(NOT_FOUND_FILENAME)}")
        print(f"- {os.path.basename(METADATA_FILENAME)}")
        print(f"- {os.path.basename(CONVERTED_FILENAME)} (NUOVO FORMATO)")  # AGGIUNTO
        print(f"- {os.path.basename(SUMMARY_FILENAME)}")
        print(f"- {os.path.basename(CACHE_FILENAME)}")
        if test_retry_candidates:
            print(f"- {os.path.basename(RETRY_FILENAME)} ({len(test_retry_candidates)} candidati)")
        print("="*60)
        
        if len(entries) > TEST_BATCH_SIZE:
            choice = input(f"\nVuoi continuare con i rimanenti {len(entries) - TEST_BATCH_SIZE} DOI? (s/n): ").strip().lower()
            
            if choice == 's' or choice == 'si' or choice == 'y' or choice == 'yes':
                # FASE 2: Elaborazione completa
                logging.info("="*60)
                logging.info("FASE 2: ELABORAZIONE COMPLETA")
                logging.info("="*60)
                
                # Continua dall'ultimo DOI elaborato
                remaining_results, remaining_metadata, remaining_not_found, remaining_success, remaining_failure, remaining_retry_candidates = process_batch(
                    entries, TEST_BATCH_SIZE, len(entries)
                )

                
                # Combina i risultati
                all_results = test_results + remaining_results
                all_metadata = test_metadata + remaining_metadata
                all_not_found = test_not_found + remaining_not_found
                all_retry_candidates = test_retry_candidates + remaining_retry_candidates
                total_success = test_success + remaining_success
                total_failure = test_failure + remaining_failure
                
                final_summary = {
                    'total_dois': len(entries),
                    'opencitation_success': total_success,
                    'opencitation_failure': total_failure,
                    'success_percentage': round((total_success / len(entries)) * 100, 2) if entries else 0,
                    'retry_candidates': len(all_retry_candidates)
                }
                
                # Salva i risultati finali
                save_cache()
                save_results(all_results, all_metadata, all_not_found, final_summary, all_retry_candidates)
                
                logging.info("="*60)
                logging.info("ELABORAZIONE COMPLETATA!")
                logging.info(f"Totale DOI elaborati: {len(entries)}")
                logging.info(f"Successi: {total_success}")
                logging.info(f"Fallimenti: {total_failure}")
                logging.info(f"Candidati per retry: {len(all_retry_candidates)}")
                logging.info(f"Percentuale di successo: {final_summary['success_percentage']}%")
                logging.info(f"File salvati in: {OUTPUT_DIR}")
                logging.info("="*60)
                
                if all_retry_candidates:
                    print(f"\nCi sono {len(all_retry_candidates)} DOI candidati per retry.")
                    print("Puoi rieseguire lo script per riprovare automaticamente questi DOI.")
                    
            else:
                logging.info("Elaborazione interrotta dall'utente dopo il test.")
        else:
            logging.info("Test completato. Tutti i DOI sono stati elaborati.")
            if test_retry_candidates:
                print(f"\nCi sono {len(test_retry_candidates)} DOI candidati per retry.")
                print("Puoi rieseguire lo script per riprovare automaticamente questi DOI.")
    
    except FileNotFoundError as e:
        logging.error(f"File {INPUT_FILENAME} non trovato: {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Errore nella decodifica del file JSON: {e}")
    except Exception as e:
        logging.exception("Errore imprevisto")
        save_cache()  # Salva la cache anche in caso di errore

if __name__ == '__main__':
    print("Avvio elaborazione OpenCitations...")
    main()
    print("Programma terminato.")