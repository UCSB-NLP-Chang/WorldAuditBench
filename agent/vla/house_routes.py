"""Setting 3 oracle routes for the HS suite (Family House). Same contract as the SP routes in
agent/vla/scripted_tour.py: each route is a function of a Tour and deterministically exposes the
planted bug (approach + dwell with the carrier and its siblings in frame; push into the air
wall; cross the ghost island; leave-and-return for the state cases ...).

House layout (world x east / z south, front door at z=+5, upper floor y=3):
  spawn (0.55, 3.9) facing north; hall x -1.74..1.74; living room west of the hall (opening at
  x=-1.8, z 2.8..4.8); dining/kitchen east (openings at x=1.8, z 2.8..4.8 and z -4.4..-2.4);
  stairs x -1.74..-0.75, foot at z=2.4 rising north to the landing at z<-1.65.
"""
import math

# waypoints (x, z) on the ground floor
HALL_S, HALL_N = (0.6, 3.6), (0.6, -3.6)
LIVING_DOOR = (-1.9, 3.8)     # living-room opening
DINING_DOOR = (2.0, 3.8)      # dining-room opening
KITCHEN_DOOR = (2.0, -3.4)    # kitchen opening from the hall
STAIR_FOOT = (-1.25, 2.9)
STAIR_TOP = (-1.25, -2.2)     # on the landing (y=3)
UPSTAIRS = [STAIR_FOOT, STAIR_TOP]   # up the stairs onto the landing
KIDS_DOOR = (1.8, -1.95)      # kids-room door from the landing (upper floor)
LOUNGE_DOOR = (1.8, 2.6)      # lounge opening from the landing (upper floor)


LIVING_LOOP = [LIVING_DOOR, (-4.0, 3.9), (-5.25, 2.35), (-4.6, 1.2)]   # south strip -> west passage -> north part
DINING_W = [DINING_DOOR, (2.7, 3.6), (2.7, -0.2)]                           # west aisle of the dining room


def r_view(t, via, vx, vz, x, y, z, dwell=3.0):
    """Walk the waypoints, then to the viewpoint (vx,vz), face the carrier (x,y,z) and dwell
    (carrier and its siblings stay in frame; no close-ups)."""
    for wp in via:
        t.goto(*wp, tol=0.5)
    t.goto(vx, vz, tol=0.45)
    t.face(x, y, z)
    t.dwell(dwell, x, y, z)


ROUTES = {
    # geometry: dining chairs / kitchen stool / living armchair
    "hs01-float": lambda t: r_view(t, [DINING_DOOR, (3.4, 4.2)], 5.0, 4.3, 5.11, 0.9, 2.91),
    "hs02-clip": lambda t: r_view(t, DINING_W, 3.6, -0.3, 5.1, 0.3, -1.75),
    # v2 (2026-09-12): the kids-room desk chair upstairs; UPSTAIRS climbs the stairs, KIDS_DOOR is the room's door
    "hs03-scale": lambda t: r_view(t, UPSTAIRS + [(1.3, -1.95), KIDS_DOOR, (2.6, -2.2)], 2.8, -2.2, 4.0, 3.6, -3.6),
    "hs04-doublespawn": lambda t: (r_view(t, [LIVING_DOOR, (-3.6, 3.9)], -5.0, 3.9, -6.1, 0.45, 2.6, dwell=2.5),
                                   t.goto(-4.2, 3.9, tol=0.4), t.face(-6.1, 0.4, 2.6),
                                   t.dwell(2.0, -6.1, 0.4, 2.6)),
    # collision: air wall across the hall at z=0.9 (push, look around, push again)
    "hs05-airwall": lambda t: (t.goto(0.6, 2.2), t.face(0.6, 1.6, -3.6),
                               t.push(0.6, -3.6, 4.0), t.spin(30), t.spin(-30),
                               t.push(0.6, -3.6, 2.5)),
    # hole in the hall floor at (0.6,-1.9): walk north into it (respawn), and again
    "hs06-hole": lambda t: (t.face(0.6, 1.6, -3.6), t.push(0.6, -3.6, 6.0),
                            t.face(0.6, 1.6, -3.6), t.push(0.6, -3.6, 6.0)),
    # ghost island: approach from the dining side and push through it toward the counter
    # ghost island: from the kitchen aisle (counter side) push south through the island toward the
    # dining room, turn, look back at it, push back through (the bar stools block the south side)
    "hs07-ghostisland": lambda t: ([t.goto(*wp, tol=0.5) for wp in [HALL_N, KITCHEN_DOOR, (3.4, -3.65)]],
                                   t.goto(4.4, -3.65, tol=0.35),
                                   t.face(4.4, 0.9, -2.6), t.push(4.4, -0.9, 3.0), t.spin(180),
                                   t.dwell(2.0, 4.4, 0.9, -2.6), t.push(4.4, -4.3, 3.0)),
    "hs08-jitter": lambda t: r_view(t, LIVING_LOOP, -4.6, 0.3, -6.45, 1.2, -0.75, dwell=6.0),
    # visual: TV console magenta / sofa backcull / coffee table x-ray / rug LOD
    "hs09-magenta": lambda t: r_view(t, LIVING_LOOP, -3.2, 1.5, -3.2, 0.5, -0.86),
    "hs10-backcull": lambda t: (r_view(t, LIVING_LOOP, -2.6, 1.5, -3.2, 0.6, 2.35, dwell=2.5),   # front (TV side): normal
                                [t.goto(*wp, tol=0.5) for wp in [(-4.6, 1.2), (-5.25, 2.35), (-4.0, 3.9)]],
                                t.goto(-3.2, 4.3, tol=0.4),
                                t.face(-3.2, 0.6, 2.35), t.dwell(3.0, -3.2, 0.6, 2.35),   # behind (window side): gone
                                t.face(-4.62, 0.6, 2.35), t.dwell(1.5, -4.62, 0.6, 2.35),
                                t.face(-3.2, 0.6, 2.35), t.dwell(1.5, -3.2, 0.6, 2.35)),
    # v2 (2026-09-12): the master bed drawn through the bedroom wall (landing side), then from inside the room
    "hs11-xray": lambda t: ([t.goto(*wp, tol=0.5) for wp in UPSTAIRS], t.goto(0.6, -0.4, tol=0.5),
                            t.face(-3.25, 3.5, -0.05), t.dwell(2.5, -3.25, 3.5, -0.05),        # through the wall
                            t.goto(0.6, 1.4, tol=0.5), t.face(-3.25, 3.5, -0.05), t.dwell(1.5, -3.25, 3.5, -0.05),
                            t.goto(-1.2, 3.85, tol=0.5), t.goto(-2.6, 3.4, tol=0.5),           # into the bedroom
                            t.face(-3.25, 3.5, -0.05), t.dwell(2.5, -3.25, 3.5, -0.05)),
    "hs12-unload": lambda t: (r_view(t, [LIVING_DOOR, (-3.6, 3.9)], -4.4, 4.0, -6.35, 0.6, 4.4, dwell=1.5),
                              t.goto(-1.9, 3.8, tol=0.5), t.goto(1.4, 3.6, tol=0.5),     # leave the area (>7 m)
                              t.goto(1.4, -1.5, tol=0.5), t.spin(180),
                              t.goto(0.6, 3.6, tol=0.5), t.goto(-1.9, 3.8, tol=0.5), t.goto(-3.6, 3.9, tol=0.5),
                              t.face(-6.35, 0.6, 4.4), t.dwell(2.5, -6.35, 0.6, 4.4)),
    "hs13-statereset": lambda t: (r_view(t, [DINING_DOOR, (2.7, 3.6)], 2.7, 1.5, 5.11, 0.5, 1.49, dwell=1.5),
                                  t.goto(2.7, 3.6, tol=0.5), t.goto(-1.9, 3.8, tol=0.5),   # leave (>7 m), come back
                                  t.goto(-4.0, 3.9, tol=0.5), t.spin(180),
                                  t.goto(-1.9, 3.8, tol=0.5), t.goto(2.0, 3.8, tol=0.5), t.goto(2.7, 3.6, tol=0.5),
                                  t.goto(2.7, 1.5, tol=0.5),
                                  t.face(5.11, 0.5, 1.49), t.dwell(2.0, 5.11, 0.5, 1.49),
                                  t.face(6.31, 0.5, 0.69), t.dwell(1.5, 6.31, 0.5, 0.69)),
    # v2 (2026-09-12): the lounge sofa upstairs - a crude box from the landing (>3.5 m), the real sofa up close, box again
    "hs14-lodpop": lambda t: ([t.goto(*wp, tol=0.5) for wp in UPSTAIRS], t.goto(0.4, 1.4, tol=0.5),
                              t.face(4.4, 3.5, -0.04), t.dwell(2.0, 4.4, 3.5, -0.04),          # box from 4 m
                              t.goto(1.8, 2.6, tol=0.5), t.goto(3.0, 1.0, tol=0.5),
                              t.face(4.4, 3.5, -0.04), t.dwell(1.5, 4.4, 3.5, -0.04),          # sofa at 1.7 m
                              t.goto(1.8, 2.6, tol=0.5), t.goto(0.4, 1.4, tol=0.5),
                              t.face(4.4, 3.5, -0.04), t.dwell(1.5, 4.4, 3.5, -0.04)),         # box again
    # v2 (2026-09-12): the furniture pile in the kids room upstairs
    "hs15-spawnpile": lambda t: ([t.goto(*wp, tol=0.5) for wp in UPSTAIRS + [(1.3, -1.95), KIDS_DOOR]], t.goto(2.4, -1.6, tol=0.5),
                                 t.face(2.9, 3.4, -3.3), t.dwell(2.0, 2.9, 3.4, -3.3),
                                 t.goto(3.6, -2.0, tol=0.5), t.face(2.9, 3.4, -3.3), t.dwell(2.5, 2.9, 3.4, -3.3)),
}
# clean control: 4 matched routes on the untouched house (same footage statistics)
CLEAN_ROUTES = [ROUTES["hs01-float"], ROUTES["hs06-hole"],
                ROUTES["hs10-backcull"], ROUTES["hs14-lodpop"]]
CLEAN_CONFIG = "hs00-clean"
