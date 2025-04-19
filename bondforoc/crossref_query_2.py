import csv
import json
import time
import os
import requests
import matplotlib.pyplot as plt
from typing import Dict, List, Optional, Tuple, Union, Any


def main():
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)
    
    input_file = r"data/Bondvalidation.json"  
    training_csv = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\training_set.csv"
    validation_csv = r"C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\validation_set.csv"
    output_plot = os.path.join(results_dir, "crossref_score_analysis.png")
    validation_output = "validation_results.csv"  
    validation_direct_output = os.path.join(results_dir, "validation_direct_results.csv")
    training_cache_file = os.path.join(results_dir, "crossref_training_cache.json")
    validation_cache_file = os.path.join(results_dir, "crossref_validation_cache.json")
    wrong_matches_output = os.path.join(results_dir, "wrong_matches_analysis.csv")
    
    use_cache = True
    create_cache = True
    do_direct_validation = False
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            input_json = json.load(f)
        
        print("Analisi del dataset di training per trovare il cutoff ottimale...")
        results, best_cutoff = process_json_and_training(
            input_json, 
            training_csv, 
            output_plot, 
            #max_keys=50,  # Limita per test, rimuovi o aumenta per l'analisi completa
            results_dir=results_dir,
            crossref_cache_file=training_cache_file,
            use_cache=use_cache
        )
        
        if create_cache:
            print("\nCreazione della cache per il validation set...")
            validation_cache = create_validation_cache(
                input_json,
                validation_csv,
                results_dir=results_dir,
                validation_cache_file=validation_cache_file
            )
        
        print("\nValutazione del validation set con il cutoff ottimale usando la cache...")
        cached_metrics = evaluate_validation_set(
            input_json,
            validation_csv,
            best_cutoff,
            validation_output,
            results_dir=results_dir,
            crossref_cache_file=validation_cache_file
        )
        
        if do_direct_validation:
            print("\nValutazione diretta del validation set (interrogazione diretta a Crossref)...")
            direct_metrics = evaluate_validation_set_direct(
                input_json,
                validation_csv,
                best_cutoff,
                validation_direct_output,
                results_dir=results_dir
            )
        
        print_summary(best_cutoff, cached_metrics)
        
        print("\nAnalisi dei wrong matches sopra il cutoff...")
        analyze_wrong_matches(results, best_cutoff, wrong_matches_output)
        
    except Exception as e:
        print(f"Si è verificato un errore: {e}")
        import traceback
        traceback.print_exc()


def print_summary(best_cutoff: float, cached_metrics: Dict) -> None:
    """Stampa un riepilogo dei risultati della validazione."""
    print("\nRiassunto finale:")
    print(f"Cutoff ottimale sul training set: {best_cutoff:.2f}")
    
    if cached_metrics and "accuracy" in cached_metrics:
        print(f"\nPerformance sul validation set (usando cache):")
        print(f"  Accuratezza: {cached_metrics['accuracy']:.4f}")
        print(f"  Precisione: {cached_metrics['precision']:.4f}")
        print(f"  Recall: {cached_metrics['recall']:.4f}")
        print(f"  F1 Score: {cached_metrics['f1']:.4f}")


def query_with_retry(query_function, max_retries=3, timeout=5, *args, **kwargs) -> Dict:
    """Esegue una query con tentativi di ripetizione in caso di errore."""
    for attempt in range(max_retries):
        try:
            return query_function(*args, **kwargs)
        except Exception as e:
            print(f"Errore durante il tentativo {attempt + 1}: {e}")
            if attempt < max_retries - 1:  
                time.sleep(timeout)
    raise Exception("Numero massimo di tentativi superato")


def query_crossref(title: str, year: int) -> Dict:
    """Interroga l'API di CrossRef per un titolo e anno specifici."""
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "filter": f"from-pub-date:{year},until-pub-date:{year + 1}",
        "rows": 1  
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def extract_crossref_score(item: Dict) -> float:
    """Estrae lo score di rilevanza da un risultato CrossRef."""
    return item.get('score', 0)


def extract_crossref_metadata(item: Dict) -> Dict:
    """Estrae i metadati da un risultato CrossRef."""
    metadata = {
        "title": "",
        "year": None,
        "authors": [],
        "venue": ""
    }
    
    if "title" in item and isinstance(item["title"], list) and len(item["title"]) > 0:
        metadata["title"] = item["title"][0]
    
    if "published" in item and "date-parts" in item["published"]:
        date_parts = item["published"]["date-parts"]
        if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
            metadata["year"] = date_parts[0][0]
    
    if "author" in item and isinstance(item["author"], list):
        for author in item["author"]:
            author_name = []
            if "given" in author:
                author_name.append(author["given"])
            if "family" in author:
                author_name.append(author["family"])
            
            if author_name:
                metadata["authors"].append(" ".join(author_name))
    
    if "container-title" in item and isinstance(item["container-title"], list) and len(item["container-title"]) > 0:
        metadata["venue"] = item["container-title"][0]
    elif "publisher" in item:
        metadata["venue"] = item["publisher"]
    
    return metadata


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


def save_crossref_cache(cache: Dict, filename: str) -> None:
    """Salva i risultati delle query Crossref in un file JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)


def load_crossref_cache(filename: str) -> Dict:
    """Carica i risultati delle query Crossref da un file JSON."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_csv_data(file_path: str) -> Tuple[List[Dict], List[str]]:
    """Legge un file CSV e restituisce i dati e le intestazioni."""
    with open(file_path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        delimiter = ";" if ";" in first_line else ","
        f.seek(0)
        
        reader = csv.reader(f, delimiter=delimiter)
        headers = next(reader)
        
        indices = {}
        for i, header in enumerate(headers):
            header_lower = header.lower()
            if header_lower == "key":
                indices["key"] = i
            elif header_lower == "title":
                indices["title"] = i
            elif header_lower == "doi":
                indices["doi"] = i
            elif header_lower == "id_on_crossref":
                indices["id_on_crossref"] = i
        
        required_columns = ["key", "title", "doi", "id_on_crossref"]
        missing_columns = [col for col in required_columns if col not in indices]
        if missing_columns:
            raise ValueError(f"Colonne mancanti nel file CSV: {missing_columns}")
        
        data = []
        for row in reader:
            if len(row) >= max(indices.values()) + 1:
                data.append({
                    "Key": row[indices["key"]],
                    "title": row[indices["title"]],
                    "DOI": row[indices["doi"]],
                    "ID_on_Crossref": row[indices["id_on_crossref"]].lower() == "true"
                })
        
        return data, headers


def process_json_and_training(
    input_json: Dict, 
    training_csv: str, 
    output_plot: str, 
    max_keys: Optional[int] = None, 
    results_dir: str = "results", 
    crossref_cache_file: Optional[str] = None, 
    use_cache: bool = True
) -> Tuple[List[Dict], float]:
    os.makedirs(results_dir, exist_ok=True)
    
    crossref_cache = {}
    if crossref_cache_file and use_cache:
        crossref_cache = load_crossref_cache(crossref_cache_file)
        print(f"Cache Crossref caricata con {len(crossref_cache)} elementi")
    
    training_data, _ = read_csv_data(training_csv)
    print(f"Righe lette dal CSV: {len(training_data)}")
    
    results = []
    cache_updates = False
    
    rows_to_process = training_data
    if max_keys and max_keys < len(training_data):
        rows_to_process = training_data[:max_keys]
    
    print(f"Elaborazione di {len(rows_to_process)} righe dal CSV di training")
    
    for row in rows_to_process:
        key = row["Key"]
        title = row["title"]
        gold_doi = row["DOI"]
        on_crossref = row["ID_on_Crossref"]
        
        year, updated_title = get_info_from_json(input_json, key, title)
        
        if updated_title:
            result = process_record(
                key, updated_title, gold_doi, on_crossref, year, 
                crossref_cache, use_cache
            )
            if result["cache_updated"]:
                cache_updates = True
            results.append(result["data"])
        else:
            print(f"Titolo mancante per la chiave {key}, impossibile interrogare CrossRef")
        
    if crossref_cache_file and cache_updates:
        save_crossref_cache(crossref_cache, crossref_cache_file)
        print(f"Cache Crossref salvata con {len(crossref_cache)} elementi")

    best_cutoff = create_score_analysis_plot(results, output_plot, results_dir)
    
    return results, best_cutoff


def get_info_from_json(input_json: Dict, key: str, title: str) -> Tuple[int, str]:
    """Estrae l'anno e aggiorna il titolo dal file JSON."""
    year = 2020  # Anno predefinito
    updated_title = title  # titolo del CSV
    
    if key in input_json:
        json_item = input_json[key]
        if "title" in json_item and json_item["title"]:
            updated_title = json_item["title"]
        if "year" in json_item:
            year = json_item["year"]
    
    return year, updated_title


def process_record(
    key: str, 
    title: str, 
    gold_doi: str, 
    on_crossref: bool, 
    year: int, 
    crossref_cache: Dict, 
    use_cache: bool
) -> Dict:
    cache_key = f"{title}_{year}"
    cache_updated = False
    
    if cache_key in crossref_cache and use_cache:
        print(f"Usando risultato dalla cache per '{title}'")
        cr_result = crossref_cache[cache_key]
        cr_doi = cr_result.get("doi")
        cr_score = cr_result.get("score", 0)
        cr_metadata = cr_result.get("metadata", {})
    else:
        print(f"Interrogazione di CrossRef per il titolo '{title}' e anno '{year}'...")
        try:
            crossref_results = query_with_retry(query_crossref, title=title, year=year)
            
            cr_items = crossref_results.get("message", {}).get("items", [])
            if cr_items:
                cr_item = cr_items[0]  
                cr_doi = cr_item.get("DOI")
                cr_score = extract_crossref_score(cr_item)
                cr_metadata = extract_crossref_metadata(cr_item)
            else:
                print(f"Nessun risultato trovato su CrossRef per {key}")
                cr_doi = None
                cr_score = 0
                cr_metadata = {}
            
            crossref_cache[cache_key] = {
                "doi": cr_doi,
                "score": cr_score,
                "metadata": cr_metadata,
                "key": key  
            }
            cache_updated = True
        except Exception as e:
            print(f"Errore nell'interrogazione per la chiave {key}: {e}")
            cr_doi = None
            cr_score = 0
            cr_metadata = {}
    
    norm_gold_doi = normalize_doi(gold_doi)
    norm_cr_doi = normalize_doi(cr_doi)
    
    is_correct = (norm_gold_doi == norm_cr_doi) if norm_cr_doi is not None else False
    
    return {
        "data": {
            "key": key,
            "title": title,
            "gold_doi": gold_doi,
            "crossref_doi": cr_doi,
            "score": cr_score,
            "is_correct": is_correct,
            "on_crossref": on_crossref,
            "cr_title": cr_metadata.get("title", ""),
            "cr_year": cr_metadata.get("year", ""),
            "cr_authors": cr_metadata.get("authors", []),
            "cr_venue": cr_metadata.get("venue", "")
        },
        "cache_updated": cache_updated
    }


def create_score_analysis_plot(results: List[Dict], output_plot: str, results_dir: str = "results") -> Optional[float]:
    """Crea lo scatterplot di analisi e trova il cutoff ottimale."""
    if not results:
        print("Nessun risultato da analizzare")
        return None
    
    os.makedirs(results_dir, exist_ok=True)
    
    on_crossref_true = {'correct': [], 'wrong': []}
    on_crossref_false = {'correct': [], 'wrong': []}
    
    for result in results:
        if result["on_crossref"]:
            if result["is_correct"]:
                on_crossref_true['correct'].append(result["score"])
            else:
                on_crossref_true['wrong'].append(result["score"])
        else:
            if result["is_correct"]:
                on_crossref_false['correct'].append(result["score"])
            else:
                on_crossref_false['wrong'].append(result["score"])
    
    plt.figure(figsize=(12, 8))
    
    if on_crossref_true['correct']:
        plt.scatter(on_crossref_true['correct'], 
                   [1] * len(on_crossref_true['correct']), 
                   color='green', 
                   marker='o', 
                   label='Present on Crossref - Correct match', 
                   alpha=0.7)
    
    if on_crossref_true['wrong']:
        plt.scatter(on_crossref_true['wrong'], 
                   [0] * len(on_crossref_true['wrong']), 
                   color='red', 
                   marker='o', 
                   label='Present on Crossref - Wrong match', 
                   alpha=0.7)
    
    if on_crossref_false['correct']:
        plt.scatter(on_crossref_false['correct'], 
                   [1] * len(on_crossref_false['correct']), 
                   color='blue', 
                   marker='x', 
                   label='Not present on Crossref - Correct match', 
                   alpha=0.7)
    
    if on_crossref_false['wrong']:
        plt.scatter(on_crossref_false['wrong'], 
                   [0] * len(on_crossref_false['wrong']), 
                   color='orange', 
                   marker='x', 
                   label='Not present on Crossref - Wrong match', 
                   alpha=0.7)
    
    all_scores = [r["score"] for r in results]
    
    if all_scores:
        potential_cutoffs = sorted(set(all_scores))
        best_cutoff = 0
        best_accuracy = 0
        best_metrics = {}
        
        cutoff_metrics = []
        for cutoff in potential_cutoffs:
            metrics = calculate_metrics_at_cutoff(results, cutoff)
            cutoff_metrics.append(metrics)
            
            if metrics["accuracy"] > best_accuracy:
                best_accuracy = metrics["accuracy"]
                best_cutoff = cutoff
                best_metrics = metrics
        
        save_cutoff_metrics(cutoff_metrics, results_dir)
        
        plt.axvline(x=best_cutoff, color='purple', linestyle='--', 
                   label=f'Optimal cutoff: {best_cutoff:.2f} (Accuracy: {best_accuracy:.2f})')
        
        print(f"Cutoff ottimale: {best_cutoff:.2f}")
        print(f"Accuratezza: {best_accuracy:.2f}")
        print(f"Precisione: {best_metrics['precision']:.2f}")
        print(f"Recall: {best_metrics['recall']:.2f}")
        print(f"F1 Score: {best_metrics['f1']:.2f}")
    
    plt.title('Crossref Score vs Correct DOI Match')
    plt.xlabel('Crossref Score')
    plt.ylabel('Is Match Correct (1=Yes, 0=No)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    
    plt.savefig(output_plot)
    print(f"Grafico salvato come {output_plot}")
    
    return best_cutoff if all_scores else None


def calculate_metrics_at_cutoff(results: List[Dict], cutoff: float) -> Dict:
    """Calcola le metriche di performance per un dato cutoff."""
    tp = sum(1 for r in results if r["score"] >= cutoff and r["is_correct"])
    fp = sum(1 for r in results if r["score"] >= cutoff and not r["is_correct"])
    tn = sum(1 for r in results if r["score"] < cutoff and not r["is_correct"])
    fn = sum(1 for r in results if r["score"] < cutoff and r["is_correct"])
    
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "cutoff": cutoff,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }


def save_cutoff_metrics(cutoff_metrics: List[Dict], results_dir: str) -> None:
    """Salva le metriche per diversi cutoff in un file CSV."""
    metrics_file = os.path.join(results_dir, "crossref_cutoff_analysis.csv")
    with open(metrics_file, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["cutoff", "tp", "fp", "tn", "fn", "accuracy", "precision", "recall", "f1"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cutoff_metrics)
    print(f"Metriche per diversi cutoff salvate in {metrics_file}")


def create_validation_cache(
    input_json: Dict, 
    validation_csv: str, 
    results_dir: str = "results", 
    validation_cache_file: Optional[str] = None
) -> Dict:
    """Crea o aggiorna la cache per il validation set."""
    os.makedirs(results_dir, exist_ok=True)
    
    validation_cache = {}
    if validation_cache_file and os.path.exists(validation_cache_file):
        validation_cache = load_crossref_cache(validation_cache_file)
        print(f"Cache di validazione caricata con {len(validation_cache)} elementi")
    
    validation_data, _ = read_csv_data(validation_csv)
    print(f"Lette {len(validation_data)} righe dal file di validazione")
    
    cache_updates = False
    
    for row in validation_data:
        key = row["Key"]
        title = row["title"]
        
        year,updated_title = get_info_from_json(input_json, key, title)
        
        if updated_title:
            
            cache_key = f"{title}_{year}"
            
            if cache_key not in validation_cache:
                try:
                    crossref_results = query_with_retry(query_crossref, title=title, year=year)
                    
                    cr_items = crossref_results.get("message", {}).get("items", [])
                    if cr_items:
                        cr_item = cr_items[0]
                        cr_doi = cr_item.get("DOI")
                        cr_score = extract_crossref_score(cr_item)
                        cr_metadata = extract_crossref_metadata(cr_item)
                        
                        validation_cache[cache_key] = {
                            "doi": cr_doi,
                            "score": cr_score,
                            "metadata": cr_metadata,
                            "key": key
                        }
                    else:
                        validation_cache[cache_key] = {
                            "doi": None,
                            "score": 0,
                            "metadata": {},
                            "key": key
                        }
                    
                    cache_updates = True
                except Exception as e:
                    print(f"Errore nell'interrogazione per la chiave {key}: {e}")
                    validation_cache[cache_key] = {
                        "doi": None,
                        "score": 0,
                        "metadata": {},
                        "key": key,
                        "error": str(e)
                    }
                    cache_updates = True
            else:
                print(f"Elemento già presente nella cache per '{title}'")
        else:
            print(f"Titolo mancante per la chiave {key}")
    
    if validation_cache_file and cache_updates:
        save_crossref_cache(validation_cache, validation_cache_file)
        print(f"Cache di validazione salvata con {len(validation_cache)} elementi")
    
    return validation_cache


def evaluate_validation_set(
    input_json: Dict, 
    validation_csv: str, 
    cutoff: float, 
    output_csv: str, 
    results_dir: str = "results", 
    crossref_cache_file: Optional[str] = None
) -> Dict:
    os.makedirs(results_dir, exist_ok=True)
    
    output_csv = os.path.join(results_dir, output_csv)
    
    crossref_cache = {}
    if crossref_cache_file:
        crossref_cache = load_crossref_cache(crossref_cache_file)
        print(f"Cache di validazione caricata con {len(crossref_cache)} elementi")
    
    validation_data, _ = read_csv_data(validation_csv)
    print(f"Lette {len(validation_data)} righe dal file di validazione")
    
    results = []
    validation_metrics = {
        "total": len(validation_data),
        "with_crossref_result": 0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0
    }
    
    for row in validation_data:
        key = row["Key"]
        title = row["title"]
        gold_doi = row["DOI"]
        on_crossref = row["ID_on_Crossref"]
        
        year, updated_title = get_info_from_json(input_json, key, title)
        
        if title:
            cache_key = f"{title}_{year}"
            
            if cache_key in crossref_cache:
                print(f"Usando risultato dalla cache per '{title}'")
                cr_result = crossref_cache[cache_key]
                cr_doi = cr_result.get("doi")
                cr_score = cr_result.get("score", 0)
                cr_metadata = cr_result.get("metadata", {})
                
                if cr_doi is not None:
                    validation_metrics["with_crossref_result"] += 1
                    
                    norm_gold_doi = normalize_doi(gold_doi)
                    norm_cr_doi = normalize_doi(cr_doi)
                    
                    is_correct = (norm_gold_doi == norm_cr_doi)
                    
                    exceeds_cutoff = cr_score >= cutoff
                    accepted_doi = cr_doi if exceeds_cutoff else None
                    
                    if is_correct and exceeds_cutoff:
                        validation_metrics["true_positives"] += 1
                    elif not is_correct and exceeds_cutoff:
                        validation_metrics["false_positives"] += 1
                    elif not is_correct and not exceeds_cutoff:
                        validation_metrics["true_negatives"] += 1
                    elif is_correct and not exceeds_cutoff:
                        validation_metrics["false_negatives"] += 1
                    
                    results.append({
                        "Key": key,
                        "title": title,
                        "gold_doi": gold_doi,
                        "crossref_doi": cr_doi,
                        "score": cr_score,
                        "is_correct": is_correct,
                        "exceeds_cutoff": exceeds_cutoff,
                        "accepted_doi": accepted_doi,
                        "on_crossref": on_crossref,
                        "cr_title": cr_metadata.get("title", ""),
                        "cr_year": cr_metadata.get("year", ""),
                        "cr_authors": ", ".join(cr_metadata.get("authors", [])),
                        "cr_venue": cr_metadata.get("venue", "")
                    })
                else:
                    print(f"Nessun risultato da Crossref nella cache per {key}")
                    results.append({
                        "Key": key,
                        "title": title,
                        "gold_doi": gold_doi,
                        "crossref_doi": None,
                        "score": 0,
                        "is_correct": False,
                        "exceeds_cutoff": False,
                        "accepted_doi": None,
                        "on_crossref": on_crossref,
                        "error": "Nessun risultato nella cache",
                        "cr_title": "",
                        "cr_year": "",
                        "cr_authors": "",
                        "cr_venue": ""
                    })
            else:
                print(f"Chiave {cache_key} non trovata nella cache, saltando...")
                results.append({
                    "Key": key,
                    "title": title,
                    "gold_doi": gold_doi,
                    "crossref_doi": None,
                    "score": 0,
                    "is_correct": False,
                    "exceeds_cutoff": False,
                    "accepted_doi": None,
                    "on_crossref": on_crossref,
                    "error": "Chiave non trovata nella cache",
                    "cr_title": "",
                    "cr_year": "",
                    "cr_authors": "",
                    "cr_venue": ""
                })
        else:
            print(f"Titolo mancante per la chiave {key}")
            results.append({
                "Key": key,
                "title": "",
                "gold_doi": gold_doi,
                "crossref_doi": None,
                "score": 0,
                "is_correct": False,
                "exceeds_cutoff": False,
                "accepted_doi": None,
                "on_crossref": on_crossref,
                "error": "Titolo mancante",
                "cr_title": "",
                "cr_year": "",
                "cr_authors": "",
                "cr_venue": ""
            })
    
    tp = validation_metrics["true_positives"]
    fp = validation_metrics["false_positives"]
    tn = validation_metrics["true_negatives"]
    fn = validation_metrics["false_negatives"]
    total_classified = tp + fp + tn + fn
    
    if total_classified > 0:
        validation_metrics["accuracy"] = (tp + tn) / total_classified
        validation_metrics["precision"] = tp / (tp + fp) if (tp + fp) > 0 else 0
        validation_metrics["recall"] = tp / (tp + fn) if (tp + fn) > 0 else 0
        validation_metrics["f1"] = 2 * (validation_metrics["precision"] * validation_metrics["recall"]) / (validation_metrics["precision"] + validation_metrics["recall"]) if (validation_metrics["precision"] + validation_metrics["recall"]) > 0 else 0
    
    print("\nMetriche di validazione:")
    print(f"Totale elementi: {validation_metrics['total']}")
    print(f"Elementi con risultato Crossref: {validation_metrics['with_crossref_result']}")
    print(f"Cutoff applicato: {cutoff}")
    if total_classified > 0:
        print(f"Accuratezza: {validation_metrics['accuracy']:.4f}")
        print(f"Precisione: {validation_metrics['precision']:.4f}")
        print(f"Recall: {validation_metrics['recall']:.4f}")
        print(f"F1 Score: {validation_metrics['f1']:.4f}")
    
    print("\nMatrice di confusione:")
    print(f"VP: {tp} | FP: {fp}")
    print(f"FN: {fn} | VN: {tn}")
    
    save_validation_results(results, output_csv, results_dir, validation_metrics)
    
    return validation_metrics

def save_validation_results(results: List[Dict], output_csv: str, results_dir: str, validation_metrics: Dict) -> None:
    """Salva i risultati della validazione in CSV e le metriche in JSON."""
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["Key", "title", "gold_doi", "crossref_doi", "score", "is_correct", 
                     "exceeds_cutoff", "accepted_doi", "on_crossref", "error", 
                     "cr_title", "cr_year", "cr_authors", "cr_venue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nRisultati salvati in {output_csv}")
    
    metrics_file = os.path.join(results_dir, "validation_metrics.json")
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(validation_metrics, f, ensure_ascii=False, indent=4)
    
    print(f"Metriche salvate in {metrics_file}")

def analyze_wrong_matches(results, cutoff, output_csv):
    wrong_matches = [r for r in results if r["score"] >= cutoff and not r["is_correct"] and r["on_crossref"]]
    
    if not wrong_matches:
        print("Nessun wrong match sopra il cutoff trovato.")
        return
    
    print(f"Trovati {len(wrong_matches)} wrong matches sopra il cutoff.")

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["key", "title", "gold_doi", "crossref_doi", "score", "on_crossref", 
                        "cr_title", "cr_year", "cr_authors", "cr_venue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for match in wrong_matches:
            writer.writerow({
                "key": match["key"],
                "title": match["title"],
                "gold_doi": match["gold_doi"],
                "crossref_doi": match["crossref_doi"],
                "score": match["score"],
                "on_crossref": match["on_crossref"],
                "cr_title": match["cr_title"],
                "cr_year": match["cr_year"],
                "cr_authors": match["cr_authors"],
                "cr_venue": match["cr_venue"]
            })

    
    print(f"Analisi dei wrong matches salvata in {output_csv}")

def evaluate_validation_set_direct(
    input_json: Dict, 
    validation_csv: str, 
    cutoff: float, 
    output_csv: str, 
    results_dir: str = "results"
) -> Dict:
    """
    Valuta un set di validazione facendo interrogazioni dirette a Crossref (senza cache).
    Questa è una versione opzionale per interrogazioni dirette quando serve aggiornare i dati.
    """
    os.makedirs(results_dir, exist_ok=True)
    
    output_csv = os.path.join(results_dir, output_csv)
    
    validation_data, _ = read_csv_data(validation_csv)
    print(f"Lette {len(validation_data)} righe dal file di validazione per interrogazione diretta")
    
    results = []
    validation_metrics = {
        "total": len(validation_data),
        "with_crossref_result": 0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0
    }
    
    for row in validation_data:
        key = row["Key"]
        title = row["title"]
        gold_doi = row["DOI"]
        on_crossref = row["ID_on_Crossref"]
        
        year, updated_title = get_info_from_json(input_json, key, title)
        
        if updated_title:
            try:
                print(f"Interrogazione diretta di CrossRef per '{title}'...")
                crossref_results = query_with_retry(query_crossref, title=title, year=year)
                
                cr_items = crossref_results.get("message", {}).get("items", [])
                if cr_items:
                    validation_metrics["with_crossref_result"] += 1
                    
                    cr_item = cr_items[0]
                    cr_doi = cr_item.get("DOI")
                    cr_score = extract_crossref_score(cr_item)
                    cr_metadata = extract_crossref_metadata(cr_item)
                    
                    norm_gold_doi = normalize_doi(gold_doi)
                    norm_cr_doi = normalize_doi(cr_doi)
                    
                    is_correct = (norm_gold_doi == norm_cr_doi)
                    
                    exceeds_cutoff = cr_score >= cutoff
                    accepted_doi = cr_doi if exceeds_cutoff else None
                    
                    if is_correct and exceeds_cutoff:
                        validation_metrics["true_positives"] += 1
                    elif not is_correct and exceeds_cutoff:
                        validation_metrics["false_positives"] += 1
                    elif not is_correct and not exceeds_cutoff:
                        validation_metrics["true_negatives"] += 1
                    elif is_correct and not exceeds_cutoff:
                        validation_metrics["false_negatives"] += 1
                    
                    results.append({
                        "Key": key,
                        "title": title,
                        "gold_doi": gold_doi,
                        "crossref_doi": cr_doi,
                        "score": cr_score,
                        "is_correct": is_correct,
                        "exceeds_cutoff": exceeds_cutoff,
                        "accepted_doi": accepted_doi,
                        "on_crossref": on_crossref,
                        "cr_title": cr_metadata.get("title", ""),
                        "cr_year": cr_metadata.get("year", ""),
                        "cr_authors": ", ".join(cr_metadata.get("authors", [])),
                        "cr_venue": cr_metadata.get("venue", "")
                    })
                else:
                    print(f"Nessun risultato da Crossref per {key}")
                    results.append({
                        "Key": key,
                        "title": title,
                        "gold_doi": gold_doi,
                        "crossref_doi": None,
                        "score": 0,
                        "is_correct": False,
                        "exceeds_cutoff": False,
                        "accepted_doi": None,
                        "on_crossref": on_crossref,
                        "error": "Nessun risultato da Crossref",
                        "cr_title": "",
                        "cr_year": "",
                        "cr_authors": "",
                        "cr_venue": ""
                    })
            except Exception as e:
                print(f"Errore nell'interrogazione diretta per la chiave {key}: {e}")
                results.append({
                    "Key": key,
                    "title": title,
                    "gold_doi": gold_doi,
                    "crossref_doi": None,
                    "score": 0,
                    "is_correct": False,
                    "exceeds_cutoff": False,
                    "accepted_doi": None,
                    "on_crossref": on_crossref,
                    "error": str(e),
                    "cr_title": "",
                    "cr_year": "",
                    "cr_authors": "",
                    "cr_venue": ""
                })
        else:
            print(f"Titolo mancante per la chiave {key}")
            results.append({
                "Key": key,
                "title": "",
                "gold_doi": gold_doi,
                "crossref_doi": None,
                "score": 0,
                "is_correct": False,
                "exceeds_cutoff": False,
                "accepted_doi": None,
                "on_crossref": on_crossref,
                "error": "Titolo mancante",
                "cr_title": "",
                "cr_year": "",
                "cr_authors": "",
                "cr_venue": ""
            })
    
    tp = validation_metrics["true_positives"]
    fp = validation_metrics["false_positives"]
    tn = validation_metrics["true_negatives"]
    fn = validation_metrics["false_negatives"]
    total_classified = tp + fp + tn + fn
    
    if total_classified > 0:
        validation_metrics["accuracy"] = (tp + tn) / total_classified
        validation_metrics["precision"] = tp / (tp + fp) if (tp + fp) > 0 else 0
        validation_metrics["recall"] = tp / (tp + fn) if (tp + fn) > 0 else 0
        validation_metrics["f1"] = 2 * (validation_metrics["precision"] * validation_metrics["recall"]) / (validation_metrics["precision"] + validation_metrics["recall"]) if (validation_metrics["precision"] + validation_metrics["recall"]) > 0 else 0
    
    print("\nMetriche di validazione (interrogazione diretta):")
    print(f"Totale elementi: {validation_metrics['total']}")
    print(f"Elementi con risultato Crossref: {validation_metrics['with_crossref_result']}")
    print(f"Cutoff applicato: {cutoff}")
    if total_classified > 0:
        print(f"Accuratezza: {validation_metrics['accuracy']:.4f}")
        print(f"Precisione: {validation_metrics['precision']:.4f}")
        print(f"Recall: {validation_metrics['recall']:.4f}")
        print(f"F1 Score: {validation_metrics['f1']:.4f}")
    
    print("\nMatrice di confusione (interrogazione diretta):")
    print(f"VP: {tp} | FP: {fp}")
    print(f"FN: {fn} | VN: {tn}")
    
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["Key", "title", "gold_doi", "crossref_doi", "score", "is_correct", 
                     "exceeds_cutoff", "accepted_doi", "on_crossref", "error", 
                     "cr_title", "cr_year", "cr_authors", "cr_venue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nRisultati di interrogazione diretta salvati in {output_csv}")
    
    metrics_file = os.path.join(results_dir, "validation_direct_metrics.json")
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(validation_metrics, f, ensure_ascii=False, indent=4)
    
    print(f"Metriche di interrogazione diretta salvate in {metrics_file}")
    
    return validation_metrics

if __name__ == "__main__":
    main()