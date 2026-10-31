# resume_analyzer.py

import torch
import transformers
import huggingface_hub
import polars as pl
import pyarrow as pa
import datasets
from sentence_transformers import SentenceTransformer

#
def print_versions():
    print(f"PyTorch version: {torch.__version__}")
    print(f"Transformers version: {transformers.__version__}")
    print(f"Huggingface Hub version: {huggingface_hub.__version__}")
    print(f"Polars version: {pl.__version__}")
    print(f"PyArrow version: {pa.__version__}")
    print(f"Datasets version: {datasets.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")




import json
import time
import torch
from utca.core import RenameAttribute
from utca.implementation.predictors import (
    GLiNERPredictor,
    GLiNERPredictorConfig
)
from utca.implementation.tasks import (
    GLiNER,
    GLiNERPreprocessor,
    GLiNERRelationExtraction,
    GLiNERRelationExtractionPreprocessor,
)

# Example resume text
EXAMPLE_RESUME = """
John Smith
Senior Software Engineer (SWE) at Advanced Technology Solutions (ATS)

Professional Experience:
- Currently working as a Senior Software Engineer (SSE) at Advanced Technology Solutions
- Previously served as a Development Operations Engineer (DevOps) at Cloud Infrastructure Technologies (CIT)
- Started career as a Junior Software Developer (JSD) at Technical Systems International (TSI)

Education:
- Master of Computer Science (MCS) from California Institute of Technology (Caltech)
- Bachelor of Science in Information Technology (BSIT) from University of California, Berkeley (UCB)

Professional Certifications:
- Certified Information Systems Security Professional (CISSP)
- Project Management Professional (PMP)
- Amazon Web Services Solutions Architect (AWS SA)

Skills:
- Full Stack Development (FSD)
- Machine Learning Engineering (MLE)
- Database Administration (DBA)
"""


def setup_pipeline():
    predictor = GLiNERPredictor(
        GLiNERPredictorConfig(
            model_name="knowledgator/gliner-multitask-large-v0.5",
            device="cuda" if torch.cuda.is_available() else "cpu",
        )
    )

    pipe = (
            GLiNER(
                predictor=predictor,
                preprocess=GLiNERPreprocessor(threshold=0.8)
            )
            | RenameAttribute("output", "entities")
            | GLiNERRelationExtraction(
        predictor=predictor,
        preprocess=(
                GLiNERPreprocessor(threshold=0.5)
                | GLiNERRelationExtractionPreprocessor()
        )
    )
    )
    return pipe


def analyze_text(pipe, text: str) -> dict:
    config = {
        "text": text,
        "labels": ["job title", "organization", "profession concept"],
        "relations": [
            {
                "relation": "abbreviation for",
                "pairs_filter": [
                    ("job title", "job title"),
                    ("organization", "organization"),
                    ("profession concept", "profession concept")
                ],
                "distance_threshold": 50,
            },
            {
                "relation": "short for",
                "pairs_filter": [
                    ("job title", "job title"),
                    ("organization", "organization"),
                    ("profession concept", "profession concept")
                ],
                "distance_threshold": 50,
            },
            {
                "relation": "slang for",
                "pairs_filter": [
                    ("job title", "job title"),
                    ("organization", "organization"),
                    ("profession concept", "profession concept")
                ],
                "distance_threshold": 50,
            },
            {
                "relation": "acronym for",
                "pairs_filter": [
                    ("job title", "job title"),
                    ("organization", "organization"),
                    ("profession concept", "profession concept")
                ],
                "distance_threshold": 50,
            }
        ]
    }

    result = pipe.run(config)
    return {
        "entities": result.get("entities", []),
        "relations": result.get("output", [])
    }


def main():
    print("Starting version check...")
    print_versions()

    print("\nInitializing pipeline...")
    pipe = setup_pipeline()

    print("\nAnalyzing resume text...")
    results = analyze_text(pipe, EXAMPLE_RESUME)

    print("\nEntities found:")
    for entity in results["entities"]:
        print(f"- {entity['span']} ({entity['entity']}, score: {entity['score']:.3f})")

    print("\nRelations found:")
    for relation in results["relations"]:
        print(f"- {relation['relation']}:")
        print(f"  From: {relation['source']['span']} ({relation['source']['entity']})")
        print(f"  To: {relation['target']['span']} ({relation['target']['entity']})")
        print(f"  Score: {relation['score']:.3f}")
        print()

    # Save results
    with open('resume_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print("\nResults saved to resume_analysis.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")