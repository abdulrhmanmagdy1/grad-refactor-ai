from pipeline import PipelineConfig, export, run_pipeline
from pipeline.export import read_summaries
from pipeline.validation import RowError

CSV = (
    "Region,Amount,Rep\n"
    "north,10.00,ann\n"
    "South,4,bob\n"
    " North ,\"1,000.50\",cy\n"
    "South,abc,dee\n"
    ",3,eve\n"
)


def config_for(tmp_path, **overrides) -> PipelineConfig:
    source = tmp_path / "sales.csv"
    if not source.exists():
        source.write_text(CSV, encoding="utf-8")
    settings = {"source": source, "dataset": "sales", "group_by": "region", "value_column": "amount"}
    settings.update(overrides)
    return PipelineConfig(**settings)


def test_summaries(tmp_path):
    result = run_pipeline(config_for(tmp_path))
    assert [(s.key, s.count, s.total) for s in result.summaries] == [
        ("North", 2, 1010.5),
        ("South", 1, 4.0),
    ]
    assert not result.from_cache


def test_bad_rows_are_reported(tmp_path):
    result = run_pipeline(config_for(tmp_path))
    assert RowError(3, "amount", "not a number: 'abc'") in result.errors
    assert RowError(4, "region", "missing value") in result.errors


def test_second_run_uses_the_cache(tmp_path):
    config = config_for(tmp_path, cache_dir=tmp_path / "cache")
    first = run_pipeline(config)
    second = run_pipeline(config)
    assert second.from_cache
    assert second.summaries == first.summaries


def test_changed_file_is_recomputed(tmp_path):
    config = config_for(tmp_path, cache_dir=tmp_path / "cache")
    run_pipeline(config)
    config.source.write_text("Region,Amount\nWest,1\n", encoding="utf-8")
    result = run_pipeline(config)
    assert not result.from_cache
    assert [s.key for s in result.summaries] == ["West"]


def test_other_settings_are_not_served_from_the_cache(tmp_path):
    run_pipeline(config_for(tmp_path, cache_dir=tmp_path / "cache"))
    by_rep = run_pipeline(config_for(tmp_path, cache_dir=tmp_path / "cache", group_by="rep"))
    assert not by_rep.from_cache
    assert [s.key for s in by_rep.summaries] == ["Ann", "Bob", "Cy", "Eve"]


def test_export(tmp_path):
    result = run_pipeline(config_for(tmp_path))
    connection = export(result, "sales")
    assert read_summaries(connection, "sales") == result.summaries
