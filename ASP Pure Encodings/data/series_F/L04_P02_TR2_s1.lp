% ── Series F: L=4, P=2, TR=2  seed=1 ──────────────────────────
% locations=4  active_products=1  transport_types=2  routes=12
% max_supply=17  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..17).
numParts(0..5).
numFreq(0..17).

% Parts
part(p2).

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
route(l1,l2,tr2,6,25).
route(l1,l3,tr1,10,27).
route(l1,l4,tr2,4,25).
route(l2,l1,tr2,8,25).
route(l2,l3,tr1,9,27).
route(l2,l4,tr1,8,27).
route(l3,l1,tr2,3,25).
route(l3,l2,tr1,2,27).
route(l3,l4,tr1,9,27).
route(l4,l1,tr1,6,27).
route(l4,l2,tr2,4,25).
route(l4,l3,tr1,9,27).

% Demand / supply  (non-zero entries only)
demandOffer(p2,l1,-7).
demandOffer(p2,l2,-10).
demandOffer(p2,l3,2).
demandOffer(p2,l4,15).
