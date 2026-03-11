% ── Series C: L=6, P=2, TR=3  seed=3 ──────────────────────────
% locations=6  active_products=2  transport_types=3  routes=30
% max_supply=18  max_pack=5

% Domain bounds (computed from this instance)
numFlow(0..18).
numParts(0..5).
numFreq(0..18).

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
route(l1,l2,tr2,2,87).
route(l1,l3,tr3,10,87).
route(l1,l4,tr1,5,40).
route(l1,l5,tr1,6,40).
route(l1,l6,tr3,9,87).
route(l2,l1,tr2,9,87).
route(l2,l3,tr2,7,87).
route(l2,l4,tr3,7,87).
route(l2,l5,tr3,4,87).
route(l2,l6,tr3,9,87).
route(l3,l1,tr3,4,87).
route(l3,l2,tr3,9,87).
route(l3,l4,tr3,5,87).
route(l3,l5,tr3,1,87).
route(l3,l6,tr2,4,87).
route(l4,l1,tr1,6,40).
route(l4,l2,tr3,10,87).
route(l4,l3,tr3,2,87).
route(l4,l5,tr2,10,87).
route(l4,l6,tr1,6,40).
route(l5,l1,tr2,10,87).
route(l5,l2,tr1,4,40).
route(l5,l3,tr3,4,87).
route(l5,l4,tr1,7,40).
route(l5,l6,tr2,7,87).
route(l6,l1,tr1,5,40).
route(l6,l2,tr2,9,87).
route(l6,l3,tr1,6,40).
route(l6,l4,tr1,1,40).
route(l6,l5,tr1,1,40).

% Demand / supply  (non-zero entries only)
demandOffer(p1,l1,-8).
demandOffer(p2,l1,8).
demandOffer(p1,l2,-10).
demandOffer(p1,l3,9).
demandOffer(p2,l5,8).
demandOffer(p1,l6,9).
demandOffer(p2,l6,-16).
