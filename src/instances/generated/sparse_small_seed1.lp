% Sparse benchmark instance
% Generated with seed=5000 locations=6 parts=3 transports=2 routes=24

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,13).
transportCO2(tr1,44).
transportCost(tr1,80).
transportSpeed(tr1,6).
transportCapacity(tr2,15).
transportCO2(tr2,22).
transportCost(tr2,55).
transportSpeed(tr2,5).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,617).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,633).
partTR(p2,tr1).
part(p3).
partSize(p3,1).
partVal(p3,600).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,-13).
demandOffer(p2,l1,-13).
demandOffer(p3,l1,-20).
demandOffer(p1,l3,-17).
demandOffer(p2,l3,-17).
demandOffer(p3,l3,-10).
demandOffer(p1,l4,15).
demandOffer(p2,l4,14).
demandOffer(p3,l4,16).
demandOffer(p1,l5,15).
demandOffer(p2,l5,16).
demandOffer(p3,l5,14).

% ---- routes ----
route(l1,l3,tr1,1,80).
route(l1,l3,tr2,5,275).
route(l2,l1,tr1,7,560).
route(l2,l3,tr1,2,160).
route(l2,l3,tr2,5,275).
route(l2,l5,tr2,6,330).
route(l2,l6,tr2,8,440).
route(l3,l1,tr1,5,400).
route(l3,l1,tr2,5,275).
route(l4,l2,tr1,4,320).
route(l4,l2,tr2,6,330).
route(l4,l3,tr1,8,640).
route(l5,l3,tr1,5,400).
route(l5,l3,tr2,1,55).
route(l5,l4,tr1,5,400).
route(l5,l4,tr2,9,495).
route(l5,l6,tr2,7,385).
route(l6,l1,tr1,5,400).
route(l6,l1,tr2,2,110).
route(l6,l3,tr1,1,80).
route(l6,l3,tr2,5,275).
route(l6,l4,tr1,2,160).
route(l6,l4,tr2,4,220).
route(l6,l5,tr1,3,240).
