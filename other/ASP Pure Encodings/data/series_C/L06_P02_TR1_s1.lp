% ── Series C: L=6, P=2, TR=1  seed=1 ──────────────────────────
% locations=6  active_products=2  transport_types=1  routes=30
% max_supply=17  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..17).
numParts(0..5).
numFreq(0..17).

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

% Routes
route(l1,l2,tr1,6,27).
route(l1,l3,tr1,8,27).
route(l1,l4,tr1,10,27).
route(l1,l5,tr1,6,27).
route(l1,l6,tr1,4,27).
route(l2,l1,tr1,7,27).
route(l2,l3,tr1,8,27).
route(l2,l4,tr1,10,27).
route(l2,l5,tr1,9,27).
route(l2,l6,tr1,5,27).
route(l3,l1,tr1,9,27).
route(l3,l2,tr1,9,27).
route(l3,l4,tr1,2,27).
route(l3,l5,tr1,7,27).
route(l3,l6,tr1,8,27).
route(l4,l1,tr1,4,27).
route(l4,l2,tr1,8,27).
route(l4,l3,tr1,9,27).
route(l4,l5,tr1,10,27).
route(l4,l6,tr1,6,27).
route(l5,l1,tr1,10,27).
route(l5,l2,tr1,6,27).
route(l5,l3,tr1,9,27).
route(l5,l4,tr1,3,27).
route(l5,l6,tr1,4,27).
route(l6,l1,tr1,10,27).
route(l6,l2,tr1,6,27).
route(l6,l3,tr1,10,27).
route(l6,l4,tr1,4,27).
route(l6,l5,tr1,9,27).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l1,2).
demandOffer(p2,l1,-10).
demandOffer(p2,l2,-3).
demandOffer(p1,l3,-7).
demandOffer(p1,l4,-10).
demandOffer(p1,l5,2).
demandOffer(p1,l6,13).
demandOffer(p2,l6,13).
