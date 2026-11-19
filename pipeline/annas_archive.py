"""Experimental metadata search using Anna's Archive's public HTML pages."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment
import requests

from .http import Client


class AnnaSearchError(ValueError):
    """A safe-to-display explanation when this source cannot be searched."""


def record_md5(url: str) -> str:
    """Validate a saved record reference; navigation uses the configured site host."""
    if not isinstance(url, str):
        raise ValueError("Choose a valid Anna's Archive book-page link.")
    parts = urlsplit(url)
    match = re.fullmatch(r'/md5/([a-fA-F0-9]{32})', parts.path)
    if (parts.scheme not in ('https', 'http') or not parts.hostname or not match
            or parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError("Choose a valid Anna's Archive /md5/ book-page link.")
    return match.group(1).lower()


def parse_results(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    # Some result cards are shipped inside comments and revealed by the site.
    for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
        if 'js-vim-focus' in comment and '/md5/' in comment:
            comment.replace_with(BeautifulSoup(str(comment), 'html.parser'))

    results, seen = [], set()
    for card in soup.select('a.js-vim-focus[href]'):
        path = urlsplit(card['href']).path
        if not re.fullmatch(r'/md5/[a-fA-F0-9]{32}', path):
            continue
        path = path.lower()
        title_node = card.find('h3')
        if path in seen:
            continue
        if title_node is not None:
            author_node = card.select_one('.italic')
            info_node = card.select_one('.text-gray-500')
            publisher_node = title_node.find_next_sibling('div')
            if publisher_node and 'italic' in publisher_node.get('class', []):
                publisher_node = None
        elif card.find_parent(class_='js-aarecord-list-outer') is not None:
            # Current layout: the title is the anchor itself; metadata sits beside it.
            title_node = card
            details = card.parent.parent
            author_icon = details.select_one('span[class*="mdi--user-edit"]')
            publisher_icon = details.select_one('span[class*="mdi--company"]')
            author_node = author_icon.find_parent('a') if author_icon else None
            publisher_node = publisher_icon.find_parent('a') if publisher_icon else None
            info_node = details.select_one('div.text-gray-800')
        else:
            continue
        title = title_node.get_text(' ', strip=True)
        if not title:
            continue
        authors = author_node.get_text(' ', strip=True) if author_node else ''
        # Preserve commas inside names; semicolons delimit authors in many cards.
        authors = [a.strip() for a in authors.split(';') if a.strip()]
        info = info_node.get_text(' ', strip=True) if info_node else ''
        info = info.replace('·', ',')
        extension = re.search(r'(?:^|,)\s*\.?([a-z0-9]+)\s*(?:,|$)', info, re.I)
        listed_format = extension.group(1).lower() if extension else None
        publisher = publisher_node.get_text(' ', strip=True) if publisher_node else ''
        years = re.findall(r'\b(?:18|19|20)\d{2}\b', publisher)
        results.append(dict(
            title=title, authors=authors, year=int(years[-1]) if years else None,
            formats=[listed_format] if listed_format in ('epub', 'pdf') else ['epub', 'pdf'],
            listed_format=listed_format, source_url=base_url.rstrip('/') + path,
            availability='Browser download; availability not checked',
        ))
        seen.add(path)
        if len(results) == 8:
            break
    if results:
        return results

    page_title = soup.title.get_text(' ', strip=True).lower() if soup.title else ''
    if (soup.select_one('#challenge-form, #cf-challenge-running, .cf-turnstile')
            or any(marker in page_title for marker in ('just a moment', 'verify', 'access denied', 'ddos-guard'))):
        raise AnnaSearchError("Anna's Archive requires browser verification. Open its search page in your browser.")
    text = soup.get_text(' ', strip=True).lower()
    # A changed layout or an error page must not silently become zero matches.
    if soup.select_one('form input[name="q"]') and any(
            marker in text for marker in ('no results found', 'no files found', 'no results match', 'no matches found')):
        return []
    raise AnnaSearchError("Anna's Archive returned an unrecognized search page; its layout may have changed.")


def validate_base_url(base_url: str) -> None:
    parts = urlsplit(base_url)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username
            or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise AnnaSearchError('Set annas_archive_url in config.yaml to a valid HTTP(S) site address.')


def lookup(client: Client, query: str, base_url: str) -> list[dict]:
    validate_base_url(base_url)
    try:
        response = client.get(base_url.rstrip('/') + '/search', params={'q': query, 'check': '1'})
        if response.status_code in (403, 429):
            raise AnnaSearchError("Anna's Archive blocked or rate-limited this search. Try its page in your browser.")
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AnnaSearchError("Anna's Archive could not be reached. Check annas_archive_url in config.yaml or try again later.") from exc
    return parse_results(response.text, base_url)
