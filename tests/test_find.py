"""Finding a place with a live alert, and the geometry it relies on."""

from closure_call import find
from closure_call.geo import inside, point_inside

SQUARE = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
# A "U" shape: the average of its corners falls in the gap between the two arms.
U_SHAPE = [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (2.0, 3.0), (2.0, 1.0), (1.0, 1.0), (1.0, 3.0), (0.0, 3.0)]


def test_inside_tells_points_in_a_ring_from_points_outside_it():
    assert inside(SQUARE, 1.0, 1.0)
    assert not inside(SQUARE, 3.0, 1.0)
    assert not inside(U_SHAPE, 1.5, 2.0)  # in the gap


def test_point_inside_uses_the_centre_of_a_simple_shape():
    assert point_inside(SQUARE) == (1.0, 1.0)


def test_point_inside_still_lands_inside_a_shape_that_bends_around_its_centre():
    longitude, latitude = point_inside(U_SHAPE)
    assert inside(U_SHAPE, longitude, latitude)


def feature(event, ends, geometry=None):
    return {"properties": {"event": event, "ends": ends}, "geometry": geometry}


def test_candidates_keep_only_the_hazards_in_scope_and_put_warnings_first():
    features = [
        feature("Wind Advisory", "2026-10-12T05:00:00-07:00"),
        feature("Tornado Warning", "2026-10-11T09:00:00-05:00"),
        feature("Winter Storm Watch", "2026-10-12T00:00:00-06:00"),
        feature("Flood Warning", "2026-10-11T21:00:00-04:00"),
    ]
    events = [item["properties"]["event"] for item in find.candidates(features)]
    assert events == ["Flood Warning", "Wind Advisory", "Winter Storm Watch"]


def test_candidates_list_the_longest_lasting_alert_first_within_a_level():
    short = feature("Flood Warning", "2026-10-10T12:45:00-04:00")
    long = feature("Flood Warning", "2026-10-13T09:00:00-04:00")
    open_ended = feature("Winter Storm Warning", None)
    assert find.candidates([short, long, open_ended]) == [open_ended, long, short]


def test_candidates_can_be_limited_to_one_hazard():
    features = [feature("Flood Warning", None), feature("High Wind Warning", None)]
    assert find.candidates(features, hazard="wind") == [features[1]]


def test_location_is_a_point_inside_the_alert_outline_as_latitude_then_longitude():
    outline = {"type": "Polygon", "coordinates": [[[-86.2, 31.3], [-85.9, 31.3], [-85.9, 31.5], [-86.2, 31.5]]]}
    assert find.location(feature("Flood Warning", None, outline)) == (31.4, -86.05)
