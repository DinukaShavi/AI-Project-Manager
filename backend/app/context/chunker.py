import re
from typing import Any, Dict, List

class TextChunker:
    def __init__(self, default_chunk_size: int = 500, default_overlap: int = 50):
        self.default_chunk_size = default_chunk_size
        self.default_overlap = default_overlap

    def chunk_text(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> List[Dict[str, Any]]:
        """Split raw text into overlapping semantic chunks preserving line/sentence boundaries."""
        size = chunk_size or self.default_chunk_size
        overlap = chunk_overlap or self.default_overlap

        if not text or not text.strip():
            return []

        # Split into paragraphs/sentences
        paragraphs = re.split(r'\n{2,}|\n', text)
        chunks = []
        current_chunk = []
        current_len = 0
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            para_words = para.split()
            para_len = len(para_words)

            if current_len + para_len > size and current_chunk:
                # Store completed chunk
                chunk_str = " ".join(current_chunk)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "content": chunk_str,
                    "token_count": current_len
                })
                chunk_idx += 1

                # Calculate overlap words for next chunk
                overlap_words = current_chunk[-overlap:] if overlap < len(current_chunk) else current_chunk
                current_chunk = overlap_words + [para]
                current_len = len(current_chunk)
            else:
                current_chunk.append(para)
                current_len += para_len

        if current_chunk:
            chunk_str = " ".join(current_chunk)
            chunks.append({
                "chunk_index": chunk_idx,
                "content": chunk_str,
                "token_count": current_len
            })

        return chunks
