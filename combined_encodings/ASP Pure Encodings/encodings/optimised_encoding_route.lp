bins(1..numBins).
#const maxItems = 20. % maximum number of items that can be packed in a single transport resource
#const maxFreq = 20. % maximum frequency of dispatching a packing pattern on a

netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D).

is_consumer(P,L) :- demandOffer(P,L,D), D < 0.
is_producer(P,L) :- demandOffer(P,L,D), D > 0.

% -------- feasible pack values only --------
feasiblePackN(P,TR,N) :-
    numParts(N),
    partSize(P,S),
    transportCapacity(TR,C),
    N*S <= C.

% -------- Flow network --------
1 { flow(From,To,Part,N) : numFlow(N) } 1 :-
    route(From,To,_,_,_),
    part(Part),
    not is_consumer(Part,From),
    not is_producer(Part,To).

:- #sum {
        N,To   : flow(Loc,To,Part,N);
       -N,From : flow(From,Loc,Part,N)
   } != DS,
   netdemandSupply(Part,Loc,DS).

% -------- Pack choices --------
1 { pack(N,P,ID,From,To,TR) : feasiblePackN(P,TR,N) } 1 :-
    route(From,To,TR,_,_),
    bins(ID),
    part(P).

% no positive pack on impossible arcs
:- pack(N,P,ID,From,To,TR), N > 0, is_consumer(P,From).
:- pack(N,P,ID,From,To,TR), N > 0, is_producer(P,To).

% capacity of each bin
:- #sum {
        N*Size :
            pack(N,P,ID,From,To,TR),
            partSize(P,Size)
   } > C,
   transportCapacity(TR,C),
   route(From,To,TR,_,_),
   bins(ID).

% -------- Frequency choices --------
1 { freq(ID,From,To,TR,F) : numFreq(F) } 1 :-
    route(From,To,TR,_,_),
    bins(ID).

% if frequency is zero, bin must be empty
:- freq(ID,From,To,TR,0),
   pack(N,P,ID,From,To,TR),
   N > 0.

% if frequency is positive, bin must carry something
has_load(ID,From,To,TR) :-
    pack(N,P,ID,From,To,TR),
    N > 0.

:- freq(ID,From,To,TR,F),
   F > 0,
   not has_load(ID,From,To,TR).

% -------- flow support --------
:- #sum {
        N*F, ID :
            pack(N,P,ID,From,To,TR),
            freq(ID,From,To,TR,F)
   } < Value,
   flow(From,To,P,Value),
   Value > 0.

% -------- symmetry breaking --------
used_bin(ID,From,To,TR) :-
    freq(ID,From,To,TR,F), F > 0.

:- used_bin(ID2,From,To,TR),
   bins(ID1), ID1 < ID2,
   not used_bin(ID1,From,To,TR).

% -------- objective --------
#minimize {
    F*Distance*Cost@1, ID,From,To,TR :
        freq(ID,From,To,TR,F),
        route(From,To,TR,Distance,Cost)
}.

#show pack/6.
#show freq/5.
#show flow/4.