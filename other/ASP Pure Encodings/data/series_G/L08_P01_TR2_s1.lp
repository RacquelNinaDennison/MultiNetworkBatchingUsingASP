% ── Series G: L=8, P=1, TR=2  seed=1 ──────────────────────────
% locations=8  active_products=1  transport_types=2  routes=56
% max_supply=13  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..13).
numParts(0..5).
numFreq(0..13).

% Parts
part(p1).

partSize(p1,3).

% Locations
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).
location(l7).
location(l8).

% Transport resources
transportCapacity(tr1,15).
transportCapacity(tr2,15).

% Routes
route(l1,l2,tr2,10,25).
route(l1,l3,tr1,7,27).
route(l1,l4,tr1,8,27).
route(l1,l5,tr2,8,25).
route(l1,l6,tr1,6,27).
route(l1,l7,tr1,3,27).
route(l1,l8,tr2,8,25).
route(l2,l1,tr1,9,27).
route(l2,l3,tr1,8,27).
route(l2,l4,tr2,3,25).
route(l2,l5,tr1,2,27).
route(l2,l6,tr1,9,27).
route(l2,l7,tr1,6,27).
route(l2,l8,tr2,4,25).
route(l3,l1,tr1,9,27).
route(l3,l2,tr1,6,27).
route(l3,l4,tr2,5,25).
route(l3,l5,tr1,5,27).
route(l3,l6,tr2,4,25).
route(l3,l7,tr1,2,27).
route(l3,l8,tr2,8,25).
route(l4,l1,tr1,4,27).
route(l4,l2,tr2,5,25).
route(l4,l3,tr1,7,27).
route(l4,l5,tr1,7,27).
route(l4,l6,tr2,6,25).
route(l4,l7,tr2,8,25).
route(l4,l8,tr2,5,25).
route(l5,l1,tr1,10,27).
route(l5,l2,tr1,5,27).
route(l5,l3,tr1,7,27).
route(l5,l4,tr2,4,25).
route(l5,l6,tr2,6,25).
route(l5,l7,tr2,5,25).
route(l5,l8,tr2,5,25).
route(l6,l1,tr1,6,27).
route(l6,l2,tr2,10,25).
route(l6,l3,tr1,5,27).
route(l6,l4,tr1,5,27).
route(l6,l5,tr2,6,25).
route(l6,l7,tr1,5,27).
route(l6,l8,tr2,8,25).
route(l7,l1,tr2,6,25).
route(l7,l2,tr2,9,25).
route(l7,l3,tr1,1,27).
route(l7,l4,tr2,2,25).
route(l7,l5,tr2,5,25).
route(l7,l6,tr1,3,27).
route(l7,l8,tr2,8,25).
route(l8,l1,tr2,4,25).
route(l8,l2,tr2,2,25).
route(l8,l3,tr1,6,27).
route(l8,l4,tr2,7,25).
route(l8,l5,tr1,5,27).
route(l8,l6,tr1,6,27).
route(l8,l7,tr2,1,25).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l2,9).
demandOffer(p1,l4,4).
demandOffer(p1,l5,-3).
demandOffer(p1,l6,-7).
demandOffer(p1,l8,-3).
