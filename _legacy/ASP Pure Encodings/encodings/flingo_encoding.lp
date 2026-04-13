#const maxPack  = 5.
#const maxFreq  = 20.
netSD(P,L,0)  :- not demandOffer(P,L,_), part(P), location(L).
netSD(P,L,D)  :- demandOffer(P,L,D).
num(0..maxPack).
bin_id(1..numBins).


1 { pack(P, ID, From, To, TR, N) : num(N) } 1 :-
    route(From,To,TR,_,_), bin_id(ID), part(P).


:- #sum{ N*Size,P : pack(P,ID,From,To,TR,N), partSize(P,Size) } > C,
   transportCapacity(TR,C), route(From,To,TR,_,_), bin_id(ID).


active_bin(ID, From, To, TR) :-
    pack(P, ID, From, To, TR, N), N > 0.


&sum{ freq(ID, From, To, TR) } >= 1 :- active_bin(ID, From, To, TR).
&sum{ freq(ID, From, To, TR) } <= maxFreq :- active_bin(ID, From, To, TR).


&sum{ freq(ID, From, To, TR) } = 0 :-
    route(From,To,TR,_,_), bin_id(ID),
    not active_bin(ID, From, To, TR).


&sum{ N*freq(ID, Loc, To, TR) : 
        pack(P, ID, Loc, To, TR, N), N > 0;
     -N*freq(ID, From, Loc, TR) : 
        pack(P, ID, From, Loc, TR, N), N > 0
    } = DS
    :- netSD(P, Loc, DS), part(P), location(Loc).


:- bin_id(ID1), bin_id(ID2), ID1 < ID2,
   route(From,To,TR,_,_),
   &sum{ freq(ID1,From,To,TR) } = 0,
   &sum{ freq(ID2,From,To,TR) } > 0.


&minimize{ Distance*Cost*freq(ID,From,To,TR) :
    route(From,To,TR,Distance,Cost), bin_id(ID) }.

#show pack/6.