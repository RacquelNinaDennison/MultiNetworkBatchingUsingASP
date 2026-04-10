% Sparse benchmark instance
% Generated with seed=6002 locations=8 parts=5 transports=2 routes=38

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
transportCapacity(tr1,12).
transportCO2(tr1,54).
transportCost(tr1,63).
transportSpeed(tr1,2).
transportCapacity(tr2,11).
transportCO2(tr2,67).
transportCost(tr2,71).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,417).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,855).
partTR(p2,tr1).
part(p3).
partSize(p3,4).
partVal(p3,811).
partTR(p3,tr2).
part(p4).
partSize(p4,2).
partVal(p4,657).
partTR(p4,tr1).
partTR(p4,tr2).
part(p5).
partSize(p5,3).
partVal(p5,574).
partTR(p5,tr1).
partTR(p5,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,-12).
demandOffer(p2,l1,-16).
demandOffer(p3,l1,-9).
demandOffer(p4,l1,-19).
demandOffer(p5,l1,-11).
demandOffer(p1,l2,6).
demandOffer(p2,l2,4).
demandOffer(p3,l2,3).
demandOffer(p4,l2,20).
demandOffer(p5,l2,25).
demandOffer(p1,l3,-5).
demandOffer(p2,l3,-7).
demandOffer(p3,l3,-19).
demandOffer(p4,l3,-8).
demandOffer(p5,l3,-11).
demandOffer(p1,l6,24).
demandOffer(p2,l6,26).
demandOffer(p3,l6,27).
demandOffer(p4,l6,10).
demandOffer(p5,l6,5).
demandOffer(p1,l8,-13).
demandOffer(p2,l8,-7).
demandOffer(p3,l8,-2).
demandOffer(p4,l8,-3).
demandOffer(p5,l8,-8).

% ---- routes ----
route(l1,l6,tr1,2,126).
route(l1,l6,tr2,10,710).
route(l2,l3,tr1,7,441).
route(l2,l3,tr2,8,568).
route(l2,l4,tr1,6,378).
route(l2,l4,tr2,10,710).
route(l2,l5,tr1,3,189).
route(l2,l5,tr2,9,639).
route(l2,l7,tr1,6,378).
route(l2,l7,tr2,9,639).
route(l2,l8,tr1,9,567).
route(l2,l8,tr2,1,71).
route(l3,l4,tr1,8,504).
route(l3,l4,tr2,1,71).
route(l3,l5,tr2,10,710).
route(l4,l1,tr1,10,630).
route(l4,l2,tr1,8,504).
route(l4,l2,tr2,4,284).
route(l4,l3,tr1,4,252).
route(l4,l6,tr2,3,213).
route(l4,l8,tr1,10,630).
route(l4,l8,tr2,1,71).
route(l5,l1,tr1,4,252).
route(l5,l1,tr2,4,284).
route(l5,l3,tr1,1,63).
route(l5,l3,tr2,10,710).
route(l5,l4,tr1,7,441).
route(l5,l4,tr2,3,213).
route(l5,l8,tr1,1,63).
route(l5,l8,tr2,8,568).
route(l6,l5,tr1,5,315).
route(l6,l8,tr2,5,355).
route(l7,l2,tr1,7,441).
route(l7,l2,tr2,1,71).
route(l8,l5,tr1,2,126).
route(l8,l5,tr2,2,142).
route(l8,l7,tr1,9,567).
route(l8,l7,tr2,9,639).
