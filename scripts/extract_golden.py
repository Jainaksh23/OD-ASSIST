import json
from db.db import SessionLocal
from db.models import QueryLog

def extract_golden_dataset():
    db = SessionLocal()
    logs = db.query(QueryLog).filter(QueryLog.confidence == 'high').all()
    
    dataset = []
    seen = set()
    for log in logs:
        if log.query not in seen and len(dataset) < 40:
            dataset.append({
                "question": log.query,
                "expected_answer": "",
                "expected_source_ids": [],
            })
            seen.add(log.query)
            
    with open("eval/golden_dataset.json", "w") as f:
        json.dump(dataset, f, indent=4)
        
    print(f"Extracted {len(dataset)} unique queries to eval/golden_dataset.json")

if __name__ == "__main__":
    import os
    if not os.path.exists("eval"):
        os.makedirs("eval")
    extract_golden_dataset()
