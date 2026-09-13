"""单元测试：指标计算与文本归一化。

这些用例不依赖任何模型，验证的是"指标到底怎么算"，
防止再次出现"用 sleep 冒充延迟""参考答案非空就算答对"这类伪实现。
"""

from app.services.evaluate_service import char_f1, normalize_text, percentile


class TestNormalizeText:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_text("Hello, World!") == "helloworld"

    def test_handles_chinese_punctuation(self):
        assert normalize_text("北京，中国。") == "北京中国"

    def test_empty_and_none(self):
        assert normalize_text(None) == ""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""


class TestCharF1:
    def test_identical_text_scores_one(self):
        assert char_f1("北京", "北京") == 1.0

    def test_identical_after_normalization(self):
        # 大小写与标点差异不应影响结果
        assert char_f1("H2O!", "h2o") == 1.0

    def test_completely_different_scores_zero(self):
        assert char_f1("北京", "完全无关") == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        score = char_f1("机器学习", "机器")
        assert 0.0 < score < 1.0

    def test_both_empty_is_perfect_match(self):
        assert char_f1("", "") == 1.0

    def test_one_empty_scores_zero(self):
        assert char_f1("abc", "") == 0.0


class TestPercentile:
    def test_median_of_odd_list(self):
        assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0

    def test_max_ratio_returns_last(self):
        assert percentile([1.0, 2.0, 3.0], 1.0) == 3.0

    def test_empty_list_returns_zero(self):
        assert percentile([], 0.5) == 0.0
