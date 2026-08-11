from app.services.parser import parse_chat


def test_parses_common_qq_export_and_links():
    text = """张三 09:31
发现一个开源工具 https://github.com/example/tool
李四 09:35
收到，谢谢"""
    messages = parse_chat(text, "2026-08-11")
    assert len(messages) == 2
    assert messages[0]["author"] == "张三"
    assert messages[0]["links"] == ["https://github.com/example/tool"]


def test_unknown_format_falls_back_to_lines():
    messages = parse_chat("第一条\n第二条", "2026-08-11")
    assert [m["content"] for m in messages] == ["第一条", "第二条"]

