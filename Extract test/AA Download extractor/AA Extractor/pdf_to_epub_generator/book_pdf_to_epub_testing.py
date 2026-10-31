"""
PDF to XML Book Processor - Linear Time Complexity Architecture
Processes academic PDFs to extract structured XML with entities and relations
MODIFIED VERSION WITH EXTENSIVE PRINT STATEMENTS FOR DEBUGGING
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import PyPDF2
from pathlib import Path
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

    def __str__(self):
        """String representation for printing"""
        return f"Entity({self.entity_type.value}: '{self.text[:50]}...' if len(self.text) > 50 else self.text, page={self.page_number}, chapter={self.chapter_number}, confidence={self.confidence:.3f})"


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

    def __str__(self):
        """String representation for printing"""
        source_text = self.source_entity.text[:30] + "..." if len(self.source_entity.text) > 30 else self.source_entity.text
        target_text = self.target_entity.text[:30] + "..." if len(self.target_entity.text) > 30 else self.target_entity.text
        return f"Relation({self.relation_type}: '{source_text}' -> '{target_text}', confidence={self.confidence:.3f})"


class BookProcessor:
    """Main processor class - Linear time complexity O(n)"""

    def __init__(self, gliner_model):
        print("🔧 Initializing BookProcessor...")
        self.gliner_model = gliner_model
        self.entities: List[Entity] = []
        self.relations: List[Relation] = []
        self.citation_stack: List[Dict] = []  # For matching citations to bibliography
        self.current_position = 0
        self.current_page = 1
        self.current_chapter = 1

        # Compiled regex patterns for efficiency
        print("📝 Compiling regex patterns...")
        self.patterns = self._compile_patterns()
        print(f"✅ Compiled {len(self.patterns)} regex patterns")

        # Entity labels for GLiNER
        self.entity_labels = [
            "book_title", "chapter_title", "author", "publisher", "publication_date",
            "citation", "footnote", "endnote", "quotation", "page_number",
            "chapter_number", "bibliography_entry", "table", "figure"
        ]
        print(f"🏷️  Entity labels: {self.entity_labels}")

        # Relation types for GLiNER
        self.relation_types = [
            {"relation": "cites", "pairs_filter": [("citation", "bibliography_entry")]},
            {"relation": "appears_in_chapter", "pairs_filter": [("citation", "chapter_title")]},
            {"relation": "authored", "pairs_filter": [("author", "book_title")]},
            {"relation": "published_by", "pairs_filter": [("book_title", "publisher")]},
            {"relation": "contains", "pairs_filter": [("chapter_title", "paragraph")]},
            {"relation": "footnote_of", "pairs_filter": [("footnote", "paragraph")]},
        ]
        print(f"🔗 Relation types: {[r['relation'] for r in self.relation_types]}")
        print("✅ BookProcessor initialized successfully!\n")

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile all regex patterns once for efficiency"""
        patterns = {
            # Citation patterns
            'numbered_citation': re.compile(r'\[(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\]'),
            'author_year': re.compile(r'\(([A-Z][a-z]+(?:\s+(?:&|and)\s+[A-Z][a-z]+)*,?\s+\d{4}[a-z]?)\)'),
            'footnote_marker': re.compile(r'(\d+)'),

            # Structure patterns
            'chapter_title': re.compile(r'^(?:Chapter\s+)?(\d+|[IVX]+)[\.\s]+(.+)$', re.MULTILINE),
            'page_number': re.compile(r'^\s*(\d+|[ivx]+)\s*$', re.MULTILINE),
            'header_footer': re.compile(r'^(.+?)\s+(\d+)$'),

            # Bibliography patterns
            'bibliography_start': re.compile(r'^(?:Bibliography|References|Works\s+Cited|Endnotes)',
                                             re.MULTILINE | re.IGNORECASE),
            'bibliography_entry': re.compile(r'^([A-Z][a-zA-Z\s,]+)\.\s+(.+)$', re.MULTILINE),
        }

        for pattern_name, pattern in patterns.items():
            print(f"  ✓ Compiled pattern: {pattern_name}")

        return patterns

    def process_pdf(self, pdf_path: Path) -> ET.Element:
        """
        Main processing function - Linear time O(n) where n is text length
        Single pass through the document with state tracking
        """
        print(f"\n📚 Starting PDF processing: {pdf_path}")
        print("=" * 60)

        # Extract text from PDF
        print("📄 Extracting text from PDF...")
        full_text = self._extract_text_from_pdf(pdf_path)
        print(f"✅ Extracted {len(full_text)} characters from PDF")

        # Single linear pass through text
        print("\n🔍 Starting linear scan of document...")
        self._linear_scan(full_text)

        # Match citations to bibliography (using the stack we built)
        print(f"\n🔗 Matching {len(self.citation_stack)} citations to bibliography...")
        self._match_citations_to_bibliography()

        # Generate XML output
        print("\n📋 Generating XML output...")
        xml_root = self._generate_xml()

        print("\n" + "=" * 60)
        print("🎉 PDF processing completed successfully!")
        print(f"📊 Final Statistics:")
        print(f"   • Total entities: {len(self.entities)}")
        print(f"   • Total relations: {len(self.relations)}")
        print(f"   • Citations processed: {len(self.citation_stack)}")

        return xml_root

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text while preserving structure information"""
        print(f"📖 Opening PDF file: {pdf_path}")

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            print(f"📄 PDF has {total_pages} pages")

            full_text = ""

            for page_num, page in enumerate(pdf_reader.pages, 1):
                print(f"  📄 Processing page {page_num}/{total_pages}...")
                page_text = page.extract_text()

                # Add page markers for tracking
                full_text += f"<PAGE_{page_num}>\n{page_text}\n</PAGE_{page_num}>\n"
                print(f"     ✓ Extracted {len(page_text)} characters from page {page_num}")

        print(f"✅ Text extraction complete. Total characters: {len(full_text)}")
        return full_text

    def _linear_scan(self, text: str) -> None:
        """
        Single pass through text - O(n) complexity
        Uses state machine to track context while scanning
        """
        print("🔍 Starting linear scan...")
        print("📍 Scan progress:")

        lines = text.split('\n')
        in_bibliography = False
        in_footnotes = False
        current_chapter_title = None
        processed_lines = 0

        print(f"   📄 Total lines to process: {len(lines)}")

        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            processed_lines += 1

            # Progress indicator
            if processed_lines % 100 == 0:
                print(f"   📍 Processed {processed_lines} lines...")

            # Update position tracking
            self.current_position += len(line)

            # Check for page markers
            if line.startswith('<PAGE_') and line.endswith('>'):
                new_page = int(line.replace('<PAGE_', '').replace('>', ''))
                print(f"📄 Page transition: {self.current_page} -> {new_page}")
                self.current_page = new_page
                continue

            # State transitions
            if self.patterns['bibliography_start'].search(line):
                print(f"📚 BIBLIOGRAPHY SECTION DETECTED at line {line_num}: '{line}'")
                in_bibliography = True
                continue

            # Process based on current state
            if in_bibliography:
                self._process_bibliography_line(line, line_num)
            elif in_footnotes:
                self._process_footnote_line(line, line_num)
            else:
                self._process_main_text_line(line, line_num)

        print(f"✅ Linear scan complete!")
        print(f"   📊 Processed {processed_lines} lines")
        print(f"   🏷️  Found {len(self.entities)} entities")
        print(f"   📚 Citations in stack: {len(self.citation_stack)}")

    def _process_main_text_line(self, line: str, line_num: int) -> None:
        """Process a line from main text content"""

        # Check for chapter titles
        chapter_match = self.patterns['chapter_title'].match(line)
        if chapter_match:
            old_chapter = self.current_chapter
            self.current_chapter = int(chapter_match.group(1)) if chapter_match.group(
                1).isdigit() else self.current_chapter

            print(f"📖 CHAPTER DETECTED (line {line_num}):")
            print(f"   Chapter number: {old_chapter} -> {self.current_chapter}")
            print(f"   Chapter title: '{chapter_match.group(2)}'")

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
            print(f"   ✅ Added entity: {entity}")
            return

        # Check for page headers/footers
        if self._is_header_footer(line):
            print(f"📋 HEADER/FOOTER detected (line {line_num}): '{line}'")
            entity = Entity(
                entity_type=EntityType.HEADER,
                text=line,
                start_pos=self.current_position,
                end_pos=self.current_position + len(line),
                page_number=self.current_page,
                chapter_number=self.current_chapter
            )
            self.entities.append(entity)
            print(f"   ✅ Added entity: {entity}")
            return

        # Process regular paragraph content
        self._process_paragraph_content(line, line_num)

    def _process_paragraph_content(self, line: str, line_num: int) -> None:
        """Process paragraph content for citations and other entities"""

        if len(line) < 10:  # Skip very short lines
            return

        print(f"\n📝 Processing paragraph content (line {line_num}):")
        print(f"   Text preview: '{line[:100]}{'...' if len(line) > 100 else ''}' ")

        # Use GLiNER for entity detection
        print("   🤖 Running GLiNER entity detection...")
        try:
            gliner_results = self.gliner_model.predict_entities(line, self.entity_labels)
            print(f"   📊 GLiNER found {len(gliner_results)} entities")

            # Convert GLiNER results to our Entity objects
            for i, result in enumerate(gliner_results):
                entity_type_str = result['label']
                print(f"   🏷️  GLiNER Entity {i+1}:")
                print(f"      Type: {entity_type_str}")
                print(f"      Text: '{result['text']}'")
                print(f"      Score: {result['score']:.3f}")
                print(f"      Position: {result['start']}-{result['end']}")

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
                    print(f"      ✅ Added to entities list: {entity}")

                    # Add to citation stack if it's a citation
                    if entity_type == EntityType.CITATION:
                        citation_info = {
                            'entity': entity,
                            'chapter': self.current_chapter,
                            'page': self.current_page,
                            'text': result['text']
                        }
                        self.citation_stack.append(citation_info)
                        print(f"      📚 Added to citation stack: {citation_info}")
                else:
                    print(f"      ❌ Unknown entity type: {entity_type_str}")

        except Exception as e:
            print(f"   ❌ GLiNER error: {e}")

        # Additional regex-based detection for patterns GLiNER might miss
        print("   🔍 Running regex-based citation detection...")
        self._detect_citation_patterns(line, line_num)

    def _detect_citation_patterns(self, line: str, line_num: int) -> None:
        """Detect specific citation patterns using regex"""

        # Numbered citations
        numbered_matches = list(self.patterns['numbered_citation'].finditer(line))
        if numbered_matches:
            print(f"   📊 Found {len(numbered_matches)} numbered citations:")

        for i, match in enumerate(numbered_matches):
            print(f"   📋 Numbered Citation {i+1}:")
            print(f"      Full match: '{match.group(0)}'")
            print(f"      Numbers: '{match.group(1)}'")
            print(f"      Position: {match.start()}-{match.end()}")

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

            citation_info = {
                'entity': entity,
                'chapter': self.current_chapter,
                'page': self.current_page,
                'text': match.group(0),
                'numbers': match.group(1)
            }
            self.citation_stack.append(citation_info)
            print(f"      ✅ Added entity: {entity}")
            print(f"      📚 Added to citation stack")

        # Author-year citations
        author_year_matches = list(self.patterns['author_year'].finditer(line))
        if author_year_matches:
            print(f"   📊 Found {len(author_year_matches)} author-year citations:")

        for i, match in enumerate(author_year_matches):
            print(f"   📋 Author-Year Citation {i+1}:")
            print(f"      Full match: '{match.group(0)}'")
            print(f"      Content: '{match.group(1)}'")
            print(f"      Position: {match.start()}-{match.end()}")

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

            citation_info = {
                'entity': entity,
                'chapter': self.current_chapter,
                'page': self.current_page,
                'text': match.group(0)
            }
            self.citation_stack.append(citation_info)
            print(f"      ✅ Added entity: {entity}")
            print(f"      📚 Added to citation stack")

    def _process_bibliography_line(self, line: str, line_num: int) -> None:
        """Process bibliography/reference entries"""

        print(f"📚 Processing bibliography line {line_num}:")
        print(f"   Text: '{line[:100]}{'...' if len(line) > 100 else ''}'")

        # Use regex to identify bibliography entries
        bib_match = self.patterns['bibliography_entry'].match(line)
        if bib_match:
            print(f"   ✅ REGEX match found:")
            print(f"      Author: '{bib_match.group(1)}'")
            print(f"      Content: '{bib_match.group(2)}'")

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
            print(f"      ✅ Added entity: {entity}")
        else:
            # Use GLiNER for more complex bibliography entries
            print(f"   🤖 No regex match, trying GLiNER...")
            try:
                gliner_results = self.gliner_model.predict_entities(line,
                                                                    ['bibliography_entry', 'author', 'title', 'publisher',
                                                                     'date'])
                print(f"   📊 GLiNER found {len(gliner_results)} entities in bibliography line")

                for i, result in enumerate(gliner_results):
                    print(f"   🏷️  Bibliography Entity {i+1}:")
                    print(f"      Type: {result['label']}")
                    print(f"      Text: '{result['text']}'")
                    print(f"      Score: {result['score']:.3f}")

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
                        print(f"      ✅ Added entity: {entity}")

            except Exception as e:
                print(f"   ❌ GLiNER error in bibliography: {e}")

    def _process_footnote_line(self, line: str, line_num: int) -> None:
        """Process footnote content"""

        print(f"📝 Processing footnote line {line_num}:")
        print(f"   Text: '{line[:100]}{'...' if len(line) > 100 else ''}'")

        entity = Entity(
            entity_type=EntityType.FOOTNOTE,
            text=line,
            start_pos=self.current_position,
            end_pos=self.current_position + len(line),
            page_number=self.current_page,
            chapter_number=self.current_chapter
        )
        self.entities.append(entity)
        print(f"   ✅ Added footnote entity: {entity}")

    def _is_header_footer(self, line: str) -> bool:
        """Determine if a line is a header or footer"""
        # Simple heuristics - can be enhanced
        is_header_footer = (len(line.split()) <= 5 and
                (any(word.isdigit() for word in line.split()) or
                 line.isupper() or
                 len(line) < 50))

        if is_header_footer:
            print(f"   🎯 Identified as header/footer: '{line}'")

        return is_header_footer

    def _match_citations_to_bibliography(self) -> None:
        """
        Match citations to bibliography entries - O(m*n) worst case
        but optimized with hashing for common cases
        """
        print("\n🔗 Starting citation-bibliography matching...")
        print(f"   📚 Citations to match: {len(self.citation_stack)}")

        # Create lookup tables for efficiency
        bibliography_entries = [e for e in self.entities if e.entity_type == EntityType.BIBLIOGRAPHY_ENTRY]
        print(f"   📖 Bibliography entries available: {len(bibliography_entries)}")

        if not bibliography_entries:
            print("   ⚠️  No bibliography entries found - skipping citation matching")
            return

        print("   📚 Bibliography entries:")
        for i, entry in enumerate(bibliography_entries):
            print(f"      {i+1}. '{entry.text[:80]}{'...' if len(entry.text) > 80 else ''}'")

        # For numbered citations, create chapter-specific maps
        numbered_bib_by_chapter = {}
        for i, entry in enumerate(bibliography_entries):
            # Assume bibliography entries are ordered by appearance
            chapter_estimate = min(self.current_chapter, len(bibliography_entries))
            if chapter_estimate not in numbered_bib_by_chapter:
                numbered_bib_by_chapter[chapter_estimate] = {}
            numbered_bib_by_chapter[chapter_estimate][i + 1] = entry

        print(f"   📊 Created chapter-specific lookup for {len(numbered_bib_by_chapter)} chapters")

        # Match each citation
        matched_count = 0
        for cite_idx, citation_info in enumerate(self.citation_stack):
            print(f"\n   🔍 Processing citation {cite_idx + 1}/{len(self.citation_stack)}:")
            entity = citation_info['entity']
            chapter = citation_info['chapter']

            print(f"      Citation text: '{entity.text}'")
            print(f"      Chapter: {chapter}, Page: {citation_info['page']}")
            print(f"      Metadata: {entity.metadata}")

            # Handle numbered citations
            if 'numbers' in citation_info['entity'].metadata:
                numbers_str = citation_info['entity'].metadata['numbers']
                numbers = self._parse_citation_numbers(numbers_str)
                print(f"      📊 Parsed numbers: {numbers}")

                for num in numbers:
                    print(f"         🔍 Matching number {num}...")

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
            print(f"      ✅ AUTHOR-YEAR MATCH: {relation}")
        else:
            print(f"      ❌ No suitable match found for author-year citation")

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity calculation - can be enhanced with better algorithms"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        similarity = len(intersection) / len(union)
        print(f"         📊 Text similarity calculation:")
        print(f"            Text1 words: {words1}")
        print(f"            Text2 words: {words2}")
        print(f"            Intersection: {intersection}")
        print(f"            Union size: {len(union)}")
        print(f"            Similarity: {similarity:.3f}")

        return similarity

    def _generate_xml(self) -> ET.Element:
        """Generate final XML output with all entities and relations"""

        print("📋 Generating XML structure...")
        root = ET.Element('book')

        # Add metadata
        print("   📝 Creating metadata section...")
        metadata = ET.SubElement(root, 'metadata')

        # Find book-level entities
        book_titles = [e for e in self.entities if e.entity_type == EntityType.BOOK_TITLE]
        authors = [e for e in self.entities if e.entity_type == EntityType.AUTHOR]
        publishers = [e for e in self.entities if e.entity_type == EntityType.PUBLISHER]
        pub_dates = [e for e in self.entities if e.entity_type == EntityType.PUBLICATION_DATE]

        print(f"   📚 Found metadata:")
        print(f"      Book titles: {len(book_titles)}")
        print(f"      Authors: {len(authors)}")
        print(f"      Publishers: {len(publishers)}")
        print(f"      Publication dates: {len(pub_dates)}")

        if book_titles:
            title_elem = ET.SubElement(metadata, 'title')
            title_elem.text = book_titles[0].text
            print(f"      ✅ Added title: '{book_titles[0].text}'")
        if authors:
            author_elem = ET.SubElement(metadata, 'author')
            author_elem.text = authors[0].text
            print(f"      ✅ Added author: '{authors[0].text}'")
        if publishers:
            publisher_elem = ET.SubElement(metadata, 'publisher')
            publisher_elem.text = publishers[0].text
            print(f"      ✅ Added publisher: '{publishers[0].text}'")
        if pub_dates:
            date_elem = ET.SubElement(metadata, 'publication_date')
            date_elem.text = pub_dates[0].text
            print(f"      ✅ Added publication date: '{pub_dates[0].text}'")

        # Add all entities
        print(f"\n   🏷️  Adding {len(self.entities)} entities to XML...")
        entities_elem = ET.SubElement(root, 'entities')

        # Group entities by type for better organization
        entities_by_type = {}
        for entity in self.entities:
            entity_type = entity.entity_type.value
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            entities_by_type[entity_type].append(entity)

        print(f"   📊 Entities by type:")
        for entity_type, entity_list in entities_by_type.items():
            print(f"      {entity_type}: {len(entity_list)}")

        for entity in self.entities:
            entities_elem.append(entity.to_xml_element())

        # Add all relations
        print(f"\n   🔗 Adding {len(self.relations)} relations to XML...")
        relations_elem = ET.SubElement(root, 'relations')

        # Group relations by type
        relations_by_type = {}
        for relation in self.relations:
            rel_type = relation.relation_type
            if rel_type not in relations_by_type:
                relations_by_type[rel_type] = []
            relations_by_type[rel_type].append(relation)

        print(f"   📊 Relations by type:")
        for rel_type, rel_list in relations_by_type.items():
            print(f"      {rel_type}: {len(rel_list)}")
            for i, rel in enumerate(rel_list):
                print(f"         {i+1}. {rel}")

        for relation in self.relations:
            relations_elem.append(relation.to_xml_element())

        print("✅ XML generation complete!")
        return root

    def save_xml(self, xml_root: ET.Element, output_path: Path) -> None:
        """Save XML to file with proper formatting"""

        print(f"\n💾 Saving XML to file: {output_path}")

        # Pretty print the XML
        print("   🎨 Formatting XML with proper indentation...")
        ET.indent(xml_root, space="  ", level=0)

        print("   💾 Writing to file...")
        tree = ET.ElementTree(xml_root)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)

        # Verify file was created
        if output_path.exists():
            file_size = output_path.stat().st_size
            print(f"✅ XML successfully saved!")
            print(f"   📁 File: {output_path}")
            print(f"   📊 Size: {file_size:,} bytes")
        else:
            print(f"❌ Error: XML file was not created!")

    def print_final_summary(self):
        """Print a comprehensive summary of all detected entities and relations"""

        print("\n" + "="*80)
        print("📊 FINAL PROCESSING SUMMARY")
        print("="*80)

        print(f"\n🏷️  ENTITIES SUMMARY ({len(self.entities)} total):")
        print("-" * 50)

        # Group entities by type
        entities_by_type = {}
        for entity in self.entities:
            entity_type = entity.entity_type.value
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            entities_by_type[entity_type].append(entity)

        for entity_type, entity_list in sorted(entities_by_type.items()):
            print(f"\n📋 {entity_type.upper()} ({len(entity_list)} entities):")
            for i, entity in enumerate(entity_list[:5]):  # Show first 5 of each type
                print(f"   {i+1}. '{entity.text[:100]}{'...' if len(entity.text) > 100 else ''}' ")
                print(f"      (Page: {entity.page_number}, Chapter: {entity.chapter_number}, Confidence: {entity.confidence:.3f})")
            if len(entity_list) > 5:
                print(f"   ... and {len(entity_list) - 5} more")

        print(f"\n🔗 RELATIONS SUMMARY ({len(self.relations)} total):")
        print("-" * 50)

        # Group relations by type
        relations_by_type = {}
        for relation in self.relations:
            rel_type = relation.relation_type
            if rel_type not in relations_by_type:
                relations_by_type[rel_type] = []
            relations_by_type[rel_type].append(relation)

        for rel_type, rel_list in sorted(relations_by_type.items()):
            print(f"\n🔄 {rel_type.upper()} ({len(rel_list)} relations):")
            for i, relation in enumerate(rel_list):
                source_preview = relation.source_entity.text[:40] + "..." if len(relation.source_entity.text) > 40 else relation.source_entity.text
                target_preview = relation.target_entity.text[:40] + "..." if len(relation.target_entity.text) > 40 else relation.target_entity.text
                print(f"   {i+1}. '{source_preview}' -> '{target_preview}'")
                print(f"      (Confidence: {relation.confidence:.3f}, Match type: {relation.metadata.get('match_type', 'N/A')})")

        print(f"\n📚 CITATION PROCESSING SUMMARY:")
        print("-" * 50)
        print(f"   Total citations detected: {len(self.citation_stack)}")
        print(f"   Citation-bibliography relations: {len([r for r in self.relations if r.relation_type == 'cites'])}")
        print(f"   Success rate: {len([r for r in self.relations if r.relation_type == 'cites']) / max(1, len(self.citation_stack)) * 100:.1f}%")

        # Show citation types breakdown
        citation_types = {}
        for cite_info in self.citation_stack:
            cite_type = cite_info['entity'].metadata.get('citation_type', 'unknown')
            citation_types[cite_type] = citation_types.get(cite_type, 0) + 1

        print(f"   Citation types:")
        for cite_type, count in citation_types.items():
            print(f"      {cite_type}: {count}")


def create_filename(book_title: str, author: str, pub_date: str, publisher: str) -> str:
    """Create filename from metadata with length constraints"""

    print(f"\n📁 Creating filename from metadata...")
    print(f"   Title: '{book_title}'")
    print(f"   Author: '{author}'")
    print(f"   Date: '{pub_date}'")
    print(f"   Publisher: '{publisher}'")

    def truncate(text: str, max_len: int) -> str:
        text = re.sub(r'[^\w\s-]', '', text)  # Remove special chars
        truncated = text[:max_len].strip()
        if len(text) > max_len:
            print(f"      Truncated '{text}' to '{truncated}'")
        return truncated

    title_part = truncate(book_title, 50)
    author_part = truncate(author, 50)
    date_part = truncate(pub_date, 40)
    publisher_part = truncate(publisher, 20)

    filename = f"{title_part}_{author_part}_{date_part}_{publisher_part}.xml"
    print(f"   Initial filename: '{filename}' (length: {len(filename)})")

    # Ensure total length doesn't exceed 160 chars
    if len(filename) > 160:
        print(f"   Filename too long ({len(filename)} chars), reducing...")
        excess = len(filename) - 160
        reduction_per_part = excess // 4

        title_part = title_part[:-reduction_per_part] if len(title_part) > reduction_per_part else title_part
        author_part = author_part[:-reduction_per_part] if len(author_part) > reduction_per_part else author_part
        date_part = date_part[:-reduction_per_part] if len(date_part) > reduction_per_part else date_part
        publisher_part = publisher_part[:-reduction_per_part] if len(
            publisher_part) > reduction_per_part else publisher_part

        filename = f"{title_part}_{author_part}_{date_part}_{publisher_part}.xml"
        print(f"   Reduced filename: '{filename}' (length: {len(filename)})")

    print(f"✅ Final filename: '{filename}'")
    return filename


def main():
    """Main execution function"""

    print("🚀 Starting PDF to XML Book Processor")
    print("="*60)

    start_time = time.time()

    # Initialize GLiNER model (placeholder - you'll use your actual model)
    print("🤖 Initializing GLiNER model...")
    try:
        from gliner import GLiNER
        gliner_model = GLiNER.from_pretrained("knowledgator/gliner-multitask-large-v0.5")
        print("✅ GLiNER model loaded successfully!")
    except Exception as e:
        print(f"❌ Error loading GLiNER model: {e}")
        print("   Using mock model for demonstration...")
        # Create a mock model for demonstration
        class MockGLiNER:
            def predict_entities(self, text, labels):
                return []  # Return empty list for demonstration
        gliner_model = MockGLiNER()

    # Create processor
    processor = BookProcessor(gliner_model)

    # Process PDF
    pdf_path = Path("input_book.pdf")  # Update with actual path
    print(f"\n📚 Target PDF: {pdf_path}")

    if not pdf_path.exists():
        print(f"❌ PDF file not found: {pdf_path}")
        print("   Please update the path in main() function")
        return

    # Main processing
    xml_root = processor.process_pdf(pdf_path)

    # Print comprehensive summary
    processor.print_final_summary()

    # Create output filename
    print(f"\n📁 Extracting metadata for filename...")
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

    # Final timing and statistics
    end_time = time.time()
    processing_time = end_time - start_time

    print(f"\n🎉 PROCESSING COMPLETE!")
    print("="*60)
    print(f"⏱️  Total processing time: {processing_time:.2f} seconds")
    print(f"📊 Final Statistics:")
    print(f"   • Total entities detected: {len(processor.entities)}")
    print(f"   • Total relations created: {len(processor.relations)}")
    print(f"   • Citations processed: {len(processor.citation_stack)}")
    print(f"   • Output file: {output_path}")
    print(f"   • File size: {output_path.stat().st_size:,} bytes" if output_path.exists() else "   • File not created")

    print(f"\n🔍 Entity breakdown:")
    entity_counts = {}
    for entity in processor.entities:
        entity_type = entity.entity_type.value
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

    for entity_type, count in sorted(entity_counts.items()):
        print(f"   • {entity_type}: {count}")

    print(f"\n🔗 Relation breakdown:")
    relation_counts = {}
    for relation in processor.relations:
        rel_type = relation.relation_type
        relation_counts[rel_type] = relation_counts.get(rel_type, 0) + 1

    for rel_type, count in sorted(relation_counts.items()):
        print(f"   • {rel_type}: {count}")


if __name__ == "__main__":
    main()