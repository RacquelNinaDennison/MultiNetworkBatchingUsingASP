% ── Series G: L=8, P=5, TR=2  seed=1 ──────────────────────────
% locations=8  active_products=5  transport_types=2  routes=56
% max_supply=22  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..22).
numParts(0..5).
numFreq(0..22).

% Parts
part(p1).
part(p2).
part(p3).
part(p4).
part(p5).

partSize(p1,3).
partSize(p2,3).
partSize(p3,3).
partSize(p4,3).
partSize(p5,3).

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
route(l1,l2,tr2,4,25).
route(l1,l3,tr2,6,25).
route(l1,l4,tr2,5,25).
route(l1,l5,tr2,5,25).
route(l1,l6,tr1,6,27).
route(l1,l7,tr2,10,25).
route(l1,l8,tr1,5,27).
route(l2,l1,tr1,5,27).
route(l2,l3,tr2,6,25).
route(l2,l4,tr1,5,27).
route(l2,l5,tr2,8,25).
route(l2,l6,tr2,6,25).
route(l2,l7,tr2,9,25).
route(l2,l8,tr1,1,27).
route(l3,l1,tr2,2,25).
route(l3,l2,tr2,5,25).
route(l3,l4,tr1,3,27).
route(l3,l5,tr2,8,25).
route(l3,l6,tr2,4,25).
route(l3,l7,tr2,2,25).
route(l3,l8,tr1,6,27).
route(l4,l1,tr2,7,25).
route(l4,l2,tr1,5,27).
route(l4,l3,tr1,6,27).
route(l4,l5,tr2,1,25).
route(l4,l6,tr1,4,27).
route(l4,l7,tr2,3,25).
route(l4,l8,tr1,9,27).
route(l5,l1,tr2,10,25).
route(l5,l2,tr1,8,27).
route(l5,l3,tr2,3,25).
route(l5,l4,tr1,2,27).
route(l5,l6,tr2,5,25).
route(l5,l7,tr1,6,27).
route(l5,l8,tr2,10,25).
route(l6,l1,tr1,3,27).
route(l6,l2,tr2,5,25).
route(l6,l3,tr1,7,27).
route(l6,l4,tr1,2,27).
route(l6,l5,tr1,2,27).
route(l6,l7,tr2,9,25).
route(l6,l8,tr1,2,27).
route(l7,l1,tr2,4,25).
route(l7,l2,tr1,8,27).
route(l7,l3,tr1,6,27).
route(l7,l4,tr2,1,25).
route(l7,l5,tr2,6,25).
route(l7,l6,tr2,10,25).
route(l7,l8,tr1,2,27).
route(l8,l1,tr2,4,25).
route(l8,l2,tr1,2,27).
route(l8,l3,tr1,6,27).
route(l8,l4,tr1,2,27).
route(l8,l5,tr1,4,27).
route(l8,l6,tr1,1,27).
route(l8,l7,tr1,9,27).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l1,4).
demandOffer(p3,l1,1).
demandOffer(p4,l1,-3).
demandOffer(p3,l2,7).
demandOffer(p5,l2,10).
demandOffer(p1,l4,3).
demandOffer(p2,l4,-4).
demandOffer(p3,l4,8).
demandOffer(p5,l4,6).
demandOffer(p1,l5,-9).
demandOffer(p2,l5,2).
demandOffer(p3,l5,-5).
demandOffer(p4,l5,1).
demandOffer(p5,l5,6).
demandOffer(p1,l6,-5).
demandOffer(p2,l6,2).
demandOffer(p3,l6,-10).
demandOffer(p4,l6,-1).
demandOffer(p2,l7,2).
demandOffer(p4,l7,-3).
demandOffer(p1,l8,7).
demandOffer(p2,l8,-2).
demandOffer(p3,l8,-1).
demandOffer(p4,l8,6).
demandOffer(p5,l8,-22).
