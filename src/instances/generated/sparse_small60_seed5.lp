% Sparse benchmark instance
% Generated with seed=9004 locations=6 parts=3 transports=2 routes=31

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,17).
transportCO2(tr1,15).
transportCost(tr1,59).
transportSpeed(tr1,5).
transportCapacity(tr2,17).
transportCO2(tr2,34).
transportCost(tr2,83).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,118).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,219).
partTR(p2,tr2).
part(p3).
partSize(p3,2).
partVal(p3,490).
partTR(p3,tr1).

% ---- demand and supply ----
demandOffer(p1,l1,-6).
demandOffer(p2,l1,-6).
demandOffer(p3,l1,-20).
demandOffer(p1,l2,12).
demandOffer(p2,l2,1).
demandOffer(p3,l2,7).
demandOffer(p1,l4,18).
demandOffer(p2,l4,29).
demandOffer(p3,l4,23).
demandOffer(p1,l5,-24).
demandOffer(p2,l5,-24).
demandOffer(p3,l5,-10).

% ---- routes ----
route(l1,l6,tr1,9,531).
route(l1,l6,tr2,7,581).
route(l2,l3,tr1,1,59).
route(l2,l3,tr2,5,415).
route(l2,l5,tr2,7,581).
route(l3,l1,tr1,10,590).
route(l3,l1,tr2,9,747).
route(l3,l2,tr1,5,295).
route(l3,l2,tr2,9,747).
route(l3,l5,tr2,1,83).
route(l4,l1,tr1,7,413).
route(l4,l1,tr2,4,332).
route(l4,l2,tr1,3,177).
route(l4,l2,tr2,8,664).
route(l4,l3,tr1,8,472).
route(l4,l3,tr2,9,747).
route(l4,l5,tr2,5,415).
route(l4,l6,tr1,7,413).
route(l4,l6,tr2,8,664).
route(l5,l1,tr1,5,295).
route(l5,l1,tr2,5,415).
route(l5,l3,tr1,5,295).
route(l5,l3,tr2,10,830).
route(l5,l6,tr1,2,118).
route(l6,l1,tr1,9,531).
route(l6,l1,tr2,6,498).
route(l6,l3,tr2,6,498).
route(l6,l4,tr1,6,354).
route(l6,l4,tr2,2,166).
route(l6,l5,tr1,3,177).
route(l6,l5,tr2,10,830).
