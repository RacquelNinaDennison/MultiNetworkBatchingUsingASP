% Sparse benchmark instance
% Generated with seed=9002 locations=6 parts=3 transports=2 routes=31

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,14).
transportCO2(tr1,24).
transportCost(tr1,52).
transportSpeed(tr1,4).
transportCapacity(tr2,20).
transportCO2(tr2,39).
transportCost(tr2,70).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,2).
partVal(p1,165).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,833).
partTR(p2,tr1).
part(p3).
partSize(p3,4).
partVal(p3,655).
partTR(p3,tr1).

% ---- demand and supply ----
demandOffer(p1,l1,14).
demandOffer(p2,l1,11).
demandOffer(p3,l1,5).
demandOffer(p1,l4,-18).
demandOffer(p2,l4,-3).
demandOffer(p3,l4,-9).
demandOffer(p1,l5,16).
demandOffer(p2,l5,19).
demandOffer(p3,l5,25).
demandOffer(p1,l6,-12).
demandOffer(p2,l6,-27).
demandOffer(p3,l6,-21).

% ---- routes ----
route(l1,l2,tr1,4,208).
route(l1,l2,tr2,2,140).
route(l1,l3,tr1,6,312).
route(l1,l3,tr2,6,420).
route(l1,l4,tr1,6,312).
route(l1,l4,tr2,1,70).
route(l2,l3,tr1,1,52).
route(l2,l3,tr2,1,70).
route(l2,l5,tr1,1,52).
route(l2,l5,tr2,8,560).
route(l2,l6,tr1,2,104).
route(l2,l6,tr2,7,490).
route(l3,l4,tr1,6,312).
route(l3,l6,tr1,6,312).
route(l3,l6,tr2,8,560).
route(l4,l2,tr1,7,364).
route(l4,l2,tr2,3,210).
route(l4,l6,tr1,6,312).
route(l4,l6,tr2,6,420).
route(l5,l2,tr1,7,364).
route(l5,l2,tr2,1,70).
route(l5,l3,tr2,10,700).
route(l5,l4,tr1,5,260).
route(l5,l6,tr1,5,260).
route(l5,l6,tr2,2,140).
route(l6,l1,tr2,3,210).
route(l6,l2,tr2,10,700).
route(l6,l4,tr1,7,364).
route(l6,l4,tr2,9,630).
route(l6,l5,tr1,7,364).
route(l6,l5,tr2,3,210).
