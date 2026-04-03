
location(l1).
location(l2).
location(l3).
location(l4).
location(l5).


transportResource(tr1).
transportResource(tr2).
transportCapacity(tr1, 15).
transportCapacity(tr2, 10).
transportCost(tr1, 40).  
transportCost(tr2, 60). 

% --- Parts ---
part(p1).
part(p2).
partSize(p1, 5).
partSize(p2, 2).
partVal(p1, 500).
partVal(p2, 300).


demandOffer(p1, l1,  10).
demandOffer(p2, l1,  12).
demandOffer(p1, l4, -10).
demandOffer(p2, l4, -12).

% Flow 2: l2 -> l5
demandOffer(p1, l2,   8).
demandOffer(p2, l2,  10).
demandOffer(p1, l5,  -8).
demandOffer(p2, l5, -10).


demandOffer(p1, l3, 0).
demandOffer(p2, l3, 0).


route(l1, l4, tr1, 1,  30).
route(l1, l4, tr2, 1, 120).
route(l2, l5, tr1, 1,  30).
route(l2, l5, tr2, 1, 120).

% Routes via hub l3
route(l1, l3, tr1, 1,  20).
route(l1, l3, tr2, 1,  80).
route(l2, l3, tr1, 1,  20).
route(l2, l3, tr2, 1,  80).
route(l3, l4, tr1, 1,  25).
route(l3, l4, tr2, 1, 100).
route(l3, l5, tr1, 1,  25).
route(l3, l5, tr2, 1, 100).
