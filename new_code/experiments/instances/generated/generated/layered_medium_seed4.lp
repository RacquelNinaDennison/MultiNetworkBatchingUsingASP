% Sparse benchmark instance
% Generated with seed=11003 locations=8 parts=3 transports=2 routes=39

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).
location(l7).
location(l8).

% ---- transport resources ----
transportCapacity(tr1,20).
transportCO2(tr1,56).
transportCost(tr1,37).
transportSpeed(tr1,6).
transportCapacity(tr2,20).
transportCO2(tr2,29).
transportCost(tr2,52).
transportSpeed(tr2,6).

% ---- parts ----
part(p1).
partSize(p1,2).
partVal(p1,811).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,981).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,2).
partVal(p3,951).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,11).
demandOffer(p2,l1,23).
demandOffer(p3,l1,26).
demandOffer(p1,l2,19).
demandOffer(p2,l2,7).
demandOffer(p3,l2,4).
demandOffer(p1,l6,-20).
demandOffer(p2,l6,-12).
demandOffer(p3,l6,-14).
demandOffer(p1,l7,-6).
demandOffer(p2,l7,-7).
demandOffer(p3,l7,-12).
demandOffer(p1,l8,-4).
demandOffer(p2,l8,-11).
demandOffer(p3,l8,-4).

% ---- routes ----
route(l1,l3,tr1,5,185).
route(l1,l3,tr2,5,260).
route(l1,l4,tr1,9,333).
route(l1,l4,tr2,1,52).
route(l1,l5,tr1,2,74).
route(l1,l5,tr2,10,520).
route(l1,l6,tr1,4,148).
route(l1,l6,tr2,6,312).
route(l1,l7,tr1,1,37).
route(l1,l7,tr2,3,156).
route(l2,l3,tr1,2,74).
route(l2,l3,tr2,7,364).
route(l2,l4,tr1,7,259).
route(l2,l4,tr2,3,156).
route(l2,l5,tr1,8,296).
route(l2,l5,tr2,1,52).
route(l2,l8,tr1,3,111).
route(l2,l8,tr2,6,312).
route(l3,l4,tr1,6,222).
route(l3,l4,tr2,2,104).
route(l3,l6,tr1,6,222).
route(l3,l6,tr2,6,312).
route(l3,l7,tr1,9,333).
route(l3,l7,tr2,4,208).
route(l3,l8,tr2,8,416).
route(l4,l6,tr1,10,370).
route(l4,l6,tr2,4,208).
route(l4,l7,tr1,7,259).
route(l4,l7,tr2,8,416).
route(l4,l8,tr1,6,222).
route(l4,l8,tr2,4,208).
route(l5,l3,tr1,6,222).
route(l5,l3,tr2,4,208).
route(l5,l6,tr1,10,370).
route(l5,l6,tr2,8,416).
route(l5,l7,tr1,1,37).
route(l5,l7,tr2,10,520).
route(l5,l8,tr1,6,222).
route(l5,l8,tr2,1,52).
