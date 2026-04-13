% Multibatching benchmark instance
% Generated with seed=1002 locations=6 parts=3 transports=2

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,12).
transportCO2(tr1,38).
transportCost(tr1,76).
transportSpeed(tr1,6).
transportCapacity(tr2,20).
transportCO2(tr2,26).
transportCost(tr2,26).
transportSpeed(tr2,3).

% ---- parts ----
part(p1).
partSize(p1,5).
partVal(p1,149).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,531).
partTR(p2,tr1).
part(p3).
partSize(p3,5).
partVal(p3,266).
partTR(p3,tr1).

% ---- demand and supply ----
demandOffer(p1,l1,46).
demandOffer(p2,l1,33).
demandOffer(p3,l1,17).
demandOffer(p2,l2,38).
demandOffer(p3,l2,-13).
demandOffer(p2,l3,4).
demandOffer(p2,l4,27).
demandOffer(p1,l5,-42).
demandOffer(p3,l5,20).
demandOffer(p1,l6,-4).
demandOffer(p3,l6,-24).
demandOffer(p2,l6,-102).

% ---- routes ----
route(l1,l2,tr2,8,208).
route(l1,l2,tr1,1,76).
route(l1,l3,tr1,5,380).
route(l1,l3,tr2,1,26).
route(l1,l4,tr2,4,104).
route(l1,l4,tr1,3,228).
route(l1,l5,tr2,10,260).
route(l1,l5,tr1,2,152).
route(l1,l6,tr2,4,104).
route(l1,l6,tr1,1,76).
route(l2,l1,tr2,1,26).
route(l2,l1,tr1,4,304).
route(l2,l3,tr1,6,456).
route(l2,l3,tr2,7,182).
route(l2,l4,tr1,3,228).
route(l2,l4,tr2,5,130).
route(l2,l5,tr2,7,182).
route(l2,l5,tr1,9,684).
route(l2,l6,tr2,10,260).
route(l2,l6,tr1,7,532).
route(l3,l1,tr2,1,26).
route(l3,l1,tr1,2,152).
route(l3,l2,tr1,10,760).
route(l3,l2,tr2,6,156).
route(l3,l4,tr1,1,76).
route(l3,l4,tr2,9,234).
route(l3,l5,tr1,6,456).
route(l3,l5,tr2,1,26).
route(l3,l6,tr2,6,156).
route(l3,l6,tr1,9,684).
route(l4,l1,tr1,2,152).
route(l4,l1,tr2,7,182).
route(l4,l2,tr2,10,260).
route(l4,l2,tr1,2,152).
route(l4,l3,tr1,2,152).
route(l4,l3,tr2,1,26).
route(l4,l5,tr2,10,260).
route(l4,l5,tr1,7,532).
route(l4,l6,tr1,5,380).
route(l4,l6,tr2,5,130).
route(l5,l1,tr1,8,608).
route(l5,l1,tr2,4,104).
route(l5,l2,tr2,5,130).
route(l5,l2,tr1,3,228).
route(l5,l3,tr2,7,182).
route(l5,l3,tr1,5,380).
route(l5,l4,tr2,6,156).
route(l5,l4,tr1,9,684).
route(l5,l6,tr1,7,532).
route(l5,l6,tr2,8,208).
route(l6,l1,tr2,6,156).
route(l6,l1,tr1,6,456).
route(l6,l2,tr2,8,208).
route(l6,l2,tr1,2,152).
route(l6,l3,tr1,9,684).
route(l6,l3,tr2,2,52).
route(l6,l4,tr2,3,78).
route(l6,l4,tr1,10,760).
route(l6,l5,tr2,3,78).
route(l6,l5,tr1,6,456).
