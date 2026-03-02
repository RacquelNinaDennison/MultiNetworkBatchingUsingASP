netdemandSupply(P,L,0) :- not demandOffer(P,L,_), part(P), location(L).
netdemandSupply(P,L,D) :- demandOffer(P,L,D).

is_consumer(P,L) :- demandOffer(P,L,D), D < 0.
is_producer(P,L) :- demandOffer(P,L,D), D > 0.

% ---------- feasible pack values only ----------
feasiblePackN(P,TR,N) :-
    numParts(N),
    partSize(P,S),
    transportCapacity(TR,C),
    N*S <= C.

% ---------- choose pack per part per bin per route ----------
1 { pack(N,P,ID,From,To,TR) : feasiblePackN(P,TR,N) } 1 :-
    route(From,To,TR,_,_),
    bins(ID),
    part(P).

% ---------- choose frequency per bin per route ----------
1 { freq(ID,From,To,TR,F) : numFreq(F) } 1 :-
    route(From,To,TR,_,_),
    bins(ID).

% ---------- no useless packing on impossible arcs ----------
:- pack(N,P,ID,From,To,TR), N > 0, is_consumer(P,From).
:- pack(N,P,ID,From,To,TR), N > 0, is_producer(P,To).

% ---------- if frequency is zero, the bin must be empty ----------
:- freq(ID,From,To,TR,0), pack(N,P,ID,From,To,TR), N > 0.

% ---------- if frequency is positive, bin must carry something ----------
has_load(ID,From,To,TR) :-
    pack(N,P,ID,From,To,TR), N > 0.

:- freq(ID,From,To,TR,F), F > 0, not has_load(ID,From,To,TR).

% ---------- support each consumer directly by incoming transport ----------
incoming_support(P,L,Total) :-
    is_consumer(P,L),
    Total = #sum {
        N*F, ID,From,TR :
            pack(N,P,ID,From,L,TR),
            freq(ID,From,L,TR,F)
    }.

:- demandOffer(P,L,D), D < 0,
   incoming_support(P,L,Total),
   Total < -D.

% ---------- symmetry breaking: lower bins first ----------
used_bin(ID,From,To,TR) :-
    freq(ID,From,To,TR,F), F > 0.

:- used_bin(ID2,From,To,TR),
   bins(ID1), ID1 < ID2,
   not used_bin(ID1,From,To,TR).

% ---------- objective ----------
#minimize {
    F*Distance*Cost@1, ID,From,To,TR :
        freq(ID,From,To,TR,F),
        route(From,To,TR,Distance,Cost)
}.

% ---------- output skeleton ----------
active_route(From,To,TR) :- freq(ID,From,To,TR,F), F > 0.
touched_link(From,To)    :- active_route(From,To,TR).
touched_node(L)          :- active_route(L,_,_).
touched_node(L)          :- active_route(_,L,_).

#show active_route/3.
#show touched_link/2.
#show touched_node/1.
#show freq/5.