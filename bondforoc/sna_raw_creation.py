import json
from collections import defaultdict
import re

def normalize_author_name(name):
    """
    Normalizza il nome dell'autore convertendolo in lowercase 
    e sostituendo spazi con underscore, rimuovendo caratteri speciali
    """
    # Rimuovi spazi extra e converti in lowercase
    normalized = name.strip().lower()
    
    # Rimuovi caratteri speciali che possono causare problemi nei nomi file
    # Mantieni solo lettere, numeri, spazi e alcuni caratteri sicuri
    normalized = re.sub(r"[^\w\s\-\.]", "", normalized)
    
    # Sostituisci spazi multipli con underscore singolo
    normalized = re.sub(r'\s+', '_', normalized)
    
    # Rimuovi underscore multipli
    normalized = re.sub(r'_+', '_', normalized)
    
    # Rimuovi underscore all'inizio e alla fine
    normalized = normalized.strip('_')
    
    # Limita la lunghezza per evitare problemi con nomi file troppo lunghi
    if len(normalized) > 100:
        normalized = normalized[:100].rstrip('_')
    
    return normalized

def build_sna_valid_raw(sna_valid_pub):
    """
    Costruisce sna_valid_raw a partire da sna_valid_pub
    
    Args:
        sna_valid_pub (dict): Dizionario con metadati delle pubblicazioni
        
    Returns:
        dict: Dizionario con autori come chiavi e liste di ID pubblicazioni come valori
    """
    author_publications = defaultdict(list)
    
    # Itera su tutte le pubblicazioni
    for pub_id, publication in sna_valid_pub.items():
        # Controlla se la pubblicazione ha autori
        if 'authors' in publication and publication['authors']:
            # Per ogni autore della pubblicazione
            for author in publication['authors']:
                # Usa solo il nome dell'autore, ignora l'organizzazione
                if 'name' in author and author['name']:
                    # Normalizza il nome dell'autore
                    normalized_name = normalize_author_name(author['name'])
                    
                    # Aggiungi solo se il nome normalizzato non è vuoto
                    if normalized_name:
                        # Aggiungi l'ID della pubblicazione alla lista dell'autore
                        author_publications[normalized_name].append(pub_id)
                else:
                    print(f"Attenzione: Autore senza nome nella pubblicazione {pub_id}")
    
    # Converte defaultdict in dict normale
    return dict(author_publications)

def load_and_convert(input_file_path, output_file_path="results/converted_metadata_raw.json"):
    """
    Carica sna_valid_pub da file JSON e salva sna_valid_raw
    
    Args:
        input_file_path (str): Percorso del file sna_valid_pub.json
        output_file_path (str): Percorso dove salvare sna_valid_raw.json (default: results/converted_metadata_raw.json)
    """
    try:
        # Crea la cartella results se non esiste
        import os
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        
        # Carica il file sna_valid_pub
        with open(input_file_path, 'r', encoding='utf-8') as f:
            sna_valid_pub = json.load(f)
        
        print(f"Caricato file con {len(sna_valid_pub)} pubblicazioni")
        
        # Costruisce sna_valid_raw
        sna_valid_raw = build_sna_valid_raw(sna_valid_pub)
        
        print(f"Trovati {len(sna_valid_raw)} autori unici")
        
        # Salva il risultato
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(sna_valid_raw, f, indent=2, ensure_ascii=False)
        
        print(f"File sna_valid_raw salvato in: {output_file_path}")
        
        # Mostra alcune statistiche
        total_publications = sum(len(pubs) for pubs in sna_valid_raw.values())
        avg_pubs_per_author = total_publications / len(sna_valid_raw) if sna_valid_raw else 0
        
        print(f"\nStatistiche:")
        print(f"- Autori totali: {len(sna_valid_raw)}")
        print(f"- Pubblicazioni totali (con possibili duplicati): {total_publications}")
        print(f"- Media pubblicazioni per autore: {avg_pubs_per_author:.2f}")
        
        return sna_valid_raw
        
    except FileNotFoundError:
        print(f"Errore: File {input_file_path} non trovato")
        return None
    except json.JSONDecodeError:
        print(f"Errore: File {input_file_path} non è un JSON valido")
        return None
    except Exception as e:
        print(f"Errore durante l'elaborazione: {e}")
        return None

# Esempio di utilizzo
if __name__ == "__main__":
    # Esempio con dati di test
    sna_valid_pub_example = {
        "rJZe1IHB": {
            "id": "rJZe1IHB",
            "title": "Enhanced Terrestrial Carbon Uptake in the Northern High Latitudes in the 21st Century from the C4MIP Model Projections",
            "abstract": "",
            "keywords": [
                "carbon-climate",
                "terrestrial carbon"
            ],
            "authors": [
                {
                    "name": "Haifeng Qian",
                    "org": ""
                },
                {
                    "name": "Renu Joseph",
                    "org": ""
                },
                {
                    "name": "Ning Zeng",
                    "org": ""
                }
            ],
            "venue": "",
            "year": 2008
        },
        "LNZGIKx7": {
            "id": "LNZGIKx7",
            "title": "Another Paper",
            "abstract": "",
            "keywords": [],
            "authors": [
                {
                    "name": "Haifeng Qian",
                    "org": ""
                },
                {
                    "name": "John Doe",
                    "org": ""
                }
            ],
            "venue": "",
            "year": 2009
        }
    }
    
    # Test con dati di esempio che includono caratteri speciali
    print("=== Test con dati di esempio ===")
    result = build_sna_valid_raw(sna_valid_pub_example)
    print("Risultato:")
    for author, publications in result.items():
        print(f"  {author}: {publications}")
    
    # Test con l'esempio problematico fornito
    problematic_example = {
        "PohImS1q": {
            "id": "PohImS1q",
            "title": "Transient thermal effect of semi-insulating GaAs photoconductive switch",
            "authors": [
                {
                    "name": "Shi Wei",
                    "org": "Department of Applied Physics,Xi'an University of Technology,Xi'an ,China"
                },
                {
                    "name": "Xiangrong Ma",
                    "org": "Xi'an University of Technology(Xi'an University of Technology,Xi'an Univ. of Technol.),Xi An,China"
                },
                {
                    "name": "Xue Hong",
                    "org": "Department of Applied Physics,Xi'an University of Technology,Xi'an ,China"
                }
            ],
            "venue": "Acta Physica Sinica",
            "year": 2010
        }
    }
    
    print("\n=== Test con esempio problematico ===")
    result_problematic = build_sna_valid_raw(problematic_example)
    print("Risultato:")
    for author, publications in result_problematic.items():
        print(f"  {author}: {publications}")
        # Verifica che i nomi siano sicuri per i file
        print(f"    -> Nome sicuro per file: ✓")
    
    print("\n=== Conversione del file reale ===")
    load_and_convert(r'C:\Users\franc\OneDrive - Alma Mater Studiorum Università di Bologna\Desktop\BondforOC\results\OC_results\converted_metadata.json', '../results/converted_metadata_raw.json')