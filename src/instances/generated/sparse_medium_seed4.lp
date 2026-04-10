% Sparse benchmark instance
% Generated with seed=6003 locations=8 parts=5 transports=2 routes=38

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
transportCapacity(tr1,14).
transportCO2(tr1,32).
transportCost(tr1,71).
transportSpeed(tr1,5).
transportCapacity(tr2,14).
transportCO2(tr2,27).
transportCost(tr2,67).
transportSpeed(tr2,4).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,931).
partTR(p1,tr1).
part(p2).
partSize(p2,1).
partVal(p2,260).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,922).
partTR(p3,tr1).
partTR(p3,tr2).
part(p4).
partSize(p4,1).
partVal(p4,303).
partTR(p4,tr1).
partTR(p4,tr2).
part(p5).
partSize(p5,3).
partVal(p5,139).
partTR(p5,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,15).
demandOffer(p2,l1,11).
demandOffer(p3,l1,6).
demandOffer(p4,l1,29).
demandOffer(p5,l1,4).
demandOffer(p1,l2,-5).
demandOffer(p2,l2,-14).
demandOffer(p3,l2,-11).
demandOffer(p4,l2,-11).
demandOffer(p5,l2,-8).
demandOffer(p1,l4,-12).
demandOffer(p2,l4,-3).
demandOffer(p3,l4,-7).
demandOffer(p4,l4,-9).
demandOffer(p5,l4,-6).
demandOffer(p1,l6,15).
demandOffer(p2,l6,19).
demandOffer(p3,l6,24).
demandOffer(p4,l6,1).
demandOffer(p5,l6,26).
demandOffer(p1,l8,-13).
demandOffer(p2,l8,-13).
demandOffer(p3,l8,-12).
demandOffer(p4,l8,-10).
demandOffer(p5,l8,-16).

% ---- routes ----
route(l1,l4,tr1,4,284).
route(l1,l4,tr2,10,670).
route(l1,l7,tr1,2,142).
route(l1,l7,tr2,8,536).
route(l1,l8,tr1,6,426).
route(l1,l8,tr2,9,603).
route(l2,l5,tr1,4,284).
route(l2,l5,tr2,10,670).
route(l2,l6,tr1,1,71).
route(l2,l6,tr2,9,603).
route(l3,l2,tr1,2,142).
route(l3,l2,tr2,9,603).
route(l3,l7,tr1,7,497).
route(l3,l7,tr2,5,335).
route(l3,l8,tr2,4,268).
route(l4,l2,tr1,6,426).
route(l4,l3,tr1,1,71).
route(l4,l3,tr2,5,335).
route(l5,l4,tr1,4,284).
route(l5,l7,tr1,4,284).
route(l5,l7,tr2,8,536).
route(l6,l2,tr1,5,355).
route(l6,l7,tr1,3,213).
route(l6,l7,tr2,4,268).
route(l7,l1,tr2,3,201).
route(l7,l2,tr1,9,639).
route(l7,l2,tr2,2,134).
route(l7,l3,tr1,8,568).
route(l7,l3,tr2,3,201).
route(l7,l4,tr1,3,213).
route(l7,l4,tr2,9,603).
route(l7,l6,tr1,9,639).
route(l7,l6,tr2,10,670).
route(l7,l8,tr1,7,497).
route(l7,l8,tr2,6,402).
route(l8,l3,tr2,10,670).
route(l8,l7,tr1,2,142).
route(l8,l7,tr2,8,536).
