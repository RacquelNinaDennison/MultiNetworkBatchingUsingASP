% ── Series C: L=6, P=2, TR=3  seed=2 ──────────────────────────
% locations=6  active_products=2  transport_types=3  routes=30
% max_supply=12  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..12).
numParts(0..5).
numFreq(0..12).

% Parts
part(p1).
part(p2).

partSize(p1,3).
partSize(p2,3).

% Locations
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% Transport resources
transportCapacity(tr1,15).
transportCapacity(tr2,15).
transportCapacity(tr3,15).

% Routes
route(l1,l2,tr1,8,17).
route(l1,l3,tr1,10,17).
route(l1,l4,tr3,10,87).
route(l1,l5,tr1,7,17).
route(l1,l6,tr3,4,87).
route(l2,l1,tr1,7,17).
route(l2,l3,tr1,4,17).
route(l2,l4,tr1,5,17).
route(l2,l5,tr3,8,87).
route(l2,l6,tr3,8,87).
route(l3,l1,tr1,4,17).
route(l3,l2,tr1,4,17).
route(l3,l4,tr3,6,87).
route(l3,l5,tr2,8,95).
route(l3,l6,tr3,9,87).
route(l4,l1,tr2,2,95).
route(l4,l2,tr2,4,95).
route(l4,l3,tr2,8,95).
route(l4,l5,tr3,3,87).
route(l4,l6,tr2,5,95).
route(l5,l1,tr2,2,95).
route(l5,l2,tr3,3,87).
route(l5,l3,tr2,2,95).
route(l5,l4,tr2,1,95).
route(l5,l6,tr3,3,87).
route(l6,l1,tr2,6,95).
route(l6,l2,tr3,6,87).
route(l6,l3,tr2,10,95).
route(l6,l4,tr3,9,87).
route(l6,l5,tr2,4,95).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l1,4).
demandOffer(p2,l2,6).
demandOffer(p1,l3,-5).
demandOffer(p2,l3,-10).
demandOffer(p1,l4,-5).
demandOffer(p2,l4,6).
demandOffer(p1,l5,6).
demandOffer(p2,l6,-2).
