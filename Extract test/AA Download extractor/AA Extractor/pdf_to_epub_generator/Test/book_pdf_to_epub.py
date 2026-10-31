
"""
PDF to XML Book Processor - Linear Time Complexity Architecture
Processes academic PDFs to extract structured XML with entities and relations
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import PyPDF2
from pathlib import Path
import json

class CitationType(Enum):
    NUMBERED = "numbered"
    AUTHOR_YEAR = "author_year"
    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"
    INLINE = "inline"

class EntityType(Enum):
    # Document structure
    BOOK_TITLE = "book_title"
    CHAPTER_TITLE = "chapter_title"
    AUTHOR = "author"
    PUBLISHER = "publisher"
    PUBLICATION_DATE = "publication_date"

    # Content
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    CITATION = "citation"
    QUOTATION = "quotation"
    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"

    # Structural
    PAGE_NUMBER = "page_number"
    CHAPTER_NUMBER = "chapter_number"
    HEADER = "header"
    FOOTER = "footer"

    # References
    BIBLIOGRAPHY_ENTRY = "bibliography_entry"
    REFERENCE_ENTRY = "reference_entry"

@dataclass
class Entity:
    """Represents an extracted entity with position and metadata"""
    entity_type: EntityType
    text: str
    start_pos: int
    end_pos: int
    page_number: int
    chapter_number: Optional[int] = None
    confidence: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_xml_element(self) -> ET.Element:
        """Convert entity to XML element"""
        elem = ET.Element(self.entity_type.value)
        elem.text = self.text
        elem.set('start', str(self.start_pos))
        elem.set('end', str(self.end_pos))
        elem.set('page', str(self.page_number))
        if self.chapter_number:
            elem.set('chapter', str(self.chapter_number))
        elem.set('confidence', str(self.confidence))

        # Add metadata as attributes
        for key, value in self.metadata.items():
            elem.set(key, str(value))

        return elem

@dataclass
class Relation:
    """Represents a relation between two entities"""
    relation_type: str
    source_entity: Entity
    target_entity: Entity
    confidence: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def to_xml_element(self) -> ET.Element:
        """Convert relation to XML element"""
        elem = ET.Element('relation')
        elem.set('type', self.relation_type)
        elem.set('source_start', str(self.source_entity.start_pos))
        elem.set('target_start', str(self.target_entity.start_pos))
        elem.set('confidence', str(self.confidence))

        for key, value in self.metadata.items():
            elem.set(key, str(value))

        return elem

class BookProcessor:
    """Main processor class - Linear time complexity O(n)"""

    def __init__(self, gliner_model):
        self.gliner_model = gliner_model
        self.entities: List[Entity] = []
        self.relations: List[Relation] = []
        self.citation_stack: List[Dict] = []  # For matching citations to bibliography
        self.current_position = 0
        self.current_page = 1
        self.current_chapter = 1

        # Compiled regex patterns for efficiency
        self.patterns = self._compile_patterns()

        # Entity labels for GLiNER
        self.entity_labels = [
            "book_title", "chapter_title", "author", "publisher", "publication_date",
            "citation", "footnote", "endnote", "quotation", "page_number",
            "chapter_number", "bibliography_entry", "table", "figure"
        ]

        # Relation types for GLiNER
        self.relation_types = [
            {"relation": "cites", "pairs_filter": [("citation", "bibliography_entry")]},
            {"relation": "appears_in_chapter", "pairs_filter": [("citation", "chapter_title")]},
            {"relation": "authored", "pairs_filter": [("author", "book_title")]},
            {"relation": "published_by", "pairs_filter": [("book_title", "publisher")]},
            {"relation": "contains", "pairs_filter": [("chapter_title", "paragraph")]},
            {"relation": "footnote_of", "pairs_filter": [("footnote", "paragraph")]},
        ]

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile all regex patterns once for efficiency"""
        return {
            # Citation patterns
            'numbered_citation': re.compile(r'\[(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\]'),
            'author_year': re.compile(r'\(([A-Z][a-z]+(?:\s+(?:&|and)\s+[A-Z][a-z]+)*,?\s+\d{4}[a-z]?)\)'),
            'footnote_marker': re.compile(r'(\d+)'),

            # Structure patterns
            'chapter_title': re.compile(r'^(?:Chapter\s+)?(\d+|[IVX]+)[\.\s]+(.+)$', re.MULTILINE),
            'page_number': re.compile(r'^\s*(\d+|[ivx]+)\s*$', re.MULTILINE),
            'header_footer': re.compile(r'^(.+?)\s+(\d+)$'),

            # Bibliography patterns
            'bibliography_start': re.compile(r'^(?:Bibliography|References|Works\s+Cited|Endnotes)', re.MULTILINE | re.IGNORECASE),
            'bibliography_entry': re.compile(r'^([A-Z][a-zA-Z\s,]+)\.\s+(.+)$', re.MULTILINE),
        }

    def process_pdf(self, pdf_path: Path) -> ET.Element:
        """
        Main processing function - Linear time O(n) where n is text length
        Single pass through the document with state tracking
        """
        print(f"Processing PDF: {pdf_path}")

        # Extract text from PDF
        full_text = self._extract_text_from_pdf(pdf_path)

        # Single linear pass through text
        self._linear_scan(full_text)

        # Match citations to bibliography (using the stack we built)
        self._match_citations_to_bibliography()

        # Generate XML output
        xml_root = self._generate_xml()

        return xml_root

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text while preserving structure information"""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            full_text = ""

            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text()
                # Add page markers for tracking
                full_text += f"<PAGE_{page_num}>\n{page_text}\n</PAGE_{page_num}>\n"

        return full_text

    def _linear_scan(self, text: str) -> None:
        """
        Single pass through text - O(n) complexity
        Uses state machine to track context while scanning
        """
        print("Starting linear scan...")

        lines = text.split('\n')
        in_bibliography = False
        in_footnotes = False
        current_chapter_title = None

        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Update position tracking
            self.current_position += len(line)

            # Check for page markers
            if line.startswith('<PAGE_') and line.endswith('>'):
                self.current_page = int(line.replace('<PAGE_', '').replace('>', ''))
                continue

            # State transitions
            if self.patterns['bibliography_start'].search(line):
                in_bibliography = True
                continue

            # Process based on current state
            if in_bibliography:
                self._process_bibliography_line(line, line_num)
            elif in_footnotes:
                self._process_footnote_line(line, line_num)
            else:
                self._process_main_text_line(line, line_num)

        print(f"Linear scan complete. Found {len(self.entities)} entities.")

    def _process_main_text_line(self, line: str, line_num: int) -> None:
        """Process a line from main text content"""

        # Check for chapter titles
        chapter_match = self.patterns['chapter_title'].match(line)
        if chapter_match:
            self.current_chapter = int(chapter_match.group(1)) if chapter_match.group \
                (1).isdigit() else self.current_chapter
            entity = Entity(
                entity_type=EntityType.CHAPTER_TITLE,
                text=chapter_match.group(2),
                start_pos=self.current_position,
                end_pos=self.current_position + len(line),
                page_number=self.current_page,
                chapter_number=self.current_chapter,
                metadata={'chapter_num': self.current_chapter}
            )
            self.entities.append(entity)
            return

        # Check for page headers/footers
        if self._is_header_footer(line):
            entity = Entity(
                entity_type=EntityType.HEADER,
                text=line,
                start_pos=self.current_position,
                end_pos=self.current_position + len(line),
                page_number=self.current_page,
                chapter_number=self.current_chapter
            )
            self.entities.append(entity)
            return

        # Process regular paragraph content
        self._process_paragraph_content(line, line_num)

    def _process_paragraph_content(self, line: str, line_num: int) -> None:
        """Process paragraph content for citations and other entities"""

        # Use GLiNER for entity detection
        gliner_results = self.gliner_model.predict_entities(line, self.entity_labels)

        # Convert GLiNER results to our Entity objects
        for result in gliner_results:
            entity_type_str = result['label']
            if hasattr(EntityType, entity_type_str.upper()):
                entity_type = EntityType(entity_type_str)

                entity = Entity(
                    entity_type=entity_type,
                    text=result['text'],
                    start_pos=self.current_position + result['start'],
                    end_pos=self.current_position + result['end'],
                    page_number=self.current_page,
                    chapter_number=self.current_chapter,
                    confidence=result['score']
                )
                self.entities.append(entity)

                # Add to citation stack if it's a citation
                if entity_type == EntityType.CITATION:
                    self.citation_stack.append({
                        'entity': entity,
                        'chapter': self.current_chapter,
                        'page': self.current_page,
                        'text': result['text']
                    })

        # Additional regex-based detection for patterns GLiNER might miss
        self._detect_citation_patterns(line)

    def _detect_citation_patterns(self, line: str) -> None:
        """Detect specific citation patterns using regex"""

        # Numbered citations
        for match in self.patterns['numbered_citation'].finditer(line):
            entity = Entity(
                entity_type=EntityType.CITATION,
                text=match.group(0),
                start_pos=self.current_position + match.start(),
                end_pos=self.current_position + match.end(),
                page_number=self.current_page,
                chapter_number=self.current_chapter,
                metadata={'citation_type': 'numbered', 'numbers': match.group(1)}
            )
            self.entities.append(entity)
            self.citation_stack.append({
                'entity': entity,
                'chapter': self.current_chapter,
                'page': self.current_page,
                'text': match.group(0),
                'numbers': match.group(1)
            })

        # Author-year citations
        for match in self.patterns['author_year'].finditer(line):
            entity = Entity(
                entity_type=EntityType.CITATION,
                text=match.group(0),
                start_pos=self.current_position + match.start(),
                end_pos=self.current_position + match.end(),
                page_number=self.current_page,
                chapter_number=self.current_chapter,
                metadata={'citation_type': 'author_year', 'content': match.group(1)}
            )
            self.entities.append(entity)
            self.citation_stack.append({
                'entity': entity,
                'chapter': self.current_chapter,
                'page': self.current_page,
                'text': match.group(0)
            })

    def _process_bibliography_line(self, line: str, line_num: int) -> None:
        """Process bibliography/reference entries"""

        # Use regex to identify bibliography entries
        bib_match = self.patterns['bibliography_entry'].match(line)
        if bib_match:
            entity = Entity(
                entity_type=EntityType.BIBLIOGRAPHY_ENTRY,
                text=line,
                start_pos=self.current_position,
                end_pos=self.current_position + len(line),
                page_number=self.current_page,
                metadata={
                    'author': bib_match.group(1),
                    'content': bib_match.group(2)
                }
            )
            self.entities.append(entity)
        else:
            # Use GLiNER for more complex bibliography entries
            gliner_results = self.gliner_model.predict_entities(line, ['bibliography_entry', 'author', 'title', 'publisher', 'date'])
            for result in gliner_results:
                if result['label'] == 'bibliography_entry':
                    entity = Entity(
                        entity_type=EntityType.BIBLIOGRAPHY_ENTRY,
                        text=result['text'],
                        start_pos=self.current_position + result['start'],
                        end_pos=self.current_position + result['end'],
                        page_number=self.current_page,
                        confidence=result['score']
                    )
                    self.entities.append(entity)

    def _process_footnote_line(self, line: str, line_num: int) -> None:
        """Process footnote content"""

        entity = Entity(
            entity_type=EntityType.FOOTNOTE,
            text=line,
            start_pos=self.current_position,
            end_pos=self.current_position + len(line),
            page_number=self.current_page,
            chapter_number=self.current_chapter
        )
        self.entities.append(entity)

    def _is_header_footer(self, line: str) -> bool:
        """Determine if a line is a header or footer"""
        # Simple heuristics - can be enhanced
        return (len(line.split()) <= 5 and
                (any(word.isdigit() for word in line.split()) or
                 line.isupper() or
                 len(line) < 50))

    def _match_citations_to_bibliography(self) -> None:
        """
        Match citations to bibliography entries - O(m*n) worst case
        but optimized with hashing for common cases
        """
        print("Matching citations to bibliography...")

        # Create lookup tables for efficiency
        bibliography_entries = [e for e in self.entities if e.entity_type == EntityType.BIBLIOGRAPHY_ENTRY]

        # For numbered citations, create chapter-specific maps
        numbered_bib_by_chapter = {}
        for i, entry in enumerate(bibliography_entries):
            # Assume bibliography entries are ordered by appearance
            chapter_estimate = min(self.current_chapter, len(bibliography_entries))
            if chapter_estimate not in numbered_bib_by_chapter:
                numbered_bib_by_chapter[chapter_estimate] = {}
            numbered_bib_by_chapter[chapter_estimate][i + 1] = entry

        # Match each citation
        for citation_info in self.citation_stack:
            entity = citation_info['entity']
            chapter = citation_info['chapter']

            # Handle numbered citations
            if 'numbers' in citation_info['entity'].metadata:
                numbers_str = citation_info['entity'].metadata['numbers']
                numbers = self._parse_citation_numbers(numbers_str)

                for num in numbers:
                    # Try chapter-specific match first
                    if chapter in numbered_bib_by_chapter and num in numbered_bib_by_chapter[chapter]:
                        target_entry = numbered_bib_by_chapter[chapter][num]
                        relation = Relation(
                            relation_type="cites",
                            source_entity=entity,
                            target_entity=target_entry,
                            confidence=0.9,
                            metadata={'match_type': 'chapter_specific_number'}
                        )
                        self.relations.append(relation)
                    # Fallback to global numbering
                    elif num <= len(bibliography_entries):
                        target_entry = bibliography_entries[num - 1]
                        relation = Relation(
                            relation_type="cites",
                            source_entity=entity,
                            target_entity=target_entry,
                            confidence=0.7,
                            metadata={'match_type': 'global_number'}
                        )
                        self.relations.append(relation)

            # Handle author-year citations
            elif citation_info['entity'].metadata.get('citation_type') == 'author_year':
                # Use GLiNER relation extraction for fuzzy matching
                self._match_author_year_citation(entity, bibliography_entries)

        print(f"Created {len(self.relations)} citation-bibliography relations.")

    def _parse_citation_numbers(self, numbers_str: str) -> List[int]:
        """Parse citation number strings like '1-5,7,9-11' into individual numbers"""
        numbers = []
        parts = numbers_str.split(',')

        for part in parts:
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                numbers.extend(range(start, end + 1))
            else:
                numbers.append(int(part))

        return numbers

    def _match_author_year_citation(self, citation_entity: Entity, bibliography_entries: List[Entity]) -> None:
        """Use GLiNER to match author-year citations to bibliography entries"""

        citation_text = citation_entity.text
        best_match = None
        best_score = 0.0

        for bib_entry in bibliography_entries:
            # Use GLiNER relation extraction to determine match
            combined_text = f"{citation_text} -> {bib_entry.text}"

            # This would use your GLiNER relation extraction setup
            # For now, using simple text similarity as placeholder
            similarity = self._calculate_text_similarity(citation_text, bib_entry.text)

            if similarity > best_score and similarity > 0.5:
                best_match = bib_entry
                best_score = similarity

        if best_match:
            relation = Relation(
                relation_type="cites",
                source_entity=citation_entity,
                target_entity=best_match,
                confidence=best_score,
                metadata={'match_type': 'author_year_similarity'}
            )
            self.relations.append(relation)

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity calculation - can be enhanced with better algorithms"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _generate_xml(self) -> ET.Element:
        """Generate final XML output with all entities and relations"""

        root = ET.Element('book')

        # Add metadata
        metadata = ET.SubElement(root, 'metadata')

        # Find book-level entities
        book_titles = [e for e in self.entities if e.entity_type == EntityType.BOOK_TITLE]
        authors = [e for e in self.entities if e.entity_type == EntityType.AUTHOR]
        publishers = [e for e in self.entities if e.entity_type == EntityType.PUBLISHER]
        pub_dates = [e for e in self.entities if e.entity_type == EntityType.PUBLICATION_DATE]

        if book_titles:
            ET.SubElement(metadata, 'title').text = book_titles[0].text
        if authors:
            ET.SubElement(metadata, 'author').text = authors[0].text
        if publishers:
            ET.SubElement(metadata, 'publisher').text = publishers[0].text
        if pub_dates:
            ET.SubElement(metadata, 'publication_date').text = pub_dates[0].text

        # Add all entities
        entities_elem = ET.SubElement(root, 'entities')
        for entity in self.entities:
            entities_elem.append(entity.to_xml_element())

        # Add all relations
        relations_elem = ET.SubElement(root, 'relations')
        for relation in self.relations:
            relations_elem.append(relation.to_xml_element())

        return root

    def save_xml(self, xml_root: ET.Element, output_path: Path) -> None:
        """Save XML to file with proper formatting"""

        # Pretty print the XML
        ET.indent(xml_root, space="  ", level=0)

        tree = ET.ElementTree(xml_root)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)

        print(f"XML saved to: {output_path}")

def create_filename(book_title: str, author: str, pub_date: str, publisher: str) -> str:
    """Create filename from metadata with length constraints"""

    def truncate(text: str, max_len: int) -> str:
        text = re.sub(r'[^\w\s-]', '', text)  # Remove special chars
        return text[:max_len].strip()

    title_part = truncate(book_title, 50)
    author_part = truncate(author, 50)
    date_part = truncate(pub_date, 40)
    publisher_part = truncate(publisher, 20)

    filename = f"{title_part}_{author_part}_{date_part}_{publisher_part}.xml"

    # Ensure total length doesn't exceed 160 chars
    if len(filename) > 160:
        # Proportionally reduce each part
        excess = len(filename) - 160
        reduction_per_part = excess // 4

        title_part = title_part[:-reduction_per_part] if len(title_part) > reduction_per_part else title_part
        author_part = author_part[:-reduction_per_part] if len(author_part) > reduction_per_part else author_part
        date_part = date_part[:-reduction_per_part] if len(date_part) > reduction_per_part else date_part
        publisher_part = publisher_part[:-reduction_per_part] if len \
            (publisher_part) > reduction_per_part else publisher_part

        filename = f"{title_part}_{author_part}_{date_part}_{publisher_part}.xml"

    return filename

def main():
    """Main execution function"""

    # Initialize GLiNER model (placeholder - you'll use your actual model)
    from gliner import GLiNER
    gliner_model = GLiNER.from_pretrained("knowledgator/gliner-multitask-large-v0.5")

    # Create processor
    processor = BookProcessor(gliner_model)

    # Process PDF
    pdf_path = Path("input_book.pdf")  # Update with actual path
    xml_root = processor.process_pdf(pdf_path)

    # Create output filename
    # Extract metadata from processed entities
    book_titles = [e.text for e in processor.entities if e.entity_type == EntityType.BOOK_TITLE]
    authors = [e.text for e in processor.entities if e.entity_type == EntityType.AUTHOR]
    publishers = [e.text for e in processor.entities if e.entity_type == EntityType.PUBLISHER]
    pub_dates = [e.text for e in processor.entities if e.entity_type == EntityType.PUBLICATION_DATE]

    filename = create_filename(
        book_titles[0] if book_titles else "Unknown_Title",
        authors[0] if authors else "Unknown_Author",
        pub_dates[0] if pub_dates else "Unknown_Date",
        publishers[0] if publishers else "Unknown_Publisher"
    )

    # Save XML
    output_path = Path(filename)
    processor.save_xml(xml_root, output_path)

    print(f"Processing complete!")
    print(f"Found {len(processor.entities)} entities and {len(processor.relations)} relations")

if __name__ == "__main__":
    main()