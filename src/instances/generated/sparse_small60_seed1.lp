% Sparse benchmark instance
% Generated with seed=9000 locations=6 parts=3 transports=2 routes=32

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,15).
transportCO2(tr1,49).
transportCost(tr1,68).
transportSpeed(tr1,5).
transportCapacity(tr2,15).
transportCO2(tr2,24).
transportCost(tr2,32).
transportSpeed(tr2,5).

% ---- parts ----
part(p1).
partSize(p1,2).
partVal(p1,565).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,172).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,1).
partVal(p3,284).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,20).
demandOffer(p2,l1,12).
demandOffer(p3,l1,17).
demandOffer(p1,l2,10).
demandOffer(p2,l2,18).
demandOffer(p3,l2,13).
demandOffer(p1,l4,-16).
demandOffer(p2,l4,-12).
demandOffer(p3,l4,-19).
demandOffer(p1,l6,-14).
demandOffer(p2,l6,-18).
demandOffer(p3,l6,-11).

% ---- routes ----
route(l1,l3,tr1,9,612).
route(l1,l3,tr2,2,64).
route(l1,l4,tr1,4,272).
route(l1,l4,tr2,8,256).
route(l1,l5,tr1,8,544).
route(l1,l5,tr2,2,64).
route(l1,l6,tr1,10,680).
route(l1,l6,tr2,6,192).
route(l2,l1,tr2,5,160).
route(l2,l3,tr2,9,288).
route(l2,l4,tr1,7,476).
route(l2,l4,tr2,3,96).
route(l2,l5,tr1,5,340).
route(l2,l5,tr2,8,256).
route(l2,l6,tr1,10,680).
route(l2,l6,tr2,10,320).
route(l3,l2,tr1,10,680).
route(l3,l2,tr2,6,192).
route(l3,l4,tr1,1,68).
route(l3,l4,tr2,6,192).
route(l4,l2,tr1,6,408).
route(l4,l2,tr2,5,160).
route(l4,l6,tr1,9,612).
route(l5,l3,tr1,6,408).
route(l5,l3,tr2,1,32).
route(l5,l4,tr1,5,340).
route(l5,l4,tr2,9,288).
route(l5,l6,tr1,10,680).
route(l5,l6,tr2,8,256).
route(l6,l1,tr1,4,272).
route(l6,l3,tr1,10,680).
route(l6,l3,tr2,6,192).
