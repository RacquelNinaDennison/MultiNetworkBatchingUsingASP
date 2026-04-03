% Sparse benchmark instance
% Generated with seed=5003 locations=6 parts=3 transports=2 routes=25

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,12).
transportCO2(tr1,39).
transportCost(tr1,48).
transportSpeed(tr1,7).
transportCapacity(tr2,16).
transportCO2(tr2,51).
transportCost(tr2,64).
transportSpeed(tr2,6).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,625).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,297).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,580).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,12).
demandOffer(p2,l1,15).
demandOffer(p3,l1,20).
demandOffer(p1,l2,-13).
demandOffer(p2,l2,-16).
demandOffer(p3,l2,-15).
demandOffer(p1,l4,-17).
demandOffer(p2,l4,-14).
demandOffer(p3,l4,-15).
demandOffer(p1,l5,18).
demandOffer(p2,l5,15).
demandOffer(p3,l5,10).

% ---- routes ----
route(l1,l2,tr1,7,336).
route(l1,l6,tr1,1,48).
route(l2,l4,tr1,3,144).
route(l2,l4,tr2,1,64).
route(l2,l5,tr2,5,320).
route(l2,l6,tr1,5,240).
route(l2,l6,tr2,7,448).
route(l3,l2,tr1,10,480).
route(l3,l2,tr2,4,256).
route(l3,l4,tr1,5,240).
route(l3,l4,tr2,2,128).
route(l4,l1,tr1,6,288).
route(l4,l1,tr2,8,512).
route(l4,l6,tr1,4,192).
route(l4,l6,tr2,5,320).
route(l5,l1,tr2,3,192).
route(l5,l4,tr1,9,432).
route(l5,l4,tr2,3,192).
route(l5,l6,tr1,1,48).
route(l5,l6,tr2,9,576).
route(l6,l1,tr1,2,96).
route(l6,l1,tr2,9,576).
route(l6,l2,tr1,3,144).
route(l6,l2,tr2,4,256).
route(l6,l4,tr2,1,64).
