% ── Series B: L=6, P=3, TR=2  seed=1 ──────────────────────────
% locations=6  active_products=3  transport_types=2  routes=30
% max_supply=17  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..17).
numParts(0..5).
numFreq(0..17).

% Parts
part(p1).
part(p2).
part(p3).

partSize(p1,3).
partSize(p2,3).
partSize(p3,3).

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

% Routes
route(l1,l2,tr1,6,27).
route(l1,l3,tr2,4,25).
route(l1,l4,tr1,9,27).
route(l1,l5,tr1,6,27).
route(l1,l6,tr2,5,25).
route(l2,l1,tr1,5,27).
route(l2,l3,tr2,4,25).
route(l2,l4,tr1,2,27).
route(l2,l5,tr2,8,25).
route(l2,l6,tr1,4,27).
route(l3,l1,tr2,5,25).
route(l3,l2,tr1,7,27).
route(l3,l4,tr1,7,27).
route(l3,l5,tr2,6,25).
route(l3,l6,tr2,8,25).
route(l4,l1,tr2,5,25).
route(l4,l2,tr1,10,27).
route(l4,l3,tr1,5,27).
route(l4,l5,tr1,7,27).
route(l4,l6,tr2,4,25).
route(l5,l1,tr2,6,25).
route(l5,l2,tr2,5,25).
route(l5,l3,tr2,5,25).
route(l5,l4,tr1,6,27).
route(l5,l6,tr2,10,25).
route(l6,l1,tr1,5,27).
route(l6,l2,tr1,5,27).
route(l6,l3,tr2,6,25).
route(l6,l4,tr1,5,27).
route(l6,l5,tr2,8,25).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l1,10).
demandOffer(p2,l1,2).
demandOffer(p3,l2,4).
demandOffer(p2,l3,1).
demandOffer(p3,l3,-3).
demandOffer(p1,l5,7).
demandOffer(p3,l5,10).
demandOffer(p1,l6,-17).
demandOffer(p2,l6,-3).
demandOffer(p3,l6,-11).
