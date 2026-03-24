% Multibatching benchmark instance
% Generated with seed=3001 locations=6 parts=3 transports=2

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,15).
transportCO2(tr1,28).
transportCost(tr1,47).
transportSpeed(tr1,7).
transportCapacity(tr2,20).
transportCO2(tr2,55).
transportCost(tr2,41).
transportSpeed(tr2,10).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,928).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,5).
partVal(p2,765).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,4).
partVal(p3,553).
partTR(p3,tr1).

% ---- demand and supply ----
demandOffer(p1,l2,7).
demandOffer(p2,l2,-7).
demandOffer(p1,l3,-8).
demandOffer(p3,l3,-5).
demandOffer(p2,l4,4).
demandOffer(p3,l4,39).
demandOffer(p1,l5,-13).
demandOffer(p2,l5,-3).
demandOffer(p3,l6,-34).
demandOffer(p1,l6,14).
demandOffer(p2,l6,6).

% ---- routes ----
route(l1,l2,tr1,10,470).
route(l1,l2,tr2,10,410).
route(l1,l3,tr2,10,410).
route(l1,l3,tr1,10,470).
route(l1,l4,tr1,3,141).
route(l1,l4,tr2,6,246).
route(l1,l5,tr2,10,410).
route(l1,l5,tr1,9,423).
route(l1,l6,tr2,6,246).
route(l1,l6,tr1,4,188).
route(l2,l1,tr2,3,123).
route(l2,l1,tr1,6,282).
route(l2,l3,tr2,4,164).
route(l2,l3,tr1,2,94).
route(l2,l4,tr1,5,235).
route(l2,l4,tr2,4,164).
route(l2,l5,tr1,4,188).
route(l2,l5,tr2,5,205).
route(l2,l6,tr1,8,376).
route(l2,l6,tr2,8,328).
route(l3,l1,tr2,9,369).
route(l3,l1,tr1,6,282).
route(l3,l2,tr1,4,188).
route(l3,l2,tr2,7,287).
route(l3,l4,tr1,6,282).
route(l3,l4,tr2,6,246).
route(l3,l5,tr2,4,164).
route(l3,l5,tr1,5,235).
route(l3,l6,tr1,9,423).
route(l3,l6,tr2,6,246).
route(l4,l1,tr2,7,287).
route(l4,l1,tr1,7,329).
route(l4,l2,tr1,4,188).
route(l4,l2,tr2,6,246).
route(l4,l3,tr2,10,410).
route(l4,l3,tr1,9,423).
route(l4,l5,tr2,1,41).
route(l4,l5,tr1,8,376).
route(l4,l6,tr1,3,141).
route(l4,l6,tr2,1,41).
route(l5,l1,tr1,3,141).
route(l5,l1,tr2,6,246).
route(l5,l2,tr1,8,376).
route(l5,l2,tr2,1,41).
route(l5,l3,tr2,3,123).
route(l5,l3,tr1,9,423).
route(l5,l4,tr2,2,82).
route(l5,l4,tr1,1,47).
route(l5,l6,tr2,9,369).
route(l5,l6,tr1,1,47).
route(l6,l1,tr2,10,410).
route(l6,l1,tr1,4,188).
route(l6,l2,tr2,1,41).
route(l6,l2,tr1,7,329).
route(l6,l3,tr2,6,246).
route(l6,l3,tr1,9,423).
route(l6,l4,tr2,4,164).
route(l6,l4,tr1,5,235).
route(l6,l5,tr1,10,470).
route(l6,l5,tr2,9,369).
