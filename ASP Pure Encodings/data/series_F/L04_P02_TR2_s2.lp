% ── Series F: L=4, P=2, TR=2  seed=2 ──────────────────────────
% locations=4  active_products=2  transport_types=2  routes=12
% max_supply=10  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..10).
numParts(0..5).
numFreq(0..10).

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

% Transport resources
transportCapacity(tr1,15).
transportCapacity(tr2,15).

% Routes
route(l1,l2,tr1,10,17).
route(l1,l3,tr2,10,95).
route(l1,l4,tr1,8,17).
route(l2,l1,tr1,8,17).
route(l2,l3,tr1,4,17).
route(l2,l4,tr1,2,17).
route(l3,l1,tr1,7,17).
route(l3,l2,tr1,7,17).
route(l3,l4,tr2,5,95).
route(l4,l1,tr1,6,17).
route(l4,l2,tr1,7,17).
route(l4,l3,tr1,9,17).

% Demand / supply  (non-zero entries only)
demandOffer(p2,l2,6).
demandOffer(p1,l3,-5).
demandOffer(p2,l3,-10).
demandOffer(p1,l4,5).
demandOffer(p2,l4,4).
