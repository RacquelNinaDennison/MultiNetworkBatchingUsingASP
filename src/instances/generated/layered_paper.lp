% Layered paper instance
% 5 locations: 2 supply (l1,l2), 1 hub (l3), 2 demand (l4,l5)
% 2 parts, 2 transport resources
% Structure mirrors the paper's running example

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).

% ---- transport resources ----
transportCapacity(tr1,15).
transportCO2(tr1,60).
transportCost(tr1,56).
transportSpeed(tr1,3).
transportCapacity(tr2,10).
transportCO2(tr2,45).
transportCost(tr2,42).
transportSpeed(tr2,2).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,1000).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,600).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,10).
demandOffer(p2,l1,15).
demandOffer(p1,l2,10).
demandOffer(p2,l2,5).

demandOffer(p1,l4,-12).
demandOffer(p2,l4,-10).
demandOffer(p1,l5,-8).
demandOffer(p2,l5,-10).

% ---- routes ----
% Supply -> Hub (both TRs)
route(l1,l3,tr1,3,168).
route(l1,l3,tr2,4,168).
route(l2,l3,tr1,2,112).
route(l2,l3,tr2,3,126).

% Supply -> Demand direct (skip-connections)
route(l1,l4,tr1,5,280).
route(l1,l4,tr2,6,252).
route(l2,l5,tr1,4,224).

% Hub -> Demand (both TRs)
route(l3,l4,tr1,2,112).
route(l3,l4,tr2,3,126).
route(l3,l5,tr1,1,56).
route(l3,l5,tr2,2,84).
