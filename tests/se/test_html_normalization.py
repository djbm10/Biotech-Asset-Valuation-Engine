"""HTML becomes the text a reader sees, and nothing else.

The company-pipeline family made this visible. Its false candidates were not mistaken
readings of prose -- they were `currentColor`, `tbody`, `parentNode`, `yoast`,
`pd-pipeline-row`: implementation text from stylesheets, scripts and plugin metadata that a
tag-stripping regex leaves behind because it only removes what sits between angle brackets.

Nothing downstream can fix that. Identity, nomination and the gates all reason about what a
document *says*, and a document that claims to say `parentNode` has already lied to them. So
the repair belongs here, at the boundary where markup becomes text, and it is a statement
about what visible text *is* rather than a list of the junk strings this one family happened
to produce.
"""

from __future__ import annotations

from bve.se.acquisition.connectors import _strip_html


class TestImplementationTextNeverBecomesContent:
    def test_a_style_attribute_value_is_not_text(self) -> None:
        text = _strip_html('<span style="color:currentColor">Asset X</span>')
        assert text == "Asset X"
        assert "currentColor" not in text

    def test_a_class_name_is_not_text(self) -> None:
        text = _strip_html('<div class="pd-pipeline-row"><p>EXB-101</p></div>')
        assert "pd-pipeline-row" not in text
        assert "EXB-101" in text

    def test_script_contents_disappear(self) -> None:
        # The regex removed the <script> tags and kept everything between them, which is how
        # a JavaScript identifier became a candidate asset name.
        text = _strip_html(
            "<body><script>var el=node.parentNode;el.className='x';</script>"
            "<p>EXB-101</p></body>"
        )
        assert "parentNode" not in text
        assert "className" not in text
        assert "EXB-101" in text

    def test_style_contents_disappear(self) -> None:
        text = _strip_html(
            "<head><style>.pipeline td{fill:currentColor}</style></head><body><p>EXB-101</p></body>"
        )
        assert "currentColor" not in text
        assert "pipeline td" not in text
        assert "EXB-101" in text

    def test_a_tag_name_is_not_text(self) -> None:
        text = _strip_html("<table><tbody><tr><td>EXB-101</td></tr></tbody></table>")
        assert "tbody" not in text
        assert "EXB-101" in text

    def test_plugin_and_schema_metadata_is_not_text(self) -> None:
        # Yoast emits its SEO graph as JSON-LD in the head. It is machine metadata that no
        # reader of the page ever sees.
        text = _strip_html(
            '<head><script type="application/ld+json" class="yoast-schema-graph">'
            '{"@graph":[{"@type":"WebPage","name":"Pipeline"}]}</script>'
            '<meta name="generator" content="yoast"></head>'
            "<body><p>EXB-101 is in Phase 2.</p></body>"
        )
        assert "yoast" not in text.lower()
        assert "@graph" not in text
        assert "EXB-101 is in Phase 2." in text

    def test_svg_implementation_text_is_not_content(self) -> None:
        text = _strip_html(
            '<body><svg viewBox="0 0 8 8"><path fill="currentColor" d="M0 0h8v8z"/></svg>'
            "<p>EXB-101</p></body>"
        )
        assert "currentColor" not in text
        assert "EXB-101" in text


class TestVisibleContentSurvives:
    def test_the_facts_a_pipeline_page_states_are_kept(self) -> None:
        text = _strip_html(
            "<html><body><h1>Our pipeline</h1>"
            '<table class="pd-pipeline"><tbody><tr>'
            "<td>EXB-101</td><td>BCMA</td><td>Phase 2</td>"
            "</tr></tbody></table>"
            "<p>Example Bio is a clinical-stage company.</p></body></html>"
        )
        for visible in ("Our pipeline", "EXB-101", "BCMA", "Phase 2", "Example Bio"):
            assert visible in text

    def test_entities_decode(self) -> None:
        assert _strip_html("<p>Phase&nbsp;2 &amp; Phase&#160;3 &lt;pivotal&gt;</p>") == (
            "Phase 2 & Phase 3 <pivotal>"
        )

    def test_adjacent_elements_do_not_concatenate(self) -> None:
        # Without a separator "EXB-101" and "Phase 2" become "EXB-101Phase 2", which is both a
        # lost fact and a newly invented token.
        text = _strip_html("<td>EXB-101</td><td>Phase 2</td>")
        assert text == "EXB-101 Phase 2"

    def test_inline_markup_inside_a_sentence_does_not_split_a_word(self) -> None:
        # The mirror risk of the separator: emphasis inside a word must not break it apart.
        assert _strip_html("<p>ide<b>cabtagene</b> vicleucel dosed</p>") == (
            "idecabtagene vicleucel dosed"
        )

    def test_plain_text_is_returned_unchanged(self) -> None:
        # Most sources hand over text that was never markup. Normalization must be a no-op on
        # it rather than a parser's guess at what it might have meant.
        assert _strip_html("EXB-101 is in Phase 2.") == "EXB-101 is in Phase 2."

    def test_text_that_merely_mentions_a_tag_name_is_kept(self) -> None:
        assert "script" in _strip_html("The script for the study was amended.")


class TestMalformedPagesDoNotVanish:
    def test_content_nested_under_head_by_a_lenient_parser_survives(self) -> None:
        # Real pages carry unclosed void elements, and a lenient parser then puts <body>
        # inside <head>. Excluding a container by position would empty the whole document --
        # a total content loss that reads downstream as "this company has no pipeline".
        text = _strip_html(
            "<html><head><meta charset='utf-8'><link rel='stylesheet'>"
            "<body><ul><li><a href='/prmt5'>PRMT5</a></li></ul>"
            "<p>EXB-101 is in Phase 2.</p></body></head></html>"
        )
        assert "PRMT5" in text
        assert "EXB-101 is in Phase 2." in text

    def test_the_page_title_is_kept(self) -> None:
        assert "Pipeline | Example Bio" in _strip_html(
            "<html><head><title>Pipeline | Example Bio</title></head>"
            "<body><p>EXB-101</p></body></html>"
        )
