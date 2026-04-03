% Sparse benchmark instance
% Generated with seed=11002 locations=8 parts=3 transports=2 routes=40

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
transportCO2(tr1,61).
transportCost(tr1,79).
transportSpeed(tr1,4).
transportCapacity(tr2,20).
transportCO2(tr2,58).
transportCost(tr2,59).
transportSpeed(tr2,4).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,602).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,944).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,680).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,13).
demandOffer(p2,l1,19).
demandOffer(p3,l1,10).
demandOffer(p1,l2,17).
demandOffer(p2,l2,11).
demandOffer(p3,l2,20).
demandOffer(p1,l6,-15).
demandOffer(p2,l6,-16).
demandOffer(p3,l6,-13).
demandOffer(p1,l7,-6).
demandOffer(p2,l7,-9).
demandOffer(p3,l7,-11).
demandOffer(p1,l8,-9).
demandOffer(p2,l8,-5).
demandOffer(p3,l8,-6).

% ---- routes ----
route(l1,l3,tr1,1,79).
route(l1,l3,tr2,3,177).
route(l1,l4,tr1,8,632).
route(l1,l4,tr2,3,177).
route(l1,l5,tr1,1,79).
route(l1,l5,tr2,8,472).
route(l1,l7,tr1,7,553).
route(l1,l7,tr2,10,590).
route(l1,l8,tr1,5,395).
route(l1,l8,tr2,3,177).
route(l2,l3,tr1,5,395).
route(l2,l3,tr2,1,59).
route(l2,l4,tr1,7,553).
route(l2,l4,tr2,6,354).
route(l2,l5,tr1,10,790).
route(l2,l5,tr2,9,531).
route(l2,l6,tr1,6,474).
route(l2,l6,tr2,5,295).
route(l2,l8,tr1,7,553).
route(l3,l6,tr1,6,474).
route(l3,l6,tr2,4,236).
route(l3,l7,tr1,6,474).
route(l3,l7,tr2,8,472).
route(l3,l8,tr1,6,474).
route(l3,l8,tr2,3,177).
route(l4,l3,tr1,2,158).
route(l4,l3,tr2,3,177).
route(l4,l5,tr1,8,632).
route(l4,l5,tr2,1,59).
route(l4,l6,tr1,3,237).
route(l4,l6,tr2,2,118).
route(l4,l7,tr1,4,316).
route(l4,l7,tr2,9,531).
route(l4,l8,tr1,10,790).
route(l5,l6,tr1,7,553).
route(l5,l6,tr2,9,531).
route(l5,l7,tr1,3,237).
route(l5,l7,tr2,7,413).
route(l5,l8,tr1,10,790).
route(l5,l8,tr2,8,472).
