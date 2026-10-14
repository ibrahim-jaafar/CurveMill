"""Tests for the COM-free parts of the SolidWorks bridge (curve conversion)."""

from curvemill.models import SplineEntity, VectorEntity
from curvemill.solidworks_bridge import END_CONDITIONS, curves_from_entities


def test_segment_soup_collapses_to_fit_point_splines():
    # A pattern DXF stores a smooth curve as many tiny separate line segments.
    # Send must run the optimize pipeline (chain + fit) so SolidWorks gets one
    # fit-point spline (== 1 element), not N raw lines -- the 7000-lines bug.
    import math

    pts = [(math.cos(t / 20 * math.pi / 2), math.sin(t / 20 * math.pi / 2)) for t in range(21)]
    segs = [VectorEntity(points=[pts[i], pts[i + 1]]) for i in range(len(pts) - 1)]
    curves = curves_from_entities(segs, [], 600.0, 400.0, 0.001)
    assert curves
    assert all(kind == "spline" for kind, _pts, _closed in curves)  # never raw lines
    assert len(curves) < len(segs)  # 20 segments collapsed, not one line each
    # meters, not millimetres: raw mm would put these near -300, not -0.3.
    assert all(abs(x) < 1 and abs(y) < 1 for _k, ps, _c in curves for x, y in ps)


def test_fit_point_spline_passes_through_with_closed_seam():
    s = SplineEntity(control_points=[], fit_points=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], closed=True)
    curves = curves_from_entities([], [s], 600.0, 400.0, 0.001)
    kind, pts, closed = curves[0]
    assert kind == "spline" and closed
    assert pts[0] == pts[-1]  # bit-identical seam so SW's refit closes the loop


def test_control_point_spline_is_sampled_to_fit_points():
    s = SplineEntity(control_points=[(0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (30.0, 10.0)], degree=3)
    curves = curves_from_entities([], [s], 600.0, 400.0, 0.001)
    kind, pts, _closed = curves[0]
    assert kind == "spline"
    assert len(pts) >= 5  # 4 samples per segment + endpoint


def test_end_conditions_match_the_send_dialog():
    assert set(END_CONDITIONS) == {"Through All", "Blind", "Up To Next", "Mid Plane"}


class _Feat:
    def __init__(self, name, type_name):
        self.Name, self._t = name, type_name

    def GetTypeName2(self):
        return self._t


class _TreeModel:
    # No SelectionManager -> _locate_new_sketch's selection branch is skipped
    # (cast raises without SolidWorks), so it falls through to the tree scan.
    def __init__(self, tree):
        self._tree = tree

    def FeatureByPositionReverse(self, i):
        return self._tree[i] if i < len(self._tree) else None


def test_locate_new_sketch_skips_trailing_folders():
    # send() re-finds the sketch it just drew. FeatureByPositionReverse(0) is the
    # LAST tree feature -- trailing folders (Sensors/bodies) sort after the
    # sketch, so scan from the end for the newest ProfileFeature.
    from curvemill.solidworks_bridge import _locate_new_sketch

    tree = [_Feat("Sensors", "SensorFolder"), _Feat("Annotations", "DetailCabinet"),
            _Feat("Sketch7", "ProfileFeature"), _Feat("Boss-Extrude1", "Extrusion")]
    feat, name = _locate_new_sketch(_TreeModel(tree))
    assert name == "Sketch7" and feat.GetTypeName2() == "ProfileFeature"


def test_locate_new_sketch_returns_none_when_tree_has_no_sketch():
    # Active doc is an assembly: its top-level tree holds no ProfileFeature (the
    # sketch went into an in-context component). send() then raises clear guidance.
    from curvemill.solidworks_bridge import _locate_new_sketch

    tree = [_Feat("Mates", "MateGroup"), _Feat("Part1<1>", "Reference")]
    assert _locate_new_sketch(_TreeModel(tree)) == (None, None)


def test_fix_all_sketch_entities_boxes_everything_and_restores_autosolve():
    # A >2000-entity sketch makes SW stop solving and report Over Defined with
    # zero relations; send() fixes every entity so the sketch is Fully Defined.
    from curvemill.solidworks_bridge import _fix_all_sketch_entities

    calls = []

    class Fake:
        def __init__(self, name):
            self.name = name
            self.AutoSolve = True

        def __getattr__(self, attr):
            def method(*args):
                calls.append((self.name, attr, args, skm.AutoSolve))
            return method

    model, ext, skm = Fake("model"), Fake("ext"), Fake("skm")
    curves = [("spline", [(0.0, 0.0), (1.0, 2.0)], False),
              ("spline", [(-3.0, 4.0), (5.0, -6.0)], True)]
    _fix_all_sketch_entities(model, ext, skm, curves, 10.0, 20.0)

    box = next(args for who, m, args, _ in calls if m == "SketchBoxSelect")
    # box covers every offset point (min -3+10, max 5+10 in x; -6+20, 4+20 in y)
    assert box[0] <= 7.0 and box[3] >= 15.0
    assert box[1] <= 14.0 and box[4] >= 24.0
    fixed = next(c for c in calls if c[1] == "SketchAddConstraints")
    assert fixed[2] == ("sgFIXED",)
    assert fixed[3] is False  # constraint added while auto-solve was off
    assert skm.AutoSolve is True  # and restored afterwards
