% Multibatching benchmark instance
% Generated with seed=5001 locations=6 parts=3 transports=2

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,19).
transportCO2(tr1,64).
transportCost(tr1,82).
transportSpeed(tr1,4).
transportCapacity(tr2,19).
transportCO2(tr2,26).
transportCost(tr2,80).
transportSpeed(tr2,2).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,576).
partTR(p1,tr2).
part(p2).
partSize(p2,4).
partVal(p2,946).
partTR(p2,tr2).
part(p3).
partSize(p3,5).
partVal(p3,637).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p2,l1,-22).
demandOffer(p3,l1,1).
demandOffer(p1,l2,-4).
demandOffer(p1,l3,-9).
demandOffer(p2,l3,-18).
demandOffer(p3,l3,48).
demandOffer(p2,l4,27).
demandOffer(p3,l4,25).
demandOffer(p1,l5,-37).
demandOffer(p2,l5,-2).
demandOffer(p3,l5,13).
demandOffer(p2,l6,15).
demandOffer(p3,l6,-87).
demandOffer(p1,l6,50).

% ---- routes ----
route(l1,l2,tr1,5,410).
route(l1,l2,tr2,8,640).
route(l1,l3,tr2,7,560).
route(l1,l3,tr1,6,492).
route(l1,l4,tr2,7,560).
route(l1,l4,tr1,10,820).
route(l1,l5,tr2,8,640).
route(l1,l5,tr1,6,492).
route(l1,l6,tr1,5,410).
route(l1,l6,tr2,8,640).
route(l2,l1,tr1,6,492).
route(l2,l1,tr2,4,320).
route(l2,l3,tr1,7,574).
route(l2,l3,tr2,4,320).
route(l2,l4,tr1,7,574).
route(l2,l4,tr2,1,80).
route(l2,l5,tr1,4,328).
route(l2,l5,tr2,4,320).
route(l2,l6,tr1,4,328).
route(l2,l6,tr2,2,160).
route(l3,l1,tr1,7,574).
route(l3,l1,tr2,4,320).
route(l3,l2,tr2,3,240).
route(l3,l2,tr1,6,492).
route(l3,l4,tr1,7,574).
route(l3,l4,tr2,10,800).
route(l3,l5,tr1,5,410).
route(l3,l5,tr2,7,560).
route(l3,l6,tr2,9,720).
route(l3,l6,tr1,4,328).
route(l4,l1,tr2,5,400).
route(l4,l1,tr1,9,738).
route(l4,l2,tr1,1,82).
route(l4,l2,tr2,3,240).
route(l4,l3,tr1,1,82).
route(l4,l3,tr2,4,320).
route(l4,l5,tr2,5,400).
route(l4,l5,tr1,1,82).
route(l4,l6,tr1,5,410).
route(l4,l6,tr2,2,160).
route(l5,l1,tr1,4,328).
route(l5,l1,tr2,2,160).
route(l5,l2,tr2,6,480).
route(l5,l2,tr1,10,820).
route(l5,l3,tr1,6,492).
route(l5,l3,tr2,4,320).
route(l5,l4,tr1,5,410).
route(l5,l4,tr2,4,320).
route(l5,l6,tr2,6,480).
route(l5,l6,tr1,5,410).
route(l6,l1,tr2,4,320).
route(l6,l1,tr1,10,820).
route(l6,l2,tr2,7,560).
route(l6,l2,tr1,9,738).
route(l6,l3,tr1,9,738).
route(l6,l3,tr2,4,320).
route(l6,l4,tr1,5,410).
route(l6,l4,tr2,9,720).
route(l6,l5,tr2,7,560).
route(l6,l5,tr1,10,820).
