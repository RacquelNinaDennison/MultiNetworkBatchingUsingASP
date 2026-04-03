% Sparse benchmark instance
% Generated with seed=9003 locations=6 parts=3 transports=2 routes=32

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,19).
transportCO2(tr1,16).
transportCost(tr1,88).
transportSpeed(tr1,6).
transportCapacity(tr2,20).
transportCO2(tr2,18).
transportCost(tr2,80).
transportSpeed(tr2,4).

% ---- parts ----
part(p1).
partSize(p1,2).
partVal(p1,683).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,410).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,3).
partVal(p3,576).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l2,12).
demandOffer(p2,l2,16).
demandOffer(p3,l2,15).
demandOffer(p1,l3,-12).
demandOffer(p2,l3,-10).
demandOffer(p3,l3,-10).
demandOffer(p1,l4,18).
demandOffer(p2,l4,14).
demandOffer(p3,l4,15).
demandOffer(p1,l6,-18).
demandOffer(p2,l6,-20).
demandOffer(p3,l6,-20).

% ---- routes ----
route(l1,l3,tr1,6,528).
route(l1,l3,tr2,9,720).
route(l1,l5,tr1,9,792).
route(l1,l5,tr2,9,720).
route(l1,l6,tr2,1,80).
route(l2,l1,tr1,3,264).
route(l2,l1,tr2,2,160).
route(l2,l3,tr1,8,704).
route(l2,l4,tr1,7,616).
route(l2,l4,tr2,10,800).
route(l2,l5,tr1,3,264).
route(l2,l5,tr2,4,320).
route(l3,l2,tr1,4,352).
route(l3,l5,tr1,2,176).
route(l3,l5,tr2,4,320).
route(l3,l6,tr1,3,264).
route(l3,l6,tr2,6,480).
route(l4,l2,tr1,1,88).
route(l4,l2,tr2,1,80).
route(l4,l3,tr1,9,792).
route(l4,l3,tr2,2,160).
route(l4,l5,tr1,4,352).
route(l4,l5,tr2,10,800).
route(l4,l6,tr1,2,176).
route(l4,l6,tr2,9,720).
route(l5,l3,tr1,2,176).
route(l5,l3,tr2,8,640).
route(l5,l6,tr1,7,616).
route(l5,l6,tr2,5,400).
route(l6,l4,tr1,7,616).
route(l6,l4,tr2,5,400).
route(l6,l5,tr1,1,88).
