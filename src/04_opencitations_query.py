from flask import Flask, jsonify
import requests
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

OPENCITATION_META_API_URL = "https://opencitations.net/meta/api/v1/metadata/"
INPUT_FILENAME = r"C:\Users\franc\ANDiamo\output_final_batch.json"
NOT_FOUND_FILENAME = "final_batch_notfound.json"  # Nome del file per i DOI non trovati

# Configura il logging
logging.basicConfig(level=logging.INFO)

def check_doi_in_opencitation(doi):
    """Check if the DOI exists in OpenCitation Meta."""
    prefix = "doi:"  # Prefisso richiesto dall'API
    full_doi = f"{prefix}{doi}"
    try:
        response = requests.get(f"{OPENCITATION_META_API_URL}{full_doi}", timeout=10)
        if response.status_code == 200:
            return True
        else:
            logging.info(f"Received status code {response.status_code} for DOI {full_doi}")
            return False
    except requests.RequestException as e:
        logging.error(f"Error checking DOI {full_doi}: {e}")
        return False

@app.route('/check_opencitation', methods=['POST'])
def check_opencitation():
    try:
        with open(INPUT_FILENAME, 'r', encoding='utf-8') as file:
            entries = json.load(file)
    except FileNotFoundError:
        return jsonify({"error": f"File {INPUT_FILENAME} not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error decoding JSON file"}), 400

    results = []
    opencitation_success = 0
    opencitation_failure = 0
    not_found_dois = []  

    doi_list = [entry.get('doi') for entry in entries if entry.get('doi')]

    # Esegui richieste in parallelo
    with ThreadPoolExecutor(max_workers=5) as executor:  # Riduci max_workers se necessario
        future_to_doi = {executor.submit(check_doi_in_opencitation, doi): doi for doi in doi_list}

        for future in as_completed(future_to_doi):
            doi = future_to_doi[future]
            try:
                if future.result():
                    opencitation_success += 1
                    results.append({'doi': doi, 'status': 'found'})
                else:
                    opencitation_failure += 1
                    results.append({'doi': doi, 'status': 'not found'})
                    not_found_dois.append({'doi': doi})
            except Exception as e:
                logging.error(f"Error processing DOI {doi}: {e}")
                opencitation_failure += 1
                results.append({'doi': doi, 'status': 'error'})
                not_found_dois.append({'doi': doi})

    summary = {
        'opencitation_success': opencitation_success,
        'opencitation_failure': opencitation_failure
    }

    logging.info(json.dumps({'results': results, 'summary': summary}, indent=4))

    with open(NOT_FOUND_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(not_found_dois, f, indent=4)

    return jsonify({'results': results, 'summary': summary})

if __name__ == '__main__':
    app.run(debug=True)
