% Sparse benchmark instance
% Generated with seed=11000 locations=8 parts=3 transports=2 routes=36

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
transportCapacity(tr1,10).
transportCO2(tr1,49).
transportCost(tr1,54).
transportSpeed(tr1,2).
transportCapacity(tr2,18).
transportCO2(tr2,33).
transportCost(tr2,64).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,456).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,351).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,3).
partVal(p3,407).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,9).
demandOffer(p2,l1,18).
demandOffer(p3,l1,11).
demandOffer(p1,l2,21).
demandOffer(p2,l2,12).
demandOffer(p3,l2,19).
demandOffer(p1,l6,-3).
demandOffer(p2,l6,-8).
demandOffer(p3,l6,-1).
demandOffer(p1,l7,-23).
demandOffer(p2,l7,-13).
demandOffer(p3,l7,-16).
demandOffer(p1,l8,-4).
demandOffer(p2,l8,-9).
demandOffer(p3,l8,-13).

% ---- routes ----
route(l1,l3,tr1,4,216).
route(l1,l3,tr2,10,640).
route(l1,l4,tr1,10,540).
route(l1,l4,tr2,6,384).
route(l1,l5,tr1,8,432).
route(l1,l5,tr2,4,256).
route(l2,l3,tr1,5,270).
route(l2,l3,tr2,2,128).
route(l2,l4,tr1,7,378).
route(l2,l4,tr2,10,640).
route(l2,l5,tr1,8,432).
route(l2,l5,tr2,9,576).
route(l2,l7,tr2,1,64).
route(l3,l5,tr1,9,486).
route(l3,l5,tr2,9,576).
route(l3,l6,tr1,8,432).
route(l3,l6,tr2,9,576).
route(l3,l7,tr1,2,108).
route(l3,l7,tr2,10,640).
route(l3,l8,tr1,4,216).
route(l4,l3,tr1,10,540).
route(l4,l3,tr2,2,128).
route(l4,l6,tr1,1,54).
route(l4,l6,tr2,2,128).
route(l4,l7,tr2,4,256).
route(l4,l8,tr1,3,162).
route(l4,l8,tr2,8,512).
route(l5,l3,tr2,4,256).
route(l5,l4,tr1,6,324).
route(l5,l4,tr2,8,512).
route(l5,l6,tr1,1,54).
route(l5,l6,tr2,8,512).
route(l5,l7,tr1,7,378).
route(l5,l7,tr2,5,320).
route(l5,l8,tr1,5,270).
route(l5,l8,tr2,3,192).
