from ci_doctor.utils import parse_github_run_url
import pytest


def test_parse_valid_run_url():
    url = "https://github.com/owner/repo/actions/runs/123456789"
    p = parse_github_run_url(url)
    assert p.owner == "owner"
    assert p.repo == "repo"
    assert p.run_id == 123456789


@pytest.mark.parametrize("url", [
    "https://example.com/owner/repo/actions/runs/1",
    "https://github.com/owner/repo/actions/workflows/1",
    "https://github.com/owner/repo/runs/1",
])
def test_parse_invalid_urls(url):
    with pytest.raises(ValueError):
        parse_github_run_url(url)


