% Sparse benchmark instance
% Generated with seed=10001 locations=6 parts=2 transports=2 routes=22

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,15).
transportCO2(tr1,52).
transportCost(tr1,37).
transportSpeed(tr1,7).
transportCapacity(tr2,11).
transportCO2(tr2,41).
transportCost(tr2,56).
transportSpeed(tr2,2).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,574).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,365).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,16).
demandOffer(p2,l1,20).
demandOffer(p1,l2,14).
demandOffer(p2,l2,10).
demandOffer(p1,l5,-16).
demandOffer(p2,l5,-8).
demandOffer(p1,l6,-14).
demandOffer(p2,l6,-22).

% ---- routes ----
route(l1,l3,tr1,8,296).
route(l1,l3,tr2,6,336).
route(l1,l4,tr1,7,259).
route(l1,l4,tr2,1,56).
route(l1,l6,tr1,2,74).
route(l1,l6,tr2,10,560).
route(l2,l3,tr1,9,333).
route(l2,l3,tr2,7,392).
route(l2,l4,tr1,6,222).
route(l2,l4,tr2,2,112).
route(l2,l5,tr1,6,222).
route(l2,l5,tr2,1,56).
route(l2,l6,tr1,4,148).
route(l2,l6,tr2,6,336).
route(l3,l5,tr1,1,37).
route(l3,l5,tr2,8,448).
route(l3,l6,tr1,1,37).
route(l3,l6,tr2,9,504).
route(l4,l5,tr1,8,296).
route(l4,l5,tr2,6,336).
route(l4,l6,tr1,8,296).
route(l4,l6,tr2,2,112).
