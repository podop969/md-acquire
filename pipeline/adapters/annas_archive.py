"""The exact file explicitly selected in an Anna's Archive search result."""
from .base import Adapter
from ..annas_archive import record_md5, validate_base_url
from ..models import Candidate


class AnnasArchiveAdapter(Adapter):
    name = 'annas_archive'

    def lookup(self, client, spec):
        if spec.source != self.name:
            return []
        md5 = record_md5(spec.source_url)
        validate_base_url(self.cfg.annas_archive_url)
        if spec.source_format not in ('pdf', 'epub') or spec.source_format not in spec.formats:
            raise ValueError('The selected Anna file must be a requested PDF or EPUB format.')
        return [Candidate(
            source=self.name, url=self.cfg.annas_archive_url.rstrip('/') + '/md5/' + md5,
            fmt=spec.source_format, title=spec.title, score=1000,
            license='Not verified (user-selected Anna’s Archive file)',
            extra={'md5': md5, 'selected_source_url': spec.source_url, 'transport': 'browser'},
        )]
