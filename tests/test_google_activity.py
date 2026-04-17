from worker.google_activity import SEARCH_QUERIES


def test_search_queries_have_default():
    assert "default" in SEARCH_QUERIES
    assert len(SEARCH_QUERIES["default"]) > 0


def test_search_queries_occupations():
    for occ in ["대학생", "회사원", "자영업", "주부", "프리랜서"]:
        assert occ in SEARCH_QUERIES
        assert len(SEARCH_QUERIES[occ]) >= 3


def test_search_queries_all_strings():
    for occ, queries in SEARCH_QUERIES.items():
        for q in queries:
            assert isinstance(q, str) and len(q) > 0
