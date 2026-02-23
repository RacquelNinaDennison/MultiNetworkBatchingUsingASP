location(l1; l2; l3; l4; l5; l6). 
transportResource(tr1; tr2).

transportCapacity(tr1, 10).
transportCapacity(tr2, 15).

transportCO2(tr1, 60).
transportCO2(tr2, 45).
transportCost(tr1, 56).
transportCost(tr2, 43). 


route(l1,l2,tr1,1,56).   route(l1,l2,tr2,2,86).
route(l1,l3,tr1,3,168).  route(l1,l3,tr2,4,172).
route(l1,l4,tr1,4,224).  route(l1,l4,tr2,8,344).
route(l2,l3,tr1,1,56).   route(l2,l3,tr2,2,86).
route(l2,l4,tr1,2,112).  route(l2,l4,tr2,6,258).
route(l2,l6,tr1,2,112).  route(l3,l5,tr1,1,56).
route(l3,l5,tr2,3,129).  route(l3,l6,tr1,1,56).
route(l3,l6,tr2,2,86).   route(l4,l5,tr1,2,112).
route(l4,l5,tr2,4,172).  route(l4,l6,tr1,3,168).
route(l4,l6,tr2,5,215).


part(p1).
part(p2).
partSize(p1, 4). 
partSize(p2, 3).


demandOffer(p1, l1, 15). demandOffer(p1, l2, 20).
demandOffer(p1, l5, -15). demandOffer(p1, l6, -20).
demandOffer(p2, l1, 40). demandOffer(p2, l2, -10).
demandOffer(p2, l5, -20). demandOffer(p2, l6, -10).

netdemandSupply(P,L,D) :- demandOffer(P,L,D).
netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).


numFlow(1..20).
{ flow(F,T,P,N) : numFlow(N) } :- route(F,T,_,_,_), part(P).


:- #sum{ N,T : flow(L,T,P,N); -N,F : flow(F,L,P,N) } != DS, netdemandSupply(P,L,DS).
:- flow(F,T,P,N1), flow(F,T,P,N2), N1 != N2.

packingId(0..1). 
numParts(0..5).
numFreq(1..20).


{ bin_contains(ID, P, N) : numParts(N) } = 1 :- packingId(ID), part(P).
:- bin_contains(ID, P, N1), bin_contains(ID, P, N2), N1 != N2.

bin_unit_weight(ID, W) :- 
    packingId(ID), 
    W = #sum{ N*S,P : bin_contains(ID,P,N), partSize(P,S) }.


{ transportLink(assigned_packings(ID), route(F,T,TR,D,C), Freq) : numFreq(Freq) } :- 
    route(F,T,TR,D,C), packingId(ID).

:- transportLink(A, R, N1), transportLink(A, R, N2), N1 != N2.

:- transportLink(assigned_packings(ID), route(_,_,TR,_,_), _),transportCapacity(TR, Cap),
   #sum{ N*S,P : bin_contains(ID,P,N), partSize(P,S) } > Cap.

:- packingId(ID), packingId(ID+1), 
   bin_unit_weight(ID, W1), bin_unit_weight(ID+1, W2), 
   W1 < W2.

:- packingId(ID), packingId(ID+1), 
   bin_unit_weight(ID, W), bin_unit_weight(ID+1, W), 
   bin_contains(ID, p1, N1), bin_contains(ID+1, p1, N2), 
   N1 < N2.


:- flow(F,T,P,FlowVal), FlowVal > 0,
   Packed = #sum{ N*Freq,ID,TR,D,C : transportLink(assigned_packings(ID), route(F,T,TR,D,C), Freq), 
                                    bin_contains(ID,P,N) },
   Packed < FlowVal.


% :- packingId(ID), not transportLink(assigned_packings(ID), _, _), bin_unit_weight(ID, W), W > 0.

#minimize { Freq * C * D,F,T,TR : transportLink(_, route(F,T,TR,D,C), Freq) }.

#show transportLink/3.
#show bin_contains/3.
#show flow/4.