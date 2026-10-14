"""Duplicates must not mask open profiles or inflate multi-vertex counts."""

from curvemill.geometry import count_profile_issues
from curvemill.models import VectorEntity


def test_open_profile_not_masked_by_duplicates():
    # Two identical open copies chain end-to-end into a fake closed loop; the
    # counter must see the open profile the user actually drew.
    opened = VectorEntity(points=[(0, 0), (50, 0), (50, 50), (0, 50)], closed=False)
    issues = count_profile_issues([opened.clone(), opened.clone(), opened.clone()])
    assert issues.open_profiles == 1
    assert issues.duplicates == 2
    assert issues.multi_vertex == 0
