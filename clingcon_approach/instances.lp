%%% Locations %%%
location(l1; l2; l3; l4; l5; l6). 

%%% Transport Resources %%%
transportResource(tr1; tr2).


transportCapacity(tr1, 10).
transportCapacity(tr2, 15).


transportCO2(tr1, 60).
transportCO2(tr2, 45).


transportCost(tr1, 56).
transportCost(tr2, 43). 


transportSpeed(tr1, 3).  
transportSpeed(tr2, 2).

part(p1). 


partSize(p1, 4).
partSize(p2, 3).


partVal(p1, 1000).

demandOffer(p1, l1, 15).
demandOffer(p1, l2, 20).
demandOffer(p1, l5, -15).
demandOffer(p1, l6, -20).


route(l1,l2,tr1,1,56).  
route(l1,l2,tr2,2,86).   


route(l1,l3,tr1,3,168). 
route(l1,l3,tr2,4,172).  


route(l1,l4,tr1,4,224).
route(l1,l4,tr2,8,344).


route(l2,l3,tr1,1,56).
route(l2,l3,tr2,2,86).


route(l2,l4,tr1,2,112).
route(l2,l4,tr2,6,258).
route(l2,l6,tr1,2,112).
route(l3,l5,tr1,1,56).
route(l3,l5,tr2,3,129).
route(l3,l6,tr1,1,56).
route(l3,l6,tr2,2,86).
route(l4,l5,tr1,2,112).
route(l4,l5,tr2,4,172).
route(l4,l6,tr1,3,168).
route(l4,l6,tr2,5,215).