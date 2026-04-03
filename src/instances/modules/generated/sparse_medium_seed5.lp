% Sparse benchmark instance
% Generated with seed=6004 locations=8 parts=5 transports=2 routes=37

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
transportCapacity(tr1,18).
transportCO2(tr1,45).
transportCost(tr1,87).
transportSpeed(tr1,8).
transportCapacity(tr2,14).
transportCO2(tr2,46).
transportCost(tr2,81).
transportSpeed(tr2,8).

% ---- parts ----
part(p1).
partSize(p1,3).
partVal(p1,407).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,1).
partVal(p2,786).
partTR(p2,tr1).
partTR(p2,tr2).
part(p3).
partSize(p3,3).
partVal(p3,757).
partTR(p3,tr1).
partTR(p3,tr2).
part(p4).
partSize(p4,3).
partVal(p4,566).
partTR(p4,tr1).
partTR(p4,tr2).
part(p5).
partSize(p5,2).
partVal(p5,271).
partTR(p5,tr1).
partTR(p5,tr2).

% ---- demand and supply ----
demandOffer(p1,l2,-13).
demandOffer(p2,l2,-14).
demandOffer(p3,l2,-20).
demandOffer(p4,l2,-10).
demandOffer(p5,l2,-16).
demandOffer(p1,l3,12).
demandOffer(p2,l3,14).
demandOffer(p3,l3,19).
demandOffer(p4,l3,16).
demandOffer(p5,l3,11).
demandOffer(p1,l5,-8).
demandOffer(p2,l5,-9).
demandOffer(p3,l5,-5).
demandOffer(p4,l5,-10).
demandOffer(p5,l5,-7).
demandOffer(p1,l6,18).
demandOffer(p2,l6,16).
demandOffer(p3,l6,11).
demandOffer(p4,l6,14).
demandOffer(p5,l6,19).
demandOffer(p1,l7,-9).
demandOffer(p2,l7,-7).
demandOffer(p3,l7,-5).
demandOffer(p4,l7,-10).
demandOffer(p5,l7,-7).

% ---- routes ----
route(l1,l4,tr1,7,609).
route(l1,l4,tr2,2,162).
route(l1,l5,tr1,3,261).
route(l1,l5,tr2,6,486).
route(l1,l6,tr1,4,348).
route(l2,l1,tr2,6,486).
route(l2,l4,tr1,4,348).
route(l2,l4,tr2,7,567).
route(l3,l4,tr1,9,783).
route(l3,l4,tr2,5,405).
route(l3,l7,tr1,9,783).
route(l3,l7,tr2,4,324).
route(l4,l2,tr1,7,609).
route(l4,l2,tr2,10,810).
route(l4,l3,tr2,5,405).
route(l4,l5,tr1,3,261).
route(l4,l5,tr2,9,729).
route(l4,l7,tr1,9,783).
route(l4,l7,tr2,4,324).
route(l5,l4,tr1,4,348).
route(l5,l4,tr2,8,648).
route(l5,l6,tr1,5,435).
route(l5,l6,tr2,1,81).
route(l6,l3,tr1,3,261).
route(l6,l3,tr2,6,486).
route(l6,l7,tr2,9,729).
route(l6,l8,tr2,8,648).
route(l7,l1,tr1,7,609).
route(l7,l1,tr2,4,324).
route(l7,l3,tr1,8,696).
route(l7,l3,tr2,1,81).
route(l7,l4,tr1,1,87).
route(l7,l4,tr2,8,648).
route(l8,l2,tr1,8,696).
route(l8,l5,tr2,5,405).
route(l8,l7,tr1,4,348).
route(l8,l7,tr2,2,162).
