% Sparse benchmark instance
% Generated with seed=10003 locations=6 parts=2 transports=2 routes=17

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,13).
transportCO2(tr1,41).
transportCost(tr1,56).
transportSpeed(tr1,4).
transportCapacity(tr2,10).
transportCO2(tr2,40).
transportCost(tr2,40).
transportSpeed(tr2,5).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,790).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,711).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,18).
demandOffer(p2,l1,23).
demandOffer(p1,l2,12).
demandOffer(p2,l2,7).
demandOffer(p1,l5,-10).
demandOffer(p2,l5,-9).
demandOffer(p1,l6,-20).
demandOffer(p2,l6,-21).

% ---- routes ----
route(l1,l3,tr1,10,560).
route(l1,l3,tr2,8,320).
route(l1,l4,tr1,6,336).
route(l1,l4,tr2,2,80).
route(l1,l6,tr1,2,112).
route(l1,l6,tr2,2,80).
route(l2,l3,tr2,2,80).
route(l2,l4,tr1,5,280).
route(l2,l4,tr2,4,160).
route(l3,l5,tr1,7,392).
route(l3,l5,tr2,8,320).
route(l3,l6,tr1,2,112).
route(l3,l6,tr2,2,80).
route(l4,l5,tr1,7,392).
route(l4,l5,tr2,5,200).
route(l4,l6,tr1,1,56).
route(l4,l6,tr2,3,120).
