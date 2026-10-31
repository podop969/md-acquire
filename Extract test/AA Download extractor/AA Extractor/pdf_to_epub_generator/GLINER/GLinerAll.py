import time
import json
from typing import List, Dict, Tuple

import torch
from gliner import GLiNER


def measure_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"Execution time of {func.__name__}: {execution_time:.6f} seconds")
        return result

    return wrapper


def load_paragraphs(file_path: str) -> List[str]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def save_to_json(data: Dict, file_path: str):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class GlinerAdvancedAnalyzer:
    def __init__(self):
        print("Initializing GLiNER model...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        self.model = GLiNER.from_pretrained("knowledgator/gliner-multitask-large-v0.5")
        if self.device == "cuda":
            self.model = self.model.to(self.device)

        self.entity_labels = ["author", "work of art", "book", "journal", "paper"]
        self.relation_patterns = [
            "co-author with",  # For author-author relationships
            "author of",  # For author-work relationships
            "publication date of",
        ]
        self.summary_threshold = 0.1
        self.keyphrase_threshold = 0.1

    @measure_time
    def extract_entities(self, text: str) -> List[Dict]:
        """Extract scholarly entities from text."""
        return self.model.predict_entities(text, self.entity_labels)

    @measure_time
    def extract_relations(self, text: str, entity_pairs: List[Tuple[Dict, Dict]]) -> List[Dict]:
        """Extract relations between pairs of entities."""
        relations = []
        for entity1, entity2 in entity_pairs:
            if abs(entity1['end'] - entity2['start']) > 100 and abs(entity2['end'] - entity1['start']) > 100:
                continue

            for pattern in self.relation_patterns:
                if pattern == "co-author with" and entity1['label'] == "author" and entity2['label'] == "author":
                    relation_label = f"{entity1['text']} <> co-author with <> {entity2['text']}"
                elif pattern in ["author of"] and entity1['label'] == "author" and entity2['label'] in [
                    "work of art", "book", "paper"]:
                    relation_label = f"{entity1['text']} <> {pattern} <> {entity2['text']}"
                else:
                    continue

                relation_results = self.model.predict_entities(text, [relation_label])

                for rel in relation_results:
                    if rel['score'] > 0.5:
                        relations.append({
                            "entity1": entity1,
                            "entity2": entity2,
                            "relation": pattern,
                            "text": rel['text'],
                            "score": rel['score']
                        })

        return relations

    @measure_time
    def extract_summary(self, text: str) -> List[Dict]:
        """Extract summary from text."""
        prompt = "Summarize the given text, highlighting the most important information:\n"
        input_text = f"{prompt}{text}"
        return self.model.predict_entities(input_text, ["summary"], threshold=self.summary_threshold)

    @measure_time
    def extract_keyphrases(self, text: str) -> List[Dict]:
        """Extract key phrases from text."""
        prompt = "Extract the most important key phrases from the text:\n"
        input_text = f"{prompt}{text}"
        return self.model.predict_entities(input_text, ["key_phrase"], threshold=self.keyphrase_threshold)

    @measure_time
    def analyze_text(self, text: str) -> Dict:
        """Perform full analysis of text including entities, relations, summary, and keyphrases."""
        # Extract all components
        entities = self.extract_entities(text)

        entity_pairs = []
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i + 1:]:
                entity_pairs.append((entity1, entity2))

        relations = self.extract_relations(text, entity_pairs)
        summary = self.extract_summary(text)
        keyphrases = self.extract_keyphrases(text)

        return {
            "entities": entities,
            "relations": relations,
            "summary": summary,
            "keyphrases": keyphrases,
            "text": text
        }


def main():
    input_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\testing_paragraphs.txt"
    output_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\advanced_analysis.json"

    print("Loading paragraphs...")
    paragraphs = load_paragraphs(input_file)

    analyzer = GlinerAdvancedAnalyzer()
    all_results = []

    for idx, text in enumerate(paragraphs):
        print(f"\nAnalyzing paragraph {idx + 1}:")
        results = analyzer.analyze_text(text)
        print("text: ", text)
        print("text length", len(text))

        print(f"\nSummary of paragraph {idx + 1}:")
        print("-" * 50)
        for summary in results["summary"]:
            print(f"Summary: {summary['text']}")
            print(f"Score: {summary['score']:.2f}")
            print()

        print(f"\nKey phrases in paragraph {idx + 1}:")
        print("-" * 50)
        for keyphrase in results["keyphrases"]:
            print(f"Key phrase: {keyphrase['text']}")
            print(f"Score: {keyphrase['score']:.2f}")
            print()

        print(f"\nEntities found in paragraph {idx + 1}:")
        print("-" * 50)
        for entity in results["entities"]:
            print(f"Text: {entity['text']}")
            print(f"Label: {entity['label']}")
            print(f"Score: {entity['score']:.2f}")
            print()

        print(f"\nRelations found in paragraph {idx + 1}:")
        print("-" * 50)
        for relation in results["relations"]:
            print(f"Relation: {relation['relation']}")
            print(f"Entity 1: {relation['entity1']['text']} ({relation['entity1']['label']})")
            print(f"Entity 2: {relation['entity2']['text']} ({relation['entity2']['label']})")
            print(f"Score: {relation['score']:.2f}")
            print(f"Context: {relation['text']}")
            print()




        all_results.append({
            "paragraph_index": idx + 1,
            "analysis": results
        })

    save_to_json(all_results, output_file)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    try:
        print("Starting advanced analysis...")
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")