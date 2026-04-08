from app.db.bootstrap import build_core_schema_statements


def test_core_schema_statements_cover_required_tables():
    statements = "\n".join(build_core_schema_statements())
    assert "CREATE TABLE IF NOT EXISTS articles" in statements
    assert "CREATE TABLE IF NOT EXISTS source_states" in statements
    assert "CREATE TABLE IF NOT EXISTS crawl_logs" in statements
    assert "CREATE TABLE IF NOT EXISTS snapshots" in statements
    assert "idx_articles_dimension" in statements
