"""文本分块:面向 RAG 的字符级滑动窗口分块。

按字符切分(对中英文均适用),优先在段落/句子边界回退,窗口间留重叠以保留上下文。
"""

# 优先在这些边界处断开(从强到弱)
_BREAKS = ("\n\n", "\n", "。", "!", "?", ".", "!", "?", " ")


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """把长文本切成若干重叠块。返回去空后的非空块列表。"""
    text = text.strip()
    if not text:
        return []
    if overlap >= chunk_size:
        overlap = chunk_size // 4

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            end = _best_break(text, start, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def _best_break(text: str, start: int, end: int) -> int:
    """在 [start, end] 窗口尾部寻找最靠后的自然断点,找不到则原样返回 end。"""
    window = text[start:end]
    # 只在窗口后半段找断点,避免块过短
    floor = len(window) // 2
    for sep in _BREAKS:
        idx = window.rfind(sep)
        if idx >= floor:
            return start + idx + len(sep)
    return end
