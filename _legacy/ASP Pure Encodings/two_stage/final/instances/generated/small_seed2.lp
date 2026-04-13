% Multibatching benchmark instance
% Generated with seed=2001 locations=6 parts=3 transports=2

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,11).
transportCO2(tr1,16).
transportCost(tr1,85).
transportSpeed(tr1,1).
transportCapacity(tr2,10).
transportCO2(tr2,85).
transportCost(tr2,93).
transportSpeed(tr2,6).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,574).
partTR(p1,tr1).
part(p2).
partSize(p2,4).
partVal(p2,187).
partTR(p2,tr1).
part(p3).
partSize(p3,4).
partVal(p3,776).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p2,l1,3).
demandOffer(p1,l2,-18).
demandOffer(p2,l2,-45).
demandOffer(p3,l2,-19).
demandOffer(p1,l3,10).
demandOffer(p2,l3,-19).
demandOffer(p1,l4,-23).
demandOffer(p2,l4,16).
demandOffer(p3,l4,7).
demandOffer(p1,l5,-10).
demandOffer(p3,l5,3).
demandOffer(p1,l6,41).
demandOffer(p3,l6,9).
demandOffer(p2,l6,45).

% ---- routes ----
route(l1,l2,tr1,6,510).
route(l1,l2,tr2,2,186).
route(l1,l3,tr1,1,85).
route(l1,l3,tr2,1,93).
route(l1,l4,tr1,5,425).
route(l1,l4,tr2,9,837).
route(l1,l5,tr1,6,510).
route(l1,l5,tr2,3,279).
route(l1,l6,tr2,9,837).
route(l1,l6,tr1,8,680).
route(l2,l1,tr2,6,558).
route(l2,l1,tr1,4,340).
route(l2,l3,tr1,4,340).
route(l2,l3,tr2,7,651).
route(l2,l4,tr2,3,279).
route(l2,l4,tr1,3,255).
route(l2,l5,tr2,4,372).
route(l2,l5,tr1,4,340).
route(l2,l6,tr2,4,372).
route(l2,l6,tr1,9,765).
route(l3,l1,tr2,1,93).
route(l3,l1,tr1,10,850).
route(l3,l2,tr1,10,850).
route(l3,l2,tr2,2,186).
route(l3,l4,tr1,2,170).
route(l3,l4,tr2,9,837).
route(l3,l5,tr1,6,510).
route(l3,l5,tr2,8,744).
route(l3,l6,tr2,4,372).
route(l3,l6,tr1,6,510).
route(l4,l1,tr2,10,930).
route(l4,l1,tr1,6,510).
route(l4,l2,tr1,4,340).
route(l4,l2,tr2,8,744).
route(l4,l3,tr2,3,279).
route(l4,l3,tr1,4,340).
route(l4,l5,tr2,9,837).
route(l4,l5,tr1,2,170).
route(l4,l6,tr2,4,372).
route(l4,l6,tr1,4,340).
route(l5,l1,tr1,4,340).
route(l5,l1,tr2,7,651).
route(l5,l2,tr2,8,744).
route(l5,l2,tr1,7,595).
route(l5,l3,tr2,4,372).
route(l5,l3,tr1,2,170).
route(l5,l4,tr2,7,651).
route(l5,l4,tr1,6,510).
route(l5,l6,tr1,1,85).
route(l5,l6,tr2,6,558).
route(l6,l1,tr2,7,651).
route(l6,l1,tr1,8,680).
route(l6,l2,tr2,2,186).
route(l6,l2,tr1,2,170).
route(l6,l3,tr1,2,170).
route(l6,l3,tr2,7,651).
route(l6,l4,tr2,10,930).
route(l6,l4,tr1,2,170).
route(l6,l5,tr1,3,255).
route(l6,l5,tr2,10,930).
