"""Small geometry helpers for outlines given as rings of (longitude, latitude) points."""


def inside(ring, longitude, latitude):
    """Whether a point lies inside a closed ring."""
    result = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
            result = not result
    return result


def point_inside(ring):
    """A point that lies inside the ring.

    The average of the corners works for most outlines. For shapes that bend around it,
    the middle of a line that skips one corner is tried at each corner in turn.
    """
    count = len(ring)
    candidates = [(sum(x for x, _ in ring) / count, sum(y for _, y in ring) / count)]
    for index in range(count):
        (x1, y1), (x2, y2) = ring[index], ring[(index + 2) % count]
        candidates.append(((x1 + x2) / 2, (y1 + y2) / 2))
    return next(point for point in candidates if inside(ring, *point))
