% Sparse benchmark instance
% Generated with seed=5004 locations=6 parts=3 transports=2 routes=28

% ---- locations ----
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).
location(l6).

% ---- transport resources ----
transportCapacity(tr1,15).
transportCO2(tr1,52).
transportCost(tr1,51).
transportSpeed(tr1,5).
transportCapacity(tr2,14).
transportCO2(tr2,23).
transportCost(tr2,68).
transportSpeed(tr2,4).

% ---- parts ----
part(p1).
partSize(p1,1).
partVal(p1,309).
partTR(p1,tr1).
partTR(p1,tr2).
part(p2).
partSize(p2,2).
partVal(p2,185).
partTR(p2,tr1).
part(p3).
partSize(p3,1).
partVal(p3,419).
partTR(p3,tr1).
partTR(p3,tr2).

% ---- demand and supply ----
demandOffer(p1,l2,14).
demandOffer(p2,l2,14).
demandOffer(p3,l2,16).
demandOffer(p1,l3,16).
demandOffer(p2,l3,16).
demandOffer(p3,l3,14).
demandOffer(p1,l5,-11).
demandOffer(p2,l5,-14).
demandOffer(p3,l5,-12).
demandOffer(p1,l6,-19).
demandOffer(p2,l6,-16).
demandOffer(p3,l6,-18).

% ---- routes ----
route(l1,l2,tr1,6,306).
route(l1,l2,tr2,2,136).
route(l1,l3,tr1,1,51).
route(l1,l3,tr2,8,544).
route(l1,l5,tr1,5,255).
route(l1,l5,tr2,1,68).
route(l1,l6,tr1,3,153).
route(l2,l1,tr1,8,408).
route(l2,l1,tr2,5,340).
route(l2,l4,tr1,10,510).
route(l2,l4,tr2,4,272).
route(l2,l5,tr1,6,306).
route(l2,l5,tr2,6,408).
route(l2,l6,tr1,8,408).
route(l2,l6,tr2,7,476).
route(l3,l1,tr1,3,153).
route(l3,l1,tr2,4,272).
route(l3,l2,tr1,7,357).
route(l3,l2,tr2,10,680).
route(l3,l6,tr1,9,459).
route(l3,l6,tr2,8,544).
route(l4,l5,tr2,2,136).
route(l5,l3,tr1,5,255).
route(l5,l3,tr2,5,340).
route(l5,l6,tr1,7,357).
route(l5,l6,tr2,1,68).
route(l6,l4,tr1,3,153).
route(l6,l4,tr2,3,204).
