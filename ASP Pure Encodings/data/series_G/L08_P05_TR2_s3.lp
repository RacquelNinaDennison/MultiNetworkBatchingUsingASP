% ── Series G: L=8, P=5, TR=2  seed=3 ──────────────────────────
% locations=8  active_products=5  transport_types=2  routes=56
% max_supply=35  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..35).
numParts(0..5).
numFreq(0..35).

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
route(l1,l2,tr1,6,40).
route(l1,l3,tr1,6,40).
route(l1,l4,tr2,4,87).
route(l1,l5,tr2,2,87).
route(l1,l6,tr2,10,87).
route(l1,l7,tr1,4,40).
route(l1,l8,tr1,2,40).
route(l2,l1,tr2,10,87).
route(l2,l3,tr1,4,40).
route(l2,l4,tr2,9,87).
route(l2,l5,tr1,4,40).
route(l2,l6,tr1,7,40).
route(l2,l7,tr2,7,87).
route(l2,l8,tr1,5,40).
route(l3,l1,tr2,9,87).
route(l3,l2,tr1,10,40).
route(l3,l4,tr1,6,40).
route(l3,l5,tr2,8,87).
route(l3,l6,tr1,1,40).
route(l3,l7,tr2,2,87).
route(l3,l8,tr1,5,40).
route(l4,l1,tr1,6,40).
route(l4,l2,tr1,8,40).
route(l4,l3,tr2,6,87).
route(l4,l5,tr2,10,87).
route(l4,l6,tr1,7,40).
route(l4,l7,tr1,6,40).
route(l4,l8,tr1,3,40).
route(l5,l1,tr2,4,87).
route(l5,l2,tr1,9,40).
route(l5,l3,tr1,4,40).
route(l5,l4,tr1,2,40).
route(l5,l6,tr2,10,87).
route(l5,l7,tr2,4,87).
route(l5,l8,tr2,7,87).
route(l6,l1,tr1,3,40).
route(l6,l2,tr2,7,87).
route(l6,l3,tr2,2,87).
route(l6,l4,tr1,10,40).
route(l6,l5,tr2,5,87).
route(l6,l7,tr2,2,87).
route(l6,l8,tr2,9,87).
route(l7,l1,tr1,3,40).
route(l7,l2,tr2,1,87).
route(l7,l3,tr2,4,87).
route(l7,l4,tr2,9,87).
route(l7,l5,tr1,8,40).
route(l7,l6,tr2,8,87).
route(l7,l8,tr1,6,40).
route(l8,l1,tr1,4,40).
route(l8,l2,tr1,5,40).
route(l8,l3,tr1,4,40).
route(l8,l4,tr1,1,40).
route(l8,l5,tr1,2,40).
route(l8,l6,tr2,5,87).
route(l8,l7,tr1,6,40).

% Demand / supply  (non-zero entries only)
demandOffer(p3,l1,9).
demandOffer(p3,l2,8).
demandOffer(p4,l2,-6).
demandOffer(p1,l3,-6).
demandOffer(p2,l3,-2).
demandOffer(p4,l3,10).
demandOffer(p1,l4,2).
demandOffer(p2,l4,7).
demandOffer(p3,l4,8).
demandOffer(p3,l6,10).
demandOffer(p4,l6,8).
demandOffer(p5,l6,-7).
demandOffer(p1,l7,10).
demandOffer(p3,l7,-8).
demandOffer(p4,l7,-6).
demandOffer(p5,l7,3).
demandOffer(p1,l8,-6).
demandOffer(p2,l8,-5).
demandOffer(p3,l8,-27).
demandOffer(p4,l8,-6).
demandOffer(p5,l8,4).
