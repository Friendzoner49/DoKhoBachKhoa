from shop.core.community_links import DEFAULT_TITLE, parse_links_text
from shop.tools import export_public

SAMPLE_POST = """Giải trí tổng hợp (cập nhật khi có thêm sự kiện mới).
Giải bóng mẫu 2023 (https://bit.ly/DEMO2023)
Giải bóng mẫu 2024 (http://bit.ly/DEMO2024)

Vlog mẫu https://www.youtube.com/playlist?list=PLdemo123
Video mới đã update tại link cuối cùng, cảm ơn mọi người.
Trân trọng."""


def test_each_line_with_a_link_becomes_a_button_and_the_first_plain_line_is_the_title():
    parsed = parse_links_text(SAMPLE_POST)
    assert parsed["title"] == "Giải trí tổng hợp"  # trailing "(…)." note dropped
    assert parsed["links"] == [
        {"title": "Giải bóng mẫu 2023", "url": "https://bit.ly/DEMO2023"},
        {"title": "Giải bóng mẫu 2024", "url": "http://bit.ly/DEMO2024"},
        {"title": "Vlog mẫu", "url": "https://www.youtube.com/playlist?list=PLdemo123"},
    ]


def test_link_without_label_or_title_gets_defaults():
    parsed = parse_links_text("https://youtube.com/playlist?list=X&si=abc")
    assert parsed["title"] == DEFAULT_TITLE
    assert parsed["links"] == [{"title": "Xem video", "url": "https://youtube.com/playlist?list=X&si=abc"}]


def test_non_http_links_are_never_turned_into_buttons():
    parsed = parse_links_text("Bấm javascript:alert(1)\nTải ftp://example.test/file")
    assert parsed["links"] == []


def test_export_only_adds_community_when_there_are_links(conn, monkeypatch):
    monkeypatch.setattr(export_public, "community_links_text", lambda: "")
    assert "community" not in export_public.build_payload(conn)
    monkeypatch.setattr(export_public, "community_links_text", lambda: SAMPLE_POST)
    community = export_public.build_payload(conn)["community"]
    assert len(community["links"]) == 3


def test_title_keeps_text_without_a_trailing_note():
    assert parse_links_text("Video cộng đồng\nA https://a.test")["title"] == "Video cộng đồng"
    assert parse_links_text("(chỉ ghi chú)\nA https://a.test")["title"] == "(chỉ ghi chú)"
