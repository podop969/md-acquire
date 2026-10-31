import json
from transformers import pipeline
from collections import defaultdict
import os

# Topic: Natural Language Processing Techniques
# Subfield: Artificial Intelligence
# Field: Computer Science
# Domain: Physical Sciences



class TopicClassifier:
    def __init__(self,
                 model_name="OpenAlex/bert-base-multilingual-cased-finetuned-openalex-topic-classification-title-abstract",
                 top_k=50, device='cuda', subfield_boost=0.01):
        self.classifier = pipeline(
            model=model_name,
            top_k=top_k,
            truncation=True,
            max_length=512,
            device=device
        )
        self.top_k = top_k
        self.subfield_boost = subfield_boost
        self.topics_mapping = None
        self.load_and_process_topics()

    def load_and_process_topics(self):
        """Load topics mapping from enhanced file if it exists, otherwise process from scratch"""
        enhanced_file_path = 'enhanced_unique_topics.json'

        # First try to load the enhanced file
        if os.path.exists(enhanced_file_path):
            with open(enhanced_file_path, 'r', encoding='utf-8') as f:
                enhanced_data = json.load(f)
                self.topics_mapping = enhanced_data['topic_mapping']
                return

    def predict(self, title, abstract):
        """Make predictions and calculate subfield boosts"""
        formatted_input = f"<TITLE> {title}\n<ABSTRACT> {abstract}"
        results = self.classifier(formatted_input)

        # Calculate subfield boosts
        subfield_scores = defaultdict(float)
        processed_results = []

        # results is already a list of dictionaries with 'label' and 'score'
        for result in results[0]:  # Remove the [0] indexing
            # Each result is already a dict with 'label' and 'score'
            topic_id, topic_name = result['label'].split(': ', 1)
            print(f"Topic: {topic_name}, Score: {result['score']:.3f}")  # Fixed print statement

            if topic_name in self.topics_mapping:
                field_subfield = self.topics_mapping[topic_name]['field_subfield']
                # Add the original score
                subfield_scores[field_subfield] += result['score']

                processed_results.append({
                    'label': result['label'],
                    'score': result['score'],
                    'field_subfield': field_subfield,
                    'field': self.topics_mapping[topic_name]['field'],
                    'subfield': self.topics_mapping[topic_name]['subfield']
                })

        # Add boost for each occurrence of a field+subfield
        for result in processed_results:
            field_subfield = result['field_subfield']
            occurrences = sum(1 for r in processed_results if r['field_subfield'] == field_subfield)
            result['boosted_score'] = result['score'] + (occurrences * self.subfield_boost)

        return {
            'raw_predictions': processed_results,
            'subfield_scores': dict(subfield_scores),
            'top_subfield': max(subfield_scores.items(), key=lambda x: x[1]) if subfield_scores else None
        }


def main():
    # Example usage
    classifier = TopicClassifier(subfield_boost=0.01)

    title = "attention is all you need"
    abstract = "Attention is all you need is a paper written at google brain in 2017. Illia Polosukhin and Noam Shazeer, in artificial intelligence research. On transformer neural network architectures."

    results = classifier.predict(title, abstract)

    print("\nRaw Predictions with Boosted Scores:")
    for pred in results['raw_predictions']:
        print(f"Topic: {pred['label']}")
        print(f"Original Score: {pred['score']:.3f}")
        print(f"Boosted Score: {pred['boosted_score']:.3f}")
        print(f"Field+Subfield: {pred['field_subfield']}\n")

    print("\nSubfield Scores:")
    for subfield, score in results['subfield_scores'].items():
        print(f"{subfield}: {score:.3f}")

    if results['top_subfield']:
        print(f"\nTop Subfield: {results['top_subfield'][0]} (Score: {results['top_subfield'][1]:.3f})")


if __name__ == "__main__":
    main()