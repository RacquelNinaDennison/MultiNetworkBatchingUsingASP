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

% ── Routes: route(From, To, TR, TransitTime, CostPerTrip) ─────────────
%
% l1 → l2 : tr1 AND tr2 available  (the disruption arc)
% l1 → l3 : tr1 only
% l2 → l4 : tr1 only
% l3 → l4 : tr1 only
%
% Stage 1 loads that satisfy demand:
%   l1→l2 tr1: p1=4, p2=6
%   l1→l2 tr2: p1=2, p2=2
%   l1→l3 tr1: p1=4, p2=4
%   l2→l4 tr1: p1=6, p2=8    (receives from l1→l2)
%   l3→l4 tr1: p1=4, p2=4    (receives from l1→l3)
%
route(l1, l2, tr1, 1, 40).
route(l1, l2, tr2, 1, 48).
route(l1, l3, tr1, 1, 40).
route(l2, l4, tr1, 1, 40).
route(l3, l4, tr1, 1, 40).
