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
    # from gliner import GLiNER
    #
    # model = GLiNER.from_pretrained("xomad/gliner-model-merge-large-v1.0")
    # model_name = "xomad/gliner-model-merge-large-v1.0"
    # model_name = "knowledgator/gliner-multitask-large-v0.5"
    # knowledgator/gliner-multitask-v1.0
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
                preprocess=GLiNERPreprocessor(threshold=0.5)  # Entity detection threshold
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

    # Run pipeline
    result = pipe.run(config)
    entities = result.get("entities", [])
    relations = result.get("output", [])
    # enhanced_relations = relations.copy()
    # Filter out duplicate co-author relations from both original and enhanced relations
    relations = [r for r in relations if not (
            r['relation'] == 'co-authored with' and
            r['source']['span'] > r['target']['span']
    )]
    enhanced_relations = relations.copy()

    # Find all authored relations and coauthor relations
    authored_relations = [r for r in relations if r['relation'] == 'authored']
    # Change this part:
    coauthor_relations = [r for r in relations if r['relation'] == 'co-authored with'
                          and r['source']['span'] != r['target']['span']  # No self-relations
                          and r['source']['span'] < r['target']['span']]  # Only keep one direction of the relation



    # Process coauthor relationships and their associated metadata
    for auth_rel in authored_relations:
        work = auth_rel['target']
        primary_author = auth_rel['source']

        # Find all co-authors
        coauthors = set()
        # For co-author detection, add condition to prevent self-relations

        # Also ensure bi-directional co-author relationships are properly handled
        for coauth_rel in coauthor_relations:
            if coauth_rel['source']['span'] == primary_author['span']:
                coauthors.add(coauth_rel['target']['span'])
            elif coauth_rel['target']['span'] == primary_author['span']:
                coauthors.add(coauth_rel['source']['span'])

        # Get work's metadata (venue, date, institute)
        work_metadata = {
            'venue': next((r['target'] for r in relations if
                           r['relation'] == 'published in' and r['source']['span'] == work['span']), None),
            'date': next((r['target'] for r in relations if
                          r['relation'] == 'citation year' and r['source']['span'] == work['span']), None),
            'institute': next((r['target'] for r in relations if
                               r['relation'] == 'conducted at' and r['source']['span'] == work['span']), None)
        }


        # Create relations for each co-author
        for coauthor_span in coauthors:
            coauthor = next((e for e in entities if e['span'] == coauthor_span), None)
            if coauthor:
                # Add authored relation
                new_relation = {
                    "relation": "authored",
                    "source": coauthor,
                    "target": work,
                    "score": auth_rel['score'] * 0.95
                }
                if new_relation not in enhanced_relations:
                    enhanced_relations.append(new_relation)

                # Add metadata relations for co-author
                if work_metadata['venue']:
                    enhanced_relations.append({
                        "relation": "published in",
                        "source": coauthor,
                        "target": work_metadata['venue'],
                        "score": auth_rel['score'] * 0.9
                    })
                # And later in the co-author metadata relations section:
                if work_metadata['date']:
                    enhanced_relations.append({
                        "relation": "cited in year",
                        "source": coauthor,
                        "target": work_metadata['date'],
                        "score": auth_rel['score'] * 0.9
                    })
                if work_metadata['institute']:
                    enhanced_relations.append({
                        "relation": "affiliated with",
                        "source": coauthor,
                        "target": work_metadata['institute'],
                        "score": auth_rel['score'] * 0.9
                    })


    return {
        "entities": entities,
        "relations": enhanced_relations
    }


def main():
    input_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\testing_paragraphs.txt"
    output_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\scholarly_analysis.json"

    print("Loading paragraphs...")
    with open(input_file, 'r', encoding='utf-8') as f:
        paragraphs = [line.strip() for line in f.readlines() if line.strip()]

    # Setup pipeline
    pipe = setup_pipeline()
    all_results = []

    for idx, text in enumerate(paragraphs, 1):
        print(f"\nAnalyzing paragraph {idx}:")
        print("Text:", text)

        try:
            results = analyze_text(pipe, text)

            print("\nResults:")
            print(f"Entities found: {len(results['entities'])}")
            print(f"Relations found: {len(results['relations'])}")

            print("\nEntities:")
            for entity in results["entities"]:
                print(f"- {entity['span']} ({entity['entity']}, score: {entity['score']:.3f})")

            print("\nRelations:")
            for relation in results["relations"]:
                print(f"- {relation['relation']}:")
                print(f"  From: {relation['source']['span']} ({relation['source']['entity']})")
                print(f"  To: {relation['target']['span']} ({relation['target']['entity']})")
                print(f"  Score: {relation['score']:.3f}")
                print()

            all_results.append({
                "paragraph_index": idx,
                "analysis": results
            })

        except Exception as e:
            print(f"Error processing paragraph {idx}: {str(e)}")
            continue

    # Save results
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    try:
        print("Starting scholarly analysis...")
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")