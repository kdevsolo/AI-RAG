from langchain_text_splitters import RecursiveCharacterTextSplitter


def split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into overlapping chunks ready for embedding.

    A plain function, not a class: chunk_size/chunk_overlap vary per call
    (driven by config, but callers may override), and there's no state to
    hold between calls that would justify an instance.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_text(text)
