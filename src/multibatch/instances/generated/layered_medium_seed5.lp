% Sparse benchmark instance
% Generated with seed=11004 locations=8 parts=3 transports=2 routes=41

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
transportCO2(tr1,46).
transportCost(tr1,44).
transportSpeed(tr1,3).
transportCapacity(tr2,10).
transportCO2(tr2,18).
transportCost(tr2,76).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,695).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,819).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,3).
partVal(p3,359).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,13).
demandOffer(p2,l1,22).
demandOffer(p3,l1,20).
demandOffer(p1,l2,17).
demandOffer(p2,l2,8).
demandOffer(p3,l2,10).
demandOffer(p1,l6,-11).
demandOffer(p2,l6,-7).
demandOffer(p3,l6,-8).
demandOffer(p1,l7,-16).
demandOffer(p2,l7,-12).
demandOffer(p3,l7,-13).
demandOffer(p1,l8,-3).
demandOffer(p2,l8,-11).
demandOffer(p3,l8,-9).

% ---- routes ----
route(l1,l3,tr1,7,308).
route(l1,l3,tr2,1,76).
route(l1,l4,tr2,8,608).
route(l1,l5,tr1,3,132).
route(l1,l5,tr2,1,76).
route(l1,l6,tr1,5,220).
route(l1,l6,tr2,7,532).
route(l1,l7,tr1,5,220).
route(l1,l7,tr2,6,456).
route(l2,l3,tr1,4,176).
route(l2,l3,tr2,6,456).
route(l2,l4,tr1,9,396).
route(l2,l4,tr2,4,304).
route(l2,l5,tr1,4,176).
route(l2,l5,tr2,8,608).
route(l2,l6,tr1,7,308).
route(l2,l7,tr1,7,308).
route(l2,l7,tr2,7,532).
route(l2,l8,tr1,9,396).
route(l2,l8,tr2,7,532).
route(l3,l5,tr1,1,44).
route(l3,l5,tr2,3,228).
route(l3,l6,tr1,7,308).
route(l3,l6,tr2,8,608).
route(l3,l7,tr1,7,308).
route(l3,l7,tr2,2,152).
route(l3,l8,tr1,5,220).
route(l3,l8,tr2,1,76).
route(l4,l5,tr1,3,132).
route(l4,l5,tr2,2,152).
route(l4,l6,tr1,3,132).
route(l4,l6,tr2,4,304).
route(l4,l7,tr1,8,352).
route(l4,l7,tr2,1,76).
route(l4,l8,tr2,1,76).
route(l5,l6,tr1,4,176).
route(l5,l6,tr2,1,76).
route(l5,l7,tr1,2,88).
route(l5,l7,tr2,4,304).
route(l5,l8,tr1,2,88).
route(l5,l8,tr2,8,608).
