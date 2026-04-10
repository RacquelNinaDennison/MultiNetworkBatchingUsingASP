% Sparse benchmark instance
% Generated with seed=11001 locations=8 parts=3 transports=2 routes=45

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).
location(l7).
location(l8).

% ---- transport resources ----
transportCapacity(tr1,13).
transportCO2(tr1,48).
transportCost(tr1,45).
transportSpeed(tr1,4).
transportCapacity(tr2,20).
transportCO2(tr2,22).
transportCost(tr2,60).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,591).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,314).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,2).
partVal(p3,607).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,21).
demandOffer(p2,l1,13).
demandOffer(p3,l1,16).
demandOffer(p1,l2,9).
demandOffer(p2,l2,17).
demandOffer(p3,l2,14).
demandOffer(p1,l6,-11).
demandOffer(p2,l6,-8).
demandOffer(p3,l6,-1).
demandOffer(p1,l7,-4).
demandOffer(p2,l7,-6).
demandOffer(p3,l7,-24).
demandOffer(p1,l8,-15).
demandOffer(p2,l8,-16).
demandOffer(p3,l8,-5).

% ---- routes ----
route(l1,l3,tr1,8,360).
route(l1,l3,tr2,1,60).
route(l1,l4,tr1,9,405).
route(l1,l4,tr2,3,180).
route(l1,l5,tr1,7,315).
route(l1,l5,tr2,8,480).
route(l1,l6,tr1,2,90).
route(l1,l6,tr2,1,60).
route(l1,l7,tr1,1,45).
route(l1,l7,tr2,3,180).
route(l1,l8,tr1,8,360).
route(l1,l8,tr2,7,420).
route(l2,l3,tr1,2,90).
route(l2,l3,tr2,6,360).
route(l2,l4,tr1,1,45).
route(l2,l4,tr2,9,540).
route(l2,l5,tr1,2,90).
route(l2,l5,tr2,3,180).
route(l2,l7,tr1,1,45).
route(l2,l7,tr2,5,300).
route(l3,l4,tr1,6,270).
route(l3,l4,tr2,8,480).
route(l3,l5,tr1,5,225).
route(l3,l5,tr2,3,180).
route(l3,l6,tr1,3,135).
route(l3,l6,tr2,1,60).
route(l3,l7,tr1,4,180).
route(l3,l7,tr2,7,420).
route(l3,l8,tr1,6,270).
route(l3,l8,tr2,8,480).
route(l4,l3,tr1,1,45).
route(l4,l3,tr2,1,60).
route(l4,l6,tr1,7,315).
route(l4,l6,tr2,4,240).
route(l4,l7,tr1,4,180).
route(l4,l8,tr1,9,405).
route(l4,l8,tr2,9,540).
route(l5,l3,tr1,7,315).
route(l5,l3,tr2,8,480).
route(l5,l6,tr1,10,450).
route(l5,l6,tr2,8,480).
route(l5,l7,tr1,6,270).
route(l5,l7,tr2,7,420).
route(l5,l8,tr1,8,360).
route(l5,l8,tr2,4,240).
