from ragassist.modules.knowledge.adapters.chunkers.tokenizer import RegexTokenCounter


def test_counts_words_and_punctuation() -> None:
    assert RegexTokenCounter().count("Refunds are issued, within 5 days.") == 8


def test_empty_text_has_no_tokens() -> None:
    assert RegexTokenCounter().count("") == 0
