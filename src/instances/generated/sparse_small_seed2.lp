% Sparse benchmark instance
% Generated with seed=5001 locations=6 parts=3 transports=2 routes=28

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,19).
transportCO2(tr1,62).
transportCost(tr1,70).
transportSpeed(tr1,6).
transportCapacity(tr2,14).
transportCO2(tr2,64).
transportCost(tr2,57).
transportSpeed(tr2,6).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,152).
partTR(p1,tr1).
part(p2).
partSize(p2,4).
partVal(p2,575).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,2).
partVal(p3,493).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,26).
demandOffer(p2,l1,1).
demandOffer(p3,l1,25).
demandOffer(p1,l4,4).
demandOffer(p2,l4,29).
demandOffer(p3,l4,5).
demandOffer(p1,l5,-26).
demandOffer(p2,l5,-10).
demandOffer(p3,l5,-18).
demandOffer(p1,l6,-4).
demandOffer(p2,l6,-20).
demandOffer(p3,l6,-12).

% ---- routes ----
route(l1,l2,tr1,3,210).
route(l1,l2,tr2,1,57).
route(l1,l5,tr1,6,420).
route(l1,l5,tr2,5,285).
route(l1,l6,tr1,8,560).
route(l1,l6,tr2,2,114).
route(l2,l3,tr1,9,630).
route(l2,l3,tr2,3,171).
route(l2,l5,tr1,10,700).
route(l2,l5,tr2,2,114).
route(l2,l6,tr1,6,420).
route(l2,l6,tr2,6,342).
route(l3,l4,tr1,5,350).
route(l3,l4,tr2,6,342).
route(l3,l6,tr2,4,228).
route(l4,l1,tr1,1,70).
route(l4,l1,tr2,5,285).
route(l4,l2,tr2,4,228).
route(l4,l3,tr1,6,420).
route(l4,l3,tr2,7,399).
route(l4,l5,tr1,1,70).
route(l4,l5,tr2,3,171).
route(l4,l6,tr1,7,490).
route(l4,l6,tr2,10,570).
route(l5,l1,tr1,5,350).
route(l5,l1,tr2,7,399).
route(l5,l4,tr1,4,280).
route(l5,l4,tr2,9,513).
