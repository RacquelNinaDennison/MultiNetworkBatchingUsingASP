% Sparse benchmark instance
% Generated with seed=9001 locations=6 parts=3 transports=2 routes=33

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,10).
transportCO2(tr1,51).
transportCost(tr1,46).
transportSpeed(tr1,6).
transportCapacity(tr2,14).
transportCO2(tr2,31).
transportCost(tr2,34).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,829).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,730).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,3).
partVal(p3,398).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,20).
demandOffer(p2,l1,11).
demandOffer(p3,l1,12).
demandOffer(p1,l4,-11).
demandOffer(p2,l4,-18).
demandOffer(p3,l4,-20).
demandOffer(p1,l5,10).
demandOffer(p2,l5,19).
demandOffer(p3,l5,18).
demandOffer(p1,l6,-19).
demandOffer(p2,l6,-12).
demandOffer(p3,l6,-10).

% ---- routes ----
route(l1,l2,tr1,2,92).
route(l1,l2,tr2,10,340).
route(l1,l5,tr1,4,184).
route(l1,l5,tr2,6,204).
route(l1,l6,tr1,5,230).
route(l1,l6,tr2,5,170).
route(l2,l3,tr1,9,414).
route(l2,l3,tr2,5,170).
route(l2,l4,tr1,7,322).
route(l2,l4,tr2,1,34).
route(l2,l5,tr1,7,322).
route(l2,l5,tr2,10,340).
route(l2,l6,tr1,4,184).
route(l2,l6,tr2,8,272).
route(l3,l2,tr1,1,46).
route(l3,l2,tr2,9,306).
route(l3,l4,tr2,6,204).
route(l3,l5,tr1,9,414).
route(l3,l5,tr2,5,170).
route(l3,l6,tr1,3,138).
route(l3,l6,tr2,5,170).
route(l4,l1,tr2,9,306).
route(l4,l5,tr1,3,138).
route(l4,l5,tr2,3,102).
route(l5,l3,tr1,4,184).
route(l5,l3,tr2,3,102).
route(l5,l4,tr1,3,138).
route(l5,l4,tr2,4,136).
route(l6,l1,tr2,4,136).
route(l6,l3,tr1,4,184).
route(l6,l3,tr2,3,102).
route(l6,l5,tr1,1,46).
route(l6,l5,tr2,3,102).
