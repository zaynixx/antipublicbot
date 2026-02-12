from pathlib import Path

from src.bootstrap import build_parser
from src.importers import import_txt_file
from src.storage import HashStore


def test_build_parser_defaults():
    args = build_parser().parse_args(["a.txt"])
    assert args.batch_size == 5000
    assert str(args.db_path).endswith("data/antipublic.sqlite3")


def test_import_via_bootstrap_components(tmp_path: Path):
    txt = tmp_path / "seed.txt"
    txt.write_text("one\ntwo\none\n", encoding="utf-8")

    db_path = tmp_path / "antipublic.sqlite3"
    db = HashStore(db_path)
    try:
        report = import_txt_file(db, txt, batch_size=2)
        assert report.total_lines == 3
        assert report.inserted == 2
        assert db.contains("one") is True
        assert db.contains("two") is True
    finally:
        db.close()
