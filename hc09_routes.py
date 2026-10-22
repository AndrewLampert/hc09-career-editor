"""
Names for the routes the game's plays have (slant, post, out, curl, go ...), read from the shape of each route's art, so that a play editor can offer "Slant, deep" instead
of "8(54,32,254) 9(1,1,0) 8(120,48,254) 10".

Standard library only (no Tk). The art of a receiver's assignment is a line that starts at his position (see hc09_plays.decode_art: offsets (ax, ay), x across the field, y down
it, so a route goes up the field to negative ay). The shape is judged relative to the field: "toward the middle" or "toward the sideline", not left or right, so a slant is a
slant on either side. Checked against the names of the game's plays (a play called "Slants" should have slant routes): see docs/hc09_play_creator.md.
"""
import math

UNITS_PER_YARD = 7.2          # the diagram's units per yard (a lineman's gap is 1.67 yd = 12 units wide)
CENTER_X = 90                 # the middle of the field in the diagram's units

ROUTE_ORDER = ("Go", "Fade", "Slant", "Post", "Corner", "Out", "In", "Curl", "Comeback", "Hitch", "Drag", "Flat", "Wheel", "Swing", "Screen", "Other")


def _turn(a, b):
    """The angle in degrees between two vectors (0 straight on, 180 straight back)."""
    d = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
    return abs(d)


def polyline(art, start_x):
    """[(u, v)] of a route from its art: v is yards up the field, u is yards toward the SIDELINE (negative toward the middle); the first point is the start, (0, 0).
    Points of the art that do not move the line are dropped, and collinear points are merged."""
    out_sign = 1 if start_x >= CENTER_X else -1          # +x is toward the right sideline for a player right of the middle
    pts = [(0.0, 0.0)]
    for q in art:
        if q["ax"] == 0 and q["ay"] == 0:
            continue
        pt = (q["ax"] * out_sign / UNITS_PER_YARD, -q["ay"] / UNITS_PER_YARD)
        if math.hypot(pt[0] - pts[-1][0], pt[1] - pts[-1][1]) > 0.3:
            pts.append(pt)
    merged = [pts[0]]
    for i in range(1, len(pts)):
        if len(merged) >= 2 and _turn((merged[-1][0] - merged[-2][0], merged[-1][1] - merged[-2][1]), (pts[i][0] - merged[-1][0], pts[i][1] - merged[-1][1])) < 18:
            merged[-1] = pts[i]
        else:
            merged.append(pts[i])
    return merged


# The game's route art is a small picture that squeezes long routes (a deep post is about 7 "yards" deep in it), so the depths below are in the art's own scale; they were
# found from the names of the game's plays (the depth that best separates the plays called Post from those called Slant, Curl from Hitch ...).
POST_DEPTH = 6.5          # a diagonal toward the middle: a post from this deep, else a slant
CURL_DEPTH = 4.5          # a stop back toward the quarterback: a curl from this deep, else a hitch
DIG_DEPTH = 5.0           # a break toward the middle: an in (dig) from this deep, else a drag
STEM = 1.5                # a first leg this long up the field is a stem (the route runs up before it breaks)


def depth_word(yards):
    """short, medium or deep in the art's own scale (a third each of the game's routes)."""
    return "short" if yards < 4.5 else ("medium" if yards < 6.9 else "deep")


def classify(art, start_x):
    """{"name", "depth", "depth_word", "side" ("sideline", "middle" or ""), "points"} for a route's art, or None if the art has no line. The name is the route's final break
    judged from the last leg's direction toward the sideline or the middle; "Other" when it does not look like one of ROUTE_ORDER."""
    pts = polyline(art, start_x)
    if len(pts) < 2:
        return None
    segs = [(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
    depth = max(p[1] for p in pts)
    first, last = segs[0], segs[-1]
    last_len = math.hypot(*last)
    ang_last = math.degrees(math.atan2(last[0], last[1]))
    ang_first = math.degrees(math.atan2(first[0], first[1]))
    has_stem = len(segs) > 1 and abs(ang_first) < 25 and math.hypot(*first) >= STEM
    name = "Other"
    if len(segs) == 1:
        if first[1] < -0.5:
            name = "Screen" if abs(first[0]) < 2 else "Swing"
        elif abs(ang_first) < 20:
            name = "Go"
        elif 20 <= ang_first < 70:
            name = "Fade" if depth >= 5 else "Flat"
        elif -70 < ang_first <= -20:
            name = "Slant"
        elif ang_first >= 70:
            name = "Flat"
        else:
            name = "Drag"
    elif pts[-1][1] < -0.5 and depth < 0.5:                 # the whole route stays behind the line
        name = "Screen" if abs(pts[-1][0]) < 3 else "Swing"
    elif last[1] < -0.35 * last_len:                         # the last leg comes back toward the quarterback
        name = ("Comeback" if last[0] > 0.25 * last_len else ("Curl" if depth >= CURL_DEPTH else "Hitch"))
    elif abs(ang_last) < 22:                                 # the last leg goes straight up the field
        name = "Wheel" if abs(first[0]) > abs(first[1]) and first[0] > 0 else "Go"
    elif 22 <= ang_last < 68:
        name = "Corner" if has_stem else "Fade"
    elif -68 < ang_last <= -22:
        name = "Post" if depth >= POST_DEPTH else "Slant"
    elif ang_last >= 68:
        name = "Out" if has_stem else "Flat"
    else:
        name = "In" if (has_stem and depth >= DIG_DEPTH) else "Drag"
    total_u = pts[-1][0]
    side = "sideline" if total_u > 2 else ("middle" if total_u < -2 else "")
    return {"name": name, "depth": round(depth, 1), "depth_word": depth_word(depth), "side": side, "points": pts}
