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


def measure_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Execution time of {func.__name__}: {execution_time:.6f} seconds")
        return result

    return wrapper





def setup_pipeline():
    # Initialize predictor
    predictor = GLiNERPredictor(
        GLiNERPredictorConfig(
            model_name="knowledgator/gliner-multitask-large-v0.5",
            device="cuda" if torch.cuda.is_available() else "cpu",
        )
    )

    # Create pipeline
    pipe = (
            GLiNER(
                predictor=predictor,
                preprocess=GLiNERPreprocessor(threshold=0.8)  # Entity detection threshold
            )
            | RenameAttribute("output", "entities")
            | GLiNERRelationExtraction(
        predictor=predictor,
        preprocess=(
                GLiNERPreprocessor(threshold=0.5)  # Relation detection threshold
                | GLiNERRelationExtractionPreprocessor()
        )
    )
    )
    return pipe


@measure_time
def analyze_text(pipe, text: str) -> dict:
    # Configure pipeline input
    config = {
        "text": text,
        "labels": ["author", "scholarly work", "research institute", "publication venue", "publication date"],
        "relations": [
            # Existing relationships
            {
                "relation": "authored",
                "pairs_filter": [("author", "scholarly work")],
                "distance_threshold": 150,
            },
            {
                "relation": "co-authored with",
                "pairs_filter": [("author", "author")],
                "distance_threshold": 100,
            },
            {
                "relation": "published in",
                "pairs_filter": [("scholarly work", "publication venue")],
                "distance_threshold": 150,
            },
            {
                "relation": "affiliated with",
                "pairs_filter": [("author", "research institute")],
                "distance_threshold": 150,
            },
            {
                "relation": "conducted at",
                "pairs_filter": [("scholarly work", "research institute")],
                "distance_threshold": 150,
            },
            {
                "relation": "cited in year",  # or "published research in"
                "pairs_filter": [("author", "publication date")],
                "distance_threshold": 75,
            },
            {
                "relation": "published in year",  # For work-date relation
                "pairs_filter": [("scholarly work", "publication date")],
                "distance_threshold": 100,
            }
        ]
    }