% Sparse benchmark instance
% Generated with seed=6001 locations=8 parts=5 transports=2 routes=38

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
transportCapacity(tr1,15).
transportCO2(tr1,26).
transportCost(tr1,87).
transportSpeed(tr1,7).
transportCapacity(tr2,18).
transportCO2(tr2,15).
transportCost(tr2,76).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,753).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,322).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,736).
partTR(p3,tr1).
partTR(p3,tr2).
part(p4).
partSize(p4,2).
partVal(p4,506).
partTR(p4,tr2).
part(p5).
partSize(p5,4).
partVal(p5,522).
partTR(p5,tr1).
partTR(p5,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,-2).
demandOffer(p2,l1,-4).
demandOffer(p3,l1,-10).
demandOffer(p4,l1,-13).
demandOffer(p5,l1,-1).
demandOffer(p1,l4,12).
demandOffer(p2,l4,14).
demandOffer(p3,l4,13).
demandOffer(p4,l4,16).
demandOffer(p5,l4,21).
demandOffer(p1,l5,18).
demandOffer(p2,l5,16).
demandOffer(p3,l5,17).
demandOffer(p4,l5,14).
demandOffer(p5,l5,9).
demandOffer(p1,l7,-14).
demandOffer(p2,l7,-16).
demandOffer(p3,l7,-8).
demandOffer(p4,l7,-16).
demandOffer(p5,l7,-12).
demandOffer(p1,l8,-14).
demandOffer(p2,l8,-10).
demandOffer(p3,l8,-12).
demandOffer(p4,l8,-1).
demandOffer(p5,l8,-17).

% ---- routes ----
route(l1,l4,tr1,2,174).
route(l1,l4,tr2,9,684).
route(l1,l8,tr1,2,174).
route(l1,l8,tr2,8,608).
route(l2,l1,tr1,1,87).
route(l2,l1,tr2,8,608).
route(l2,l6,tr2,8,608).
route(l2,l7,tr1,5,435).
route(l2,l7,tr2,9,684).
route(l2,l8,tr1,6,522).
route(l3,l1,tr1,5,435).
route(l3,l1,tr2,4,304).
route(l3,l5,tr1,6,522).
route(l3,l5,tr2,6,456).
route(l4,l1,tr2,2,152).
route(l4,l2,tr1,9,783).
route(l4,l2,tr2,8,608).
route(l4,l3,tr1,1,87).
route(l4,l3,tr2,7,532).
route(l5,l2,tr2,1,76).
route(l5,l8,tr1,7,609).
route(l5,l8,tr2,5,380).
route(l6,l2,tr2,2,152).
route(l6,l3,tr1,10,870).
route(l6,l3,tr2,6,456).
route(l6,l4,tr1,5,435).
route(l6,l4,tr2,6,456).
route(l6,l7,tr1,2,174).
route(l6,l7,tr2,5,380).
route(l7,l2,tr1,10,870).
route(l7,l2,tr2,7,532).
route(l7,l6,tr1,4,348).
route(l8,l1,tr1,6,522).
route(l8,l1,tr2,4,304).
route(l8,l4,tr1,2,174).
route(l8,l4,tr2,6,456).
route(l8,l5,tr1,8,696).
route(l8,l5,tr2,9,684).
