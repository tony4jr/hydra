from worker.mouse import generate_curve_points


def test_generate_curve_points():
    points = generate_curve_points((0, 0), (100, 100), num_points=20)
    assert len(points) == 21
    assert abs(points[0][0]) < 5
    assert abs(points[0][1]) < 5
    assert abs(points[-1][0] - 100) < 5
    assert abs(points[-1][1] - 100) < 5


def test_curve_points_randomness():
    p1 = generate_curve_points((0, 0), (100, 100))
    p2 = generate_curve_points((0, 0), (100, 100))
    assert p1 != p2


def test_curve_points_count():
    points = generate_curve_points((0, 0), (500, 300), num_points=10)
    assert len(points) == 11
