#const cap_size_divide = 100.
#const max_freq = 30.


% ── Supply / Demand ──────────────────────────────────────────────────────

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0)   :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).


% ── Valid flow arcs ──────────────────────────────────────────────────────

validFromNode(L) :- demandOffer(_, L, M), M > 0.
validToNode(L)   :- demandOffer(_, L, M), M < 0.

% A part can only flow on a transport if a single unit fits in one trip.
% this allows us to prune down the space 
possibleFlow(From, To, TR, P) :-
    route(From, To, TR, _, _), part(P),
    partSize(P, S), transportCapacity(TR, C), S <= C.


% ── Capacity scaling - mostly used for big paper instances 

tRCapSmall(TR, Cap)  :- transportCapacity(TR, CapB), Cap = CapB / cap_size_divide.
partSizeSmall(P, S)  :- partSize(P, SB), S = SB / cap_size_divide.


% ── Flow variables 

&dom { 0..Max } = load(From, To, TR, P) :-
    possibleFlow(From, To, TR, P), totalSupply(P, Max).

&sum { load(From, L, TR, P) : possibleFlow(From, L, TR, P) } = flow_in(P, L) :-
    location(L), part(P).

&sum { load(L, To, TR, P) : possibleFlow(L, To, TR, P) } = flow_out(P, L) :-
    location(L), part(P).

% Flow conservation: inflow − outflow = net demand at each node
&sum { flow_in(P,L); -flow_out(P,L) } = Net :- requiredNet(P, L, Net).

% Detect active arcs 
activeFlow(From, To, TR, P) :-
    &sum { load(From, To, TR, P) : possibleFlow(From, To, TR, P) } > 0,
    possibleFlow(From, To, TR, P).



freq(1..max_freq).

1 { routeFreq(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).

&sum { S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } <= TotalCap :-
    routeFreq(F, T, TR, Freq, TotalCap).


maxItemsPerTrip(TR, P, Cap/S) :-
    transportCapacity(TR, Cap), partSize(P, S), S > 0, Cap >= S.

&sum { load(F,T,TR,P) : possibleFlow(F,T,TR,P) } <= Max*Freq :-
    routeFreq(F,T,TR,Freq,_), possibleFlow(F,T,TR,P),
    maxItemsPerTrip(TR, P, Max).

:- &sum { S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } < Minus1,
    routeFreq(F, T, TR, Freq, TotalCap),
    tRCapSmall(TR, C), Minus1 = TotalCap - C, Freq > 1.



_transCost(From,To,TR, C*Freq) :-
    routeFreq(From,To,TR,Freq,_), route(From,To,TR,_,C).


% back up features for the load 
arcHasLoad(F, T, TR, P) :-
    &sum { load(F, T, TR, P) } > 0,
    possibleFlow(F, T, TR, P).


transportResourcesAvaliable(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : possibleFlow(F, T, TR, P) }.

transportResourcesUsed(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : arcHasLoad(F, T, TR, P) }.


underDiversified(F, T, P) :-
    transportResourcesUsed(F, T, P, U),
    transportResourcesAvaliable(F, T, P, A),
    A > 1, U < A.

:~ underDiversified(F, T, P). [5@1, F, T, P]
:~ _transCost(F,T,TR,V). [V@1, F, T, TR, V]


#show.
&show { load/4 }.
#show routeFreq/5.


