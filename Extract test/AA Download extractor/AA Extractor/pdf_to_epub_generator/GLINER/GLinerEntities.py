import time
import json
import torch
from typing import List, Dict
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


class EnhancedGlinerModelTester:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        self.models = {
            #"small": "urchade/gliner_small-v2.1",
            #"medium": "urchade/gliner_medium-v2.1",
            "large": "urchade/gliner_large-v2.1",
        }

        self.labels = ["scholar", "work of art", "book", "journal", "journal article", "date", "publication date", "institute", "source", "publisher"]

        # Comprehensive list of entity categories
        self.categories = [
            # Academic Structure
            "academic field", "academic subfield", "academic topic",

            # Academic Entities
            "academic organization", "research institution", "journal",
            "book", "journal article", "database", "scholar",
            "research equipment", "research grant", "archive",

            # Historical Categories
            "historical event", "historical period", "historical framework",
            "historiography", "historical process", "historical institution",
            "historical movement", "historical artifact", "historical document",
            "historical figure", "historical methodology", "historical interpretation",
            "historical context", "comparative history",

            # Geographic
            "geographic entity",

            # Technology
            "technology",

            # Biomedical Categories
            "anatomy", "organism", "disease", "medical occupation",
            "chemical compound", "drug", "mental disorder",
            "circulatory respiratory phenomena", "cell phenomena",
            "musculoskeletal neural phenomena", "immune system phenomena",
            "genetic phenomena", "reproductive urinary phenomena",
            "microbiological phenomena", "digestive oral phenomena",
            "integumentary phenomena", "plant phenomena",
            "psychological phenomena", "population characteristic",
            "medical institution", "public health concept",
            "patient type", "group type", "food type",

            # Legal Categories
            "law", "legal definition", "legal procedure", "evidence rule",
            "jurisdiction", "constitutional right", "civil right",
            "legal duty", "liability", "legal entity", "judicial body",
            "legal role", "legal document", "court document",
            "legal citation", "patent",

            # Computer Science Categories
            "algorithm", "data structure", "coding language", "dataset",
            "software", "software library", "algorithmic case analysis",
            "complexity class", "computability class",

            # Mathematical Categories
            "definition", "theorem", "axiom", "conjecture", "equation",
            "inequality", "integral", "limit", "function", "identity",
            "proof", "proof technique", "parameter",

            # Scientific Categories
            "law of nature", "research method", "research paradigm",
            "statistical method", "study type", "experimental technique",
            "auxiliary assumption", "scientific model", "scientific instrument",
            "measurement technique", "scientific theory", "scientific hypothesis",
            "error source", "scientific principle", "control variable",
            "dependent variable", "independent variable", "scientific protocol",
            "data collection method", "data analysis method",
            "scientific notation", "scientific validation", "scientific inference",
            "scientific constraint", "scientific standard", "scientific scale",
            "replication method", "calibration technique", "scientific observation",

            # Field-Specific Concepts
            "biochemistry concept", "engineering concept", "environmental concept",
            "mathematics concept", "social concept", "physics concept",
            "economics concept", "humanities concept", "chemistry concept",
            "agricultural concept", "medicine concept", "computer concept",
            "psychology concept", "chemical engineering concept", "nursing concept",
            "pharmacology concept", "business concept", "neuroscience concept",
            "materials concept", "health concept", "immunology concept",
            "earth concept", "energy concept", "dentistry concept",
            "veterinary concept", "decision concept", "music concept",

            # Miscellaneous
            "misc"
        ]

        self.max_length = 768
        self.confidence_threshold = 0.5  # Adjustable confidence threshold

    def chunk_text(self, text: str, max_length: int = 768) -> List[str]:
        """Split text into chunks if it exceeds max_length."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            word_length = len(word.split())
            if current_length + word_length > max_length:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def categorize_entity(self, entity: Dict) -> Dict:
        """Add additional categorization and metadata to entity."""
        entity['confidence_level'] = 'high' if entity['score'] > 0.8 else 'medium' if entity['score'] > 0.6 else 'low'

        # Add category grouping
        if entity['label'] in ['journal', 'book', 'journal_article']:
            entity['category_group'] = 'publications'
        elif entity['label'].startswith('historical_'):
            entity['category_group'] = 'historical'
        elif entity['label'].startswith('concept_'):
            entity['category_group'] = 'field_specific'
        else:
            entity['category_group'] = 'general'

        return entity

    @measure_time
    def analyze_single_text(self, text: str, model: GLiNER) -> List[Dict]:
        text_length = len(text.split())
        print(f"Text length (words): {text_length}")

        if text_length > self.max_length:
            print(f"Text exceeds maximum length of {self.max_length}, chunking...")
            chunks = self.chunk_text(text)
            all_entities = []

            for i, chunk in enumerate(chunks):
                print(f"Processing chunk {i + 1}/{len(chunks)}")
                chunk_entities = model.predict_entities(chunk, self.categories)

                # Filter by confidence threshold
                chunk_entities = [entity for entity in chunk_entities
                                  if entity['score'] >= self.confidence_threshold]

                # Adjust entity positions for chunks after the first
                if i > 0:
                    previous_text = ' '.join(chunks[:i])
                    offset = len(previous_text) + 1
                    for entity in chunk_entities:
                        entity['start'] += offset
                        entity['end'] += offset

                # Add additional categorization
                chunk_entities = [self.categorize_entity(entity) for entity in chunk_entities]
                all_entities.extend(chunk_entities)

            return all_entities
        else:
            entities = model.predict_entities(text, self.categories)
            entities = [entity for entity in entities
                        if entity['score'] >= self.confidence_threshold]
            return [self.categorize_entity(entity) for entity in entities]

    def print_results(self, text: str, model_name: str, entities: List[Dict]):
        print(f"\nText:\n{text}\n")
        print(f"Model: {model_name}")
        print(f"Text length (characters): {len(text)}")
        print(f"Text length (words): {len(text.split())}")
        print("-" * 50)

        # Group entities by category_group
        grouped_entities = {}
        for entity in entities:
            group = entity['category_group']
            if group not in grouped_entities:
                grouped_entities[group] = []
            grouped_entities[group].append(entity)

        for group, group_entities in grouped_entities.items():
            print(f"\n{group.upper()} ENTITIES:")
            for entity in group_entities:
                print(f"Text: {entity['text']}")
                print(f"Label: {entity['label']}")
                print(f"Score: {entity['score']:.2f}")
                print(f"Confidence: {entity['confidence_level']}")
                print(f"Position: {entity['start']} to {entity['end']}")
                print()

    @measure_time
    def process_all_texts_with_model(self, texts: List[str], model_name: str) -> List[Dict]:
        print(f"\nLoading {model_name} model...")
        model = GLiNER.from_pretrained(self.models[model_name])

        if self.device == "cuda":
            model = model.to(self.device)

        results = []
        print(f"\nProcessing all texts with {model_name} model...")

        for idx, text in enumerate(texts):
            print(f"\nProcessing text {idx + 1}")
            entities = self.analyze_single_text(text, model)

            result = {
                "text_index": idx + 1,
                "text": text,
                "text_length": len(text.split()),
                "entities": entities,
                "entity_stats": {
                    "total_entities": len(entities),
                    "entities_by_category": self._get_entity_stats(entities),
                    "confidence_distribution": self._get_confidence_distribution(entities)
                }
            }
            self.print_results(text, model_name, entities)
            results.append(result)

        if self.device == "cuda":
            torch.cuda.empty_cache()

        return results

    def _get_entity_stats(self, entities: List[Dict]) -> Dict:
        """Calculate statistics about entity categories."""
        stats = {}
        for entity in entities:
            category = entity['category_group']
            if category not in stats:
                stats[category] = 0
            stats[category] += 1
        return stats

    def _get_confidence_distribution(self, entities: List[Dict]) -> Dict:
        """Calculate distribution of confidence levels."""
        distribution = {'high': 0, 'medium': 0, 'low': 0}
        for entity in entities:
            distribution[entity['confidence_level']] += 1
        return distribution


def main():
    input_file = "testing_paragraphs.txt"  # Update with your input file path
    output_file = "enhanced_gliner_results.json"  # Update with your output file path

    print("Loading paragraphs...")
    paragraphs = load_paragraphs(input_file)

    tester = EnhancedGlinerModelTester()
    all_results = {}

    for model_name in tester.models:
        print(f"\n{'=' * 20} Testing {model_name} model {'=' * 20}")
        model_results = tester.process_all_texts_with_model(paragraphs, model_name)
        all_results[model_name] = model_results

    save_to_json(all_results, output_file)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    try:
        print("Starting Enhanced GLiNER v2.1 model comparison...")
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")