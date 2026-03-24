% Multibatching benchmark instance
% Generated with seed=4001 locations=6 parts=3 transports=2

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,13).
transportCO2(tr1,64).
transportCost(tr1,63).
transportSpeed(tr1,7).
transportCapacity(tr2,17).
transportCO2(tr2,99).
transportCost(tr2,72).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,5).
partVal(p1,557).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,817).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,1).
partVal(p3,180).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,26).
demandOffer(p2,l1,-6).
demandOffer(p1,l2,-46).
demandOffer(p1,l3,-6).
demandOffer(p2,l3,-48).
demandOffer(p1,l4,-4).
demandOffer(p2,l4,25).
demandOffer(p3,l4,49).
demandOffer(p1,l5,32).
demandOffer(p3,l5,42).
demandOffer(p1,l6,-2).
demandOffer(p3,l6,-91).
demandOffer(p2,l6,29).

% ---- routes ----
route(l1,l2,tr2,1,72).
route(l1,l2,tr1,10,630).
route(l1,l3,tr2,6,432).
route(l1,l3,tr1,1,63).
route(l1,l4,tr2,2,144).
route(l1,l4,tr1,9,567).
route(l1,l5,tr2,9,648).
route(l1,l5,tr1,10,630).
route(l1,l6,tr2,1,72).
route(l1,l6,tr1,3,189).
route(l2,l1,tr1,3,189).
route(l2,l1,tr2,10,720).
route(l2,l3,tr2,4,288).
route(l2,l3,tr1,3,189).
route(l2,l4,tr2,2,144).
route(l2,l4,tr1,8,504).
route(l2,l5,tr2,7,504).
route(l2,l5,tr1,6,378).
route(l2,l6,tr2,7,504).
route(l2,l6,tr1,2,126).
route(l3,l1,tr2,9,648).
route(l3,l1,tr1,4,252).
route(l3,l2,tr1,10,630).
route(l3,l2,tr2,9,648).
route(l3,l4,tr2,3,216).
route(l3,l4,tr1,3,189).
route(l3,l5,tr1,5,315).
route(l3,l5,tr2,6,432).
route(l3,l6,tr2,8,576).
route(l3,l6,tr1,10,630).
route(l4,l1,tr1,4,252).
route(l4,l1,tr2,4,288).
route(l4,l2,tr1,10,630).
route(l4,l2,tr2,7,504).
route(l4,l3,tr1,1,63).
route(l4,l3,tr2,9,648).
route(l4,l5,tr1,9,567).
route(l4,l5,tr2,3,216).
route(l4,l6,tr1,9,567).
route(l4,l6,tr2,9,648).
route(l5,l1,tr2,7,504).
route(l5,l1,tr1,3,189).
route(l5,l2,tr1,6,378).
route(l5,l2,tr2,4,288).
route(l5,l3,tr1,10,630).
route(l5,l3,tr2,6,432).
route(l5,l4,tr1,10,630).
route(l5,l4,tr2,9,648).
route(l5,l6,tr1,8,504).
route(l5,l6,tr2,7,504).
route(l6,l1,tr1,7,441).
route(l6,l1,tr2,4,288).
route(l6,l2,tr2,1,72).
route(l6,l2,tr1,5,315).
route(l6,l3,tr1,2,126).
route(l6,l3,tr2,10,720).
route(l6,l4,tr1,8,504).
route(l6,l4,tr2,8,576).
route(l6,l5,tr2,10,720).
route(l6,l5,tr1,5,315).
