#!/usr/bin/env python3
"""Extract readable text from an authorized local PDF or EPUB file."""
import json
import sys
from pathlib import Path

MAX_CHARS = 1_200_000

def clean_text(value: str) -> str:
    text = (value or '').replace('\r', '')
    lines = [' '.join(line.split()) for line in text.split('\n')]
    return '\n'.join(line for line in lines if line).strip()[:MAX_CHARS]

def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return clean_text('\n\n'.join(page.extract_text() or '' for page in reader.pages))

def extract_epub(path: Path) -> str:
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup
    book = epub.read_epub(str(path), options={'ignore_ncx': True})
    chunks = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        chunks.append(soup.get_text('\n'))
    return clean_text('\n\n'.join(chunks))

def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({'ok': False, 'error': 'A single book path is required'}))
        return 2
    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.is_file():
        print(json.dumps({'ok': False, 'error': 'Book file does not exist'}))
        return 2
    suffix = path.suffix.lower()
    try:
        if suffix == '.pdf':
            text = extract_pdf(path)
        elif suffix == '.epub':
            text = extract_epub(path)
        else:
            raise ValueError('Only PDF and EPUB extraction is supported by this helper')
        if not text:
            raise ValueError('No readable text was found in the book')
        print(json.dumps({'ok': True, 'text': text}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
