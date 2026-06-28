% Sparse benchmark instance
% Generated with seed=10000 locations=6 parts=2 transports=2 routes=17

% ---- locations ----


numFlow(0..20).
numParts(0..5).
numFreq(0..20).
bins(0).

location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,19).
transportCO2(tr1,22).
transportCost(tr1,32).
transportSpeed(tr1,2).
transportCapacity(tr2,14).
transportCO2(tr2,60).
transportCost(tr2,74).
transportSpeed(tr2,7).

% ---- parts ----
part(p1).
partSize(p1,4).
partVal(p1,302).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,3).
partVal(p2,816).
partTR(p2,tr1).
partTR(p2,tr2).

% ---- demand and supply ----
demandOffer(p1,l1,14).
demandOffer(p2,l1,11).
demandOffer(p1,l2,16).
demandOffer(p2,l2,19).
demandOffer(p1,l5,-18).
demandOffer(p2,l5,-21).
demandOffer(p1,l6,-12).
demandOffer(p2,l6,-9).

% ---- routes ----
route(l1,l3,tr1,5,160).
route(l1,l3,tr2,1,74).
route(l1,l4,tr1,4,128).
route(l1,l4,tr2,1,74).
route(l1,l5,tr1,10,320).
route(l1,l5,tr2,5,370).
route(l2,l3,tr1,9,288).
route(l2,l3,tr2,3,222).
route(l2,l4,tr1,2,64).
route(l2,l4,tr2,6,444).
route(l3,l5,tr1,1,32).
route(l3,l6,tr1,8,256).
route(l3,l6,tr2,7,518).
route(l4,l5,tr1,7,224).
route(l4,l5,tr2,9,666).
route(l4,l6,tr1,8,256).
route(l4,l6,tr2,10,740).
