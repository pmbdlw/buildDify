"""文本分块单元测试 —— 纯函数,无外部依赖。"""

from app.services.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("", chunk_size=100, overlap=10) == []
    assert chunk_text("   \n  ", chunk_size=100, overlap=10) == []


def test_short_text_is_single_chunk():
    chunks = chunk_text("一段很短的话。", chunk_size=100, overlap=10)
    assert chunks == ["一段很短的话。"]


def test_long_text_is_split_with_overlap():
    text = "句子。" * 200  # 600 字
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    # 每块不超过窗口上限
    assert all(len(c) <= 100 for c in chunks)
    # 覆盖完整(去重后字符数不少于原文,因有重叠)
    assert sum(len(c) for c in chunks) >= len(text.strip()) * 0.9


def test_overlap_clamped_when_ge_chunk_size():
    # overlap >= chunk_size 时应被收敛,避免死循环
    chunks = chunk_text("a" * 50, chunk_size=10, overlap=10)
    assert len(chunks) >= 1
