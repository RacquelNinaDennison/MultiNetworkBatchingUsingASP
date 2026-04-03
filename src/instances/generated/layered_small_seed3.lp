% Sparse benchmark instance
% Generated with seed=10002 locations=6 parts=2 transports=2 routes=17

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,16).
transportCO2(tr1,17).
transportCost(tr1,36).
transportSpeed(tr1,4).
transportCapacity(tr2,13).
transportCO2(tr2,59).
transportCost(tr2,68).
transportSpeed(tr2,2).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,576).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,963).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,12).
demandOffer(p2,l1,13).
demandOffer(p1,l2,18).
demandOffer(p2,l2,17).
demandOffer(p1,l5,-11).
demandOffer(p2,l5,-16).
demandOffer(p1,l6,-19).
demandOffer(p2,l6,-14).

% ---- routes ----
route(l1,l3,tr1,5,180).
route(l1,l3,tr2,1,68).
route(l1,l4,tr1,1,36).
route(l1,l4,tr2,4,272).
route(l1,l6,tr1,10,360).
route(l1,l6,tr2,1,68).
route(l2,l3,tr1,5,180).
route(l2,l3,tr2,8,544).
route(l2,l4,tr2,3,204).
route(l3,l4,tr1,5,180).
route(l3,l5,tr1,8,288).
route(l3,l5,tr2,6,408).
route(l3,l6,tr1,8,288).
route(l3,l6,tr2,8,544).
route(l4,l5,tr1,7,252).
route(l4,l5,tr2,1,68).
route(l4,l6,tr2,3,204).
