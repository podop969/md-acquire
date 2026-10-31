import json
import time
from datetime import datetime
from collections import Counter
from pathlib import Path
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
        return result, execution_time

    return wrapper


class EntityCounter:
    def __init__(self):
        self.entity_counts = Counter()
        self.total_entities = 0
        self.paragraph_counts = []

    def update(self, entities):
        paragraph_counter = Counter(entity['entity'] for entity in entities)
        self.entity_counts.update(paragraph_counter)
        self.total_entities += len(entities)
        self.paragraph_counts.append(paragraph_counter)

    def get_summary(self):
        return {
            "total_entities": self.total_entities,
            "entity_type_counts": dict(self.entity_counts),
            "average_entities_per_paragraph": self.total_entities / len(
                self.paragraph_counts) if self.paragraph_counts else 0,
            "entity_counts_by_paragraph": [dict(count) for count in self.paragraph_counts]
        }


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
                preprocess=GLiNERPreprocessor(threshold=0.5)
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


@measure_time
def analyze_text(pipe, text: str) -> dict:
    config = {
        "text": text,
        "labels": ["author", "scholarly work"],
        "relations": [
            {
                "relation": "authored",
                "pairs_filter": [("author", "scholarly work")],
                "distance_threshold": 150,
            },
            {
                "relation": "co-authored with",
                "pairs_filter": [("author", "author")],
                "distance_threshold": 100,
            }
        ]
    }

    result = pipe.run(config)
    entities = result.get("entities", [])
    relations = result.get("output", [])

    # Filter out duplicate co-authorship relations where source > target
    relations = [r for r in relations if not (
            r['relation'] == 'co-authored with' and
            r['source']['span'] > r['target']['span']
    )]

    enhanced_relations = relations.copy()

    # Process co-authorship information
    authored_relations = [r for r in relations if r['relation'] == 'authored']
    coauthor_relations = [r for r in relations if r['relation'] == 'co-authored with'
                          and r['source']['span'] != r['target']['span']
                          and r['source']['span'] < r['target']['span']]

    # Add authored relations for co-authors
    for auth_rel in authored_relations:
        work = auth_rel['target']
        primary_author = auth_rel['source']

        coauthors = set()
        for coauth_rel in coauthor_relations:
            if coauth_rel['source']['span'] == primary_author['span']:
                coauthors.add(coauth_rel['target']['span'])
            elif coauth_rel['target']['span'] == primary_author['span']:
                coauthors.add(coauth_rel['source']['span'])

        for coauthor_span in coauthors:
            coauthor = next((e for e in entities if e['span'] == coauthor_span), None)
            if coauthor:
                new_relation = {
                    "relation": "authored",
                    "source": coauthor,
                    "target": work,
                    "score": auth_rel['score'] * 0.95
                }
                if new_relation not in enhanced_relations:
                    enhanced_relations.append(new_relation)

    return {
        "entities": entities,
        "relations": enhanced_relations
    }


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\gliner_results")
    results_dir.mkdir(exist_ok=True)

    output_file = results_dir / f"scholarly_analysis_{timestamp}.json"
    stats_file = results_dir / f"entity_statistics_{timestamp}.txt"

    print("Loading paragraphs...")
    input_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\testing_paragraphs.txt"
    with open(input_file, 'r', encoding='utf-8') as f:
        paragraphs = [line.strip() for line in f.readlines() if line.strip()]

    pipe = setup_pipeline()
    all_results = []
    entity_counter = EntityCounter()
    total_execution_time = 0

    print(f"\nStarting analysis at {timestamp}")
    print("=" * 80)

    for idx, text in enumerate(paragraphs, 1):
        print(f"\nAnalyzing paragraph {idx}/{len(paragraphs)}:")
        print(f"Text length: {len(text)} characters")

        try:
            results, execution_time = analyze_text(pipe, text)
            total_execution_time += execution_time

            entity_counter.update(results["entities"])

            print(f"\nParagraph {idx} Results:")
            print(f"Entities found: {len(results['entities'])}")
            print(f"Relations found: {len(results['relations'])}")

            # Print entity counts for this paragraph
            para_counts = Counter(entity['entity'] for entity in results['entities'])
            print("\nEntity counts for this paragraph:")
            for entity_type, count in para_counts.items():
                print(f"- {entity_type}: {count}")

            print("\nDetailed entities:")
            for entity in results["entities"]:
                print(f"- {entity['span']} ({entity['entity']}, score: {entity['score']:.3f})")

            all_results.append({
                "paragraph_index": idx,
                "analysis": results,
                "execution_time": execution_time
            })

        except Exception as e:
            print(f"Error processing paragraph {idx}: {str(e)}")
            continue

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "metadata": {
                "timestamp": timestamp,
                "total_paragraphs": len(paragraphs),
                "total_execution_time": total_execution_time,
                "average_time_per_paragraph": total_execution_time / len(paragraphs)
            },
            "results": all_results
        }, f, indent=4, ensure_ascii=False)

    entity_stats = entity_counter.get_summary()
    with open(stats_file, 'w', encoding='utf-8') as f:
        f.write(f"Entity Statistics Report - {timestamp}\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total Entities Found: {entity_stats['total_entities']}\n")
        f.write(f"Average Entities per Paragraph: {entity_stats['average_entities_per_paragraph']:.2f}\n\n")
        f.write("Entity Counts by Type:\n")
        for entity_type, count in entity_stats['entity_type_counts'].items():
            f.write(f"- {entity_type}: {count}\n")

        f.write("\nEntity Counts by Paragraph:\n")
        for idx, para_counts in enumerate(entity_stats['entity_counts_by_paragraph'], 1):
            f.write(f"\nParagraph {idx}:\n")
            for entity_type, count in para_counts.items():
                f.write(f"- {entity_type}: {count}\n")

    print("\nAnalysis Complete!")
    print(f"Results saved to: {output_file}")
    print(f"Statistics saved to: {stats_file}")
    print("\nFinal Entity Statistics:")
    print(f"Total Entities: {entity_stats['total_entities']}")
    print("\nCounts by Type:")
    for entity_type, count in entity_stats['entity_type_counts'].items():
        print(f"- {entity_type}: {count}")


if __name__ == "__main__":
    try:
        print("Starting scholarly analysis...")
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")