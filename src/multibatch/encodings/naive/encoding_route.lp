netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D).

is_consumer(P, L) :- demandOffer(P, L, D), D < 0.
is_producer(P, L) :- demandOffer(P, L, D), D > 0.

numFreq(0..10).

% Flow network
1{ flow(From,To,Part,N) : numFlow(N) }1 :-
    route(From,To,_,_,_),
    part(Part),
    not is_consumer(Part, From),
    not is_producer(Part, To).

:- #sum{ N,To : flow(Loc,To,Part,N);
        -N,From : flow(From,Loc,Part,N) } != DS,
   netdemandSupply(Part,Loc,DS).

{pack(N,P,ID,From,To,TR) : numParts(N)} = 1 :- 
    route(From,To,TR,_,_), bins(ID), part(P).

:- #sum{N*Size, P : pack(N,P,ID,From,To,TR), partSize(P,Size)} > C,
    transportCapacity(TR,C), route(From,To,TR,_,_), bins(ID).

1{freq(ID,From,To,TR,F) : numFreq(F)}1 :- 
    route(From,To,TR,_,_), bins(ID).


:- #sum{N*F, ID, TR : pack(N,P,ID,From,To,TR), N >0 , freq(ID,From,To,TR,F), F > 0} < Value,
    flow(From,To,P,Value), Value > 0.

#minimize{F*Distance*Cost@1,ID,From,To,TR  : 
    freq(ID,From,To,TR,F), 
    route(From,To,TR,Distance,Cost)}.


% totalCost(C) :- C = #sum{ F*Distance*Cost, ID, From, To, TR :
%       freq(ID,From,To,TR,F), route(From,To,TR,Distance,Cost) }.

