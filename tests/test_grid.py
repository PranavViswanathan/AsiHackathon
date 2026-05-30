from pytest import approx

from src.algorithm.grid import haversine_nm, initial_bearing_deg, route_distance_nm

ONE_DEGREE_LAT_NM = 60.0


def test_one_degree_of_latitude_is_about_sixty_nautical_miles():
    assert haversine_nm(0.0, 0.0, 1.0, 0.0) == approx(ONE_DEGREE_LAT_NM, rel=0.01)


def test_one_degree_of_longitude_at_equator_is_about_sixty_nautical_miles():
    assert haversine_nm(0.0, 0.0, 0.0, 1.0) == approx(ONE_DEGREE_LAT_NM, rel=0.01)


def test_identical_points_have_zero_distance():
    assert haversine_nm(40.0, -73.0, 40.0, -73.0) == approx(0.0, abs=1e-9)


def test_bearing_due_north_is_zero():
    assert initial_bearing_deg(0.0, 0.0, 1.0, 0.0) == approx(0.0, abs=0.5)


def test_bearing_due_east_is_ninety():
    assert initial_bearing_deg(0.0, 0.0, 0.0, 1.0) == approx(90.0, abs=0.5)


def test_route_distance_sums_consecutive_segments():
    lats = [0.0, 0.0, 0.0]
    lons = [0.0, 1.0, 2.0]
    assert route_distance_nm(lats, lons) == approx(2 * ONE_DEGREE_LAT_NM, rel=0.01)


def test_single_waypoint_route_has_zero_distance():
    assert route_distance_nm([10.0], [20.0]) == 0.0
