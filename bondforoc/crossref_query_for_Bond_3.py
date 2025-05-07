import json
import os
import time
import csv
from typing import Dict, List, Optional, Tuple

from crossref_query_2 import (
    query_with_retry,
    query_crossref,
    extract_crossref_score,
    extract_crossref_metadata,
    validate_crossref_match,
    normalize_doi
)

def crossref_with_metavalidation_pipeline(
    input_json_path: str,
    cutoff: float,
    output_dir: str = "results",
    output_file: str = "validated_keys_dois.csv"
) -> None:
    """
    Pipeline for validating resources with Crossref and extracting their DOIs.
    Saves a CSV with keys of validated resources and their associated DOIs.
    
    Args:
        input_json_path: Path to the Bondvalidation.json file
        cutoff: Manual cutoff for Crossref score
        output_dir: Directory to save results
        output_file: Filename for the output CSV
    """
    # Create output directory if it doesn't exist
    #os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file)
    
    with open(input_json_path, "r", encoding="utf-8") as f:
        input_json = json.load(f)
    
    validated_items = []
    
    stats = {
        "total": len(input_json),
        "validated": 0,
        "rejected": 0,
        "errors": 0
    }
    
    print(f"Processing {len(input_json)} items with cutoff {cutoff}...")
    
    for key, item in input_json.items():
        print(f"Processing item {key}...")
        
        title = item.get("title", "")
        year = item.get("year", 2020)  
        
        if not title:
            print(f"  Skipping {key}: No title found")
            stats["rejected"] += 1
            continue
        
        try:
            print(f"  Querying Crossref for '{title}'...")
            crossref_results = query_with_retry(query_crossref, title=title, year=year)
            
            cr_items = crossref_results.get("message", {}).get("items", [])
            if not cr_items:
                print(f"  No Crossref results for '{title}'")
                stats["rejected"] += 1
                continue
            
            cr_item = cr_items[0]
            cr_doi = cr_item.get("DOI")
            cr_score = extract_crossref_score(cr_item)
            cr_metadata = extract_crossref_metadata(cr_item)

            normalized_doi = normalize_doi(cr_doi)

            
            print(f"  Crossref score: {cr_score}, DOI: {normalized_doi}")
            
            if cr_score < cutoff:
                print(f"  Rejected: Score {cr_score} below cutoff {cutoff}")
                stats["rejected"] += 1
                continue
            
            is_valid_match, validation_details = validate_crossref_match(
                item, cr_metadata, cr_metadata.get("year")
            )
            
            if not is_valid_match:
                print(f"  Rejected: Metadata validation failed")
                stats["rejected"] += 1
                continue
            
            print(f"  Validated: DOI {normalized_doi}")
            validated_items.append({
                "key": key,
                "doi": normalized_doi or cr_doi
            })
            stats["validated"] += 1
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  Error processing {key}: {e}")
            stats["errors"] += 1
    
    if validated_items:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["key", "doi"])
            writer.writeheader()
            writer.writerows(validated_items)
    
    print(f"\nProcessing complete. Results saved to {output_path}")
    print(f"Total items: {stats['total']}")
    print(f"Validated: {stats['validated']}")
    print(f"Rejected: {stats['rejected']}")
    print(f"Errors: {stats['errors']}")

if __name__ == "__main__":

    input_file = "data/Bondvalidation.json"
    manual_cutoff = 35.0  
    output_dir = "results/Bond_crossref_validated"
    
    crossref_with_metavalidation_pipeline(
        input_json_path=input_file,
        cutoff=manual_cutoff,
        output_dir=output_dir
    )