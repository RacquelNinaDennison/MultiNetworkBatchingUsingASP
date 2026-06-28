% Sparse benchmark instance
% Generated with seed=10004 locations=6 parts=2 transports=2 routes=21

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,19).
transportCO2(tr1,61).
transportCost(tr1,70).
transportSpeed(tr1,4).
transportCapacity(tr2,17).
transportCO2(tr2,48).
transportCost(tr2,35).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,688).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,853).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,15).
demandOffer(p2,l1,5).
demandOffer(p1,l2,15).
demandOffer(p2,l2,25).
demandOffer(p1,l5,-5).
demandOffer(p2,l5,-26).
demandOffer(p1,l6,-25).
demandOffer(p2,l6,-4).

% ---- routes ----
route(l1,l3,tr1,3,210).
route(l1,l3,tr2,4,140).
route(l1,l4,tr1,4,280).
route(l1,l4,tr2,6,210).
route(l1,l6,tr1,5,350).
route(l1,l6,tr2,6,210).
route(l2,l3,tr1,4,280).
route(l2,l3,tr2,10,350).
route(l2,l4,tr1,4,280).
route(l2,l4,tr2,5,175).
route(l2,l6,tr1,5,350).
route(l2,l6,tr2,5,175).
route(l3,l5,tr1,3,210).
route(l3,l5,tr2,8,280).
route(l3,l6,tr1,10,700).
route(l3,l6,tr2,7,245).
route(l4,l3,tr1,2,140).
route(l4,l3,tr2,7,245).
route(l4,l5,tr1,3,210).
route(l4,l5,tr2,10,350).
route(l4,l6,tr1,4,280).
