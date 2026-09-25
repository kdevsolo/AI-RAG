from dataclasses import dataclass


@dataclass
class IngestDocumentInput:
    document_id: str
    file_path: str  # full path under UPLOAD_DIR, not just the bare filename


@dataclass
class MarkFailedInput:
    document_id: str
    error: str
