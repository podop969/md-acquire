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


class GlinerModelTester:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        self.models = {
            "small": "urchade/gliner_small-v2.1",
            "medium": "urchade/gliner_medium-v2.1",
            "large": "urchade/gliner_large-v2.1",
            # "multi": "urchade/gliner_multi-v2.1",
            # "zero_span": "numind/NuNerZero_span",
        }
        self.labels = ["scholar", "work of art", "book", "journal", "journal article", "date", "publication date", "institute", "source", "publisher"]
        self.max_length = 768  # Maximum sequence length from the paper

    def chunk_text(self, text: str, max_length: int = 768) -> List[str]:
        """Split text into chunks if it exceeds max_length."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            # Approximate token length (rough estimation)
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
                chunk_entities = model.predict_entities(chunk, self.labels)

                # Adjust entity positions for chunks after the first
                if i > 0:
                    previous_text = ' '.join(chunks[:i])
                    offset = len(previous_text) + 1  # +1 for space
                    for entity in chunk_entities:
                        entity['start'] += offset
                        entity['end'] += offset

                all_entities.extend(chunk_entities)
            return all_entities
        else:
            return model.predict_entities(text, self.labels)

    def print_results(self, text: str, model_name: str, entities: List[Dict]):
        print(f"\nText:\n{text}\n")
        print(f"Model: {model_name}")
        print(f"Text length (characters): {len(text)}")
        print(f"Text length (words): {len(text.split())}")
        print("-" * 50)

        for entity in entities:
            print(f"Text: {entity['text']}")
            print(f"Label: {entity['label']}")
            print(f"Score: {entity['score']:.2f}")
            print(f"Position: {entity['start']} to {entity['end']}")
            print()

    @measure_time
    def process_all_texts_with_model(self, texts: List[str], model_name: str) -> List[Dict]:
        print(f"\nLoading {model_name} model...")
        model = GLiNER.from_pretrained(self.models[model_name])

        # Move model to GPU if available
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
                "entities": entities
            }
            self.print_results(text, model_name, entities)
            results.append(result)

        # Clear GPU memory after processing
        if self.device == "cuda":
            torch.cuda.empty_cache()

        return results


def main():
    input_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\testing_paragraphs.txt"
    output_file = r"C:\Users\doren\PycharmProjects\CiteGrabberFinal\APIDetails\gliner_v2_results.json"

    print("Loading paragraphs...")
    paragraphs = load_paragraphs(input_file)

    tester = GlinerModelTester()
    all_results = {}

    # Process all texts with each model
    for model_name in tester.models:
        print(f"\n{'=' * 20} Testing {model_name} model {'=' * 20}")
        model_results = tester.process_all_texts_with_model(paragraphs, model_name)
        all_results[model_name] = model_results

    # Save all results to JSON
    save_to_json(all_results, output_file)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    try:
        print("Starting GLiNER v2.1 model comparison...")
        main()
    except Exception as e:
        print(f"An error occurred: {str(e)}")