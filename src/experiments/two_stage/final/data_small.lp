% ── Locations ─────────────────────────────────────────────────────────
location(l1).
location(l2).
location(l3).
location(l4).

% ── Transport resources ───────────────────────────────────────────────
transportResource(tr1).
transportResource(tr2).
transportCapacity(tr1, 8).
transportCapacity(tr2, 8).

% ── Parts ─────────────────────────────────────────────────────────────
part(p1).
part(p2).
partSize(p1, 2).
partSize(p2, 2).
partVal(p1, 500).
partVal(p2, 300).

% ── Supply and demand ─────────────────────────────────────────────────
% l1 is the only source, l4 is the xonly sink
demandOffer(p1, l1,  10).
demandOffer(p2, l1,  12).
demandOffer(p1, l4, -10).
demandOffer(p2, l4, -12).

%
route(l1, l2, tr1, 1, 40).
route(l1, l2, tr2, 1, 48).
route(l1, l3, tr1, 1, 40).
route(l2, l4, tr1, 1, 40).
route(l3, l4, tr1, 1, 40).
