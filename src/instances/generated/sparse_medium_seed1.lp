% Sparse benchmark instance
% Generated with seed=6000 locations=8 parts=5 transports=2 routes=41

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
transportCO2(tr1,26).
transportCost(tr1,40).
transportSpeed(tr1,7).
transportCapacity(tr2,14).
transportCO2(tr2,35).
transportCost(tr2,76).
transportSpeed(tr2,3).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,490).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,874).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,494).
partTR(p3,tr1).
partTR(p3,tr2).
part(p4).
partSize(p4,3).
partVal(p4,117).
partTR(p4,tr1).
partTR(p4,tr2).
part(p5).
partSize(p5,3).
partVal(p5,146).
partTR(p5,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,-3).
demandOffer(p2,l1,-2).
demandOffer(p3,l1,-16).
demandOffer(p4,l1,-3).
demandOffer(p5,l1,-9).
demandOffer(p1,l3,6).
demandOffer(p2,l3,4).
demandOffer(p3,l3,19).
demandOffer(p4,l3,20).
demandOffer(p5,l3,15).
demandOffer(p1,l4,-17).
demandOffer(p2,l4,-14).
demandOffer(p3,l4,-9).
demandOffer(p4,l4,-13).
demandOffer(p5,l4,-9).
demandOffer(p1,l6,-10).
demandOffer(p2,l6,-14).
demandOffer(p3,l6,-5).
demandOffer(p4,l6,-14).
demandOffer(p5,l6,-12).
demandOffer(p1,l7,24).
demandOffer(p2,l7,26).
demandOffer(p3,l7,11).
demandOffer(p4,l7,10).
demandOffer(p5,l7,15).

% ---- routes ----
route(l1,l3,tr1,4,160).
route(l1,l3,tr2,1,76).
route(l2,l1,tr1,7,280).
route(l2,l1,tr2,3,228).
route(l2,l4,tr1,1,40).
route(l2,l6,tr1,4,160).
route(l2,l6,tr2,7,532).
route(l3,l2,tr1,7,280).
route(l3,l2,tr2,10,760).
route(l3,l6,tr2,8,608).
route(l3,l7,tr1,6,240).
route(l3,l7,tr2,10,760).
route(l4,l2,tr1,4,160).
route(l4,l7,tr1,6,240).
route(l4,l7,tr2,5,380).
route(l5,l2,tr1,4,160).
route(l5,l2,tr2,1,76).
route(l5,l3,tr1,9,360).
route(l5,l3,tr2,8,608).
route(l6,l3,tr1,7,280).
route(l6,l3,tr2,4,304).
route(l6,l4,tr1,8,320).
route(l6,l4,tr2,7,532).
route(l6,l7,tr1,1,40).
route(l6,l7,tr2,7,532).
route(l7,l1,tr1,2,80).
route(l7,l1,tr2,9,684).
route(l7,l2,tr1,4,160).
route(l7,l2,tr2,9,684).
route(l7,l5,tr1,1,40).
route(l7,l5,tr2,6,456).
route(l7,l6,tr1,6,240).
route(l7,l6,tr2,3,228).
route(l8,l1,tr1,3,120).
route(l8,l1,tr2,3,228).
route(l8,l4,tr1,1,40).
route(l8,l4,tr2,1,76).
route(l8,l6,tr1,5,200).
route(l8,l6,tr2,7,532).
route(l8,l7,tr1,4,160).
route(l8,l7,tr2,10,760).
