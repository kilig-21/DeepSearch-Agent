"""quote 定位校验测试(§3.3 v1.3 收紧)。

核心机制:**近似匹配仅用于定位候选位置;最终入库必须取回实际原文片段**,
不保留模型改写的引文——防"该功能~~不~~支持离线"式高相似度反义篡改。
只允许预定义的空白/换行规范化,不允许任何字符级改写。
"""
import pytest

from orca import evidence
from orca.evidence import SOURCE_TYPES, locate_quote, normalize_ws

CLEANED = (
    "Python 3.13 引入了实验性的自由线程模式,可以通过禁用全局解释器锁来提升"
    "多线程性能。此外,交互式解释器全面升级,支持多行编辑、彩色提示与即时求值。"
    "错误消息现在更加友好,会指出常见的拼写错误并给出修正建议。"
    "该功能不支持离线使用,需要联网激活。"
)


def test_normalize_ws_collapses_all_whitespace():
    assert normalize_ws("a  b\n\n c\t d") == "a b c d"
    assert normalize_ws("中文　全角空格") == "中文 全角空格"


def test_exact_match_validates():
    quote = "交互式解释器全面升级,支持多行编辑、彩色提示与即时求值。"
    r = locate_quote(quote, CLEANED)
    assert r.validated is True
    assert r.quote == normalize_ws(quote)  # 实际原文(空白规范化)


def test_whitespace_only_difference_still_validates():
    """模型常把原文重排换行/空格——唯一允许的规范化。"""
    quote = "交互式解释器\n 全面升级, 支持\n多行编辑、彩色提示与即时求值。"
    r = locate_quote(quote, CLEANED)
    assert r.validated is True


def test_char_rewrite_is_replaced_by_actual_text():
    """模型改写"实验性"为"实验性的"(插入字符)→ 定位成功,
    但入库的是**实际原文片段**,不是模型版本。"""
    quote = "Python 3.13 引入了实验性的的自由线程模式"
    r = locate_quote(quote, CLEANED)
    assert r.validated is True
    assert r.quote != normalize_ws(quote)      # 不保留模型改写版
    assert r.quote in normalize_ws(CLEANED)    # 入库片段来自原文
    assert "实验性的自由线程" in r.quote        # 实际原文(无插入字)


def test_negation_tamper_returns_actual_text():
    """高相似度反义篡改:原文"不支持", 模型给出"支持"——
    定位到区域后必须取回含"不"的实际原文。"""
    quote = "该功能支持离线使用,需要联网激活"   # 模型删掉了"不"
    r = locate_quote(quote, CLEANED)
    assert r.validated is True
    assert "不支持" in r.quote                  # 实际原文片段, 篡改未保留


def test_fabricated_quote_fails():
    r = locate_quote("这段话在原文中根本不存在,纯属编造的引用内容", CLEANED)
    assert r.validated is False
    assert r.quote is None


def test_quote_capped_at_200_chars():
    """§3.3:quote 原文片段 ≤200 字。"""
    long_text = "长" * 5_000
    r = locate_quote("长" * 3_000, long_text)
    assert r.validated is True
    assert len(r.quote) <= 200


def test_empty_quote_fails():
    r = locate_quote("", CLEANED)
    assert r.validated is False


def test_source_types_enum_frozen():
    assert SOURCE_TYPES == {"official", "media", "blog", "ugc", "paper"}


def test_source_type_by_domain():
    """白名单来源的透明类型标签(§2.3:类型标签而非可信度分数)。
    维基百科是社区协作内容, 诚实标为 ugc。"""
    assert evidence.source_type_for_domain("docs.python.org") == "official"
    assert evidence.source_type_for_domain("developer.mozilla.org") == "official"
    assert evidence.source_type_for_domain("zh.wikipedia.org") == "ugc"


def test_source_type_unknown_domain_raises():
    with pytest.raises(ValueError):
        evidence.source_type_for_domain("unknown.example.com")
