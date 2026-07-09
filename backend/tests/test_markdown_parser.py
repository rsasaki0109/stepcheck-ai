import pytest

from app.application.markdown_parser import ProcedureParseError, parse_procedure


def test_parses_ordered_list_with_heading():
    md = """# PC Build

1. Install the motherboard
2. Mount the CPU
3. Attach the cooler
"""
    procedure = parse_procedure(md)
    assert procedure.title == "PC Build"
    assert [s.index for s in procedure.steps] == [1, 2, 3]
    assert procedure.steps[1].text == "Mount the CPU"


def test_reindexes_regardless_of_source_numbers():
    md = "5. first\n9. second\n"
    procedure = parse_procedure(md)
    assert [s.index for s in procedure.steps] == [1, 2]


def test_parses_bullets_and_checkboxes():
    md = """- [ ] plug in power
- [x] connect monitor
* extra step
"""
    procedure = parse_procedure(md)
    assert [s.text for s in procedure.steps] == [
        "plug in power",
        "connect monitor",
        "extra step",
    ]


def test_default_title_when_no_heading():
    procedure = parse_procedure("1. only step")
    assert procedure.title == "Procedure"


def test_empty_procedure_raises():
    with pytest.raises(ProcedureParseError):
        parse_procedure("just some prose with no steps")
