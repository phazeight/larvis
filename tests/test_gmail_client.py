import base64

from larvis.agents.gmail import client


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")


def _msg(plain=None, html=None, frm="Bob Jones <bob@x.com>", subject="Hello", snippet="snip"):
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    return {
        "id": "m1",
        "snippet": snippet,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": frm},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 11 Jun 2026 09:00:00 -0400"},
            ],
            "parts": parts,
        },
    }


def test_strip_html_removes_tags_and_scripts():
    html = "<style>p{color:red}</style><p>Hello <b>world</b></p><script>x()</script>"
    assert client._strip_html(html) == "Hello world"


def test_header_is_case_insensitive():
    headers = [{"name": "From", "value": "a@b.com"}]
    assert client._header(headers, "from") == "a@b.com"
    assert client._header(headers, "Subject") == ""


def test_extract_body_prefers_plain_text():
    payload = _msg(plain="plain body", html="<p>html body</p>")["payload"]
    assert client._extract_body(payload) == "plain body"


def test_extract_body_falls_back_to_stripped_html():
    payload = _msg(plain=None, html="<p>html <b>only</b></p>")["payload"]
    assert client._extract_body(payload) == "html only"


def test_parse_message_normalizes_fields():
    parsed = client.parse_message(_msg(plain="hi there"), "luke@gmail.com", body_chars=1000)
    assert parsed["account"] == "luke@gmail.com"
    assert parsed["from_name"] == "Bob Jones"
    assert parsed["from_addr"] == "bob@x.com"
    assert parsed["subject"] == "Hello"
    assert parsed["body"] == "hi there"


def test_parse_message_truncates_body():
    parsed = client.parse_message(_msg(plain="x" * 100), "luke@gmail.com", body_chars=10)
    assert parsed["body"] == "x" * 10


def test_accounts_splits_and_trims(monkeypatch):
    monkeypatch.setattr(client.settings, "gmail_accounts", "a@x.com, b@y.com ,")
    assert client._accounts() == ["a@x.com", "b@y.com"]


def test_clean_text_decodes_html_entities():
    assert client._clean_text('Shipped: &quot;Sun Bum&quot; &amp; more') == 'Shipped: "Sun Bum" & more'


def test_clean_text_strips_zero_width_chars():
    assert client._clean_text("Hel‌lo͏ world​") == "Hello world"


def test_clean_text_collapses_whitespace():
    assert client._clean_text("a   b\n\tc") == "a b c"


def test_strip_html_decodes_entities():
    assert client._strip_html("<p>Tom &amp; Jerry &#39;99</p>") == "Tom & Jerry '99"


def test_parse_message_cleans_subject_and_snippet():
    msg = _msg(plain="body", subject="Re: &quot;Order&quot;", snippet="Delivered&#39;͏ ‌ now")
    parsed = client.parse_message(msg, "luke@gmail.com", body_chars=1000)
    assert parsed["subject"] == 'Re: "Order"'
    assert parsed["snippet"] == "Delivered' now"


def test_clean_text_strips_bidi_isolates():
    # Amazon wraps numbers in U+2066..U+2069 directional isolates.
    assert client._clean_text("⁦2⁩ more items") == "2 more items"
