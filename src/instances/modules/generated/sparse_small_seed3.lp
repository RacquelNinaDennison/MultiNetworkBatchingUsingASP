% Sparse benchmark instance
% Generated with seed=5002 locations=6 parts=3 transports=2 routes=25

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,20).
transportCO2(tr1,17).
transportCost(tr1,85).
transportSpeed(tr1,8).
transportCapacity(tr2,14).
transportCO2(tr2,15).
transportCost(tr2,84).
transportSpeed(tr2,6).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,560).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,677).
partTR(p2,tr1).
part(p3).
partSize(p3,3).
partVal(p3,355).
partTR(p3,tr1).

% ---- demand and supply ----
demandOffer(p1,l1,-15).
demandOffer(p2,l1,-15).
demandOffer(p3,l1,-19).
demandOffer(p1,l3,16).
demandOffer(p2,l3,11).
demandOffer(p3,l3,15).
demandOffer(p1,l4,-15).
demandOffer(p2,l4,-15).
demandOffer(p3,l4,-11).
demandOffer(p1,l5,14).
demandOffer(p2,l5,19).
demandOffer(p3,l5,15).

% ---- routes ----
route(l1,l6,tr2,5,420).
route(l2,l1,tr1,8,680).
route(l2,l3,tr1,4,340).
route(l2,l3,tr2,7,588).
route(l2,l4,tr2,4,336).
route(l3,l2,tr1,4,340).
route(l3,l2,tr2,4,336).
route(l3,l4,tr1,6,510).
route(l3,l4,tr2,8,672).
route(l3,l6,tr1,4,340).
route(l3,l6,tr2,10,840).
route(l4,l3,tr1,6,510).
route(l4,l3,tr2,7,588).
route(l4,l6,tr1,4,340).
route(l4,l6,tr2,4,336).
route(l5,l1,tr1,2,170).
route(l5,l2,tr1,9,765).
route(l5,l2,tr2,6,504).
route(l5,l3,tr1,9,765).
route(l5,l3,tr2,3,252).
route(l5,l4,tr1,5,425).
route(l5,l4,tr2,9,756).
route(l6,l3,tr1,1,85).
route(l6,l5,tr1,4,340).
route(l6,l5,tr2,6,504).
