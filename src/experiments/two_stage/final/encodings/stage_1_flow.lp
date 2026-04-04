#const cap_size_divide = 1.
#const max_freq = 50.
#const weight = 1.


% ── Supply / Demand ──────────────────────────────────────────────────────

totalSupply(P, Max) :- Max = #sum {V,L : demandOffer(P,L,V), V > 0}, part(P).
totalFlow(P,Max) :- Max = #sum{V,L: demandOffer(P,L,V), V >0 }, part(P). 

hasDemand(P, L) :- demandOffer(P, L, V), V < 0.
hasOffer(P, L)  :- demandOffer(P, L, V), V > 0.

demand(P, L, Val * -1) :- demandOffer(P, L, Val), Val < 0.
demand(P, L, 0)        :- part(P), location(L), not hasDemand(P, L).

offer(P, L, Val) :- demandOffer(P, L, Val), Val > 0.
offer(P, L, 0)   :- part(P), location(L), not hasOffer(P, L).

% required to ensure that the total demand matches the total supply.
requiredNet(P, L, Net) :- demand(P,L,D), offer(P,L,O), Net = D - O.
requiredNet(P, L, 0)   :- not demand(P,L,_), not offer(P,L,_), location(L), part(P).




% ── Valid flow arcs ──────────────────────────────────────────────────────

%validFromNode(L) :- demandOffer(_, L, M), M > 0.
%validToNode(L)   :- demandOffer(_, L, M), M < 0.


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


% freq(1..MAX) :- totalFlow(
freq(1..max_freq). 

1 { routeFreq(From, To, TR, Freq, C*Freq) :
        freq(Freq), tRCapSmall(TR, C) } 1 :-
    activeFlow(From, To, TR, _).


% Aggregate capacity with 70% headroom to ensure Stage 2 bin-packing feasibility.
% Without headroom, aggregate-feasible loads may not distribute into integer trips.
% 10 * volume <= 7 * totalCap  ↔  volume <= 0.7 * totalCap
&sum { 10 * S*load(F, T, TR, P) :
        possibleFlow(F, T, TR, P), partSizeSmall(P, S) } <= 7 * TotalCap :-
    routeFreq(F, T, TR, Freq, TotalCap).


maxItemsPerTrip(TR, P, Cap/S) :-
    transportCapacity(TR, Cap), partSize(P, S), S > 0, Cap >= S.

&sum { load(F,T,TR,P) : possibleFlow(F,T,TR,P) } <= Max*Freq :-
    routeFreq(F,T,TR,Freq,_), possibleFlow(F,T,TR,P),
    maxItemsPerTrip(TR, P, Max).

% Underpacking constraint removed: conflicts with 70% headroom at freq >= 4.
% The headroom constraint already prevents wasteful overloading.


&sum { load(F, T, TR, P) : possibleFlow(F, T, TR, P) } = arcLoad(F, T, P) :-
    activeFlow(F, T, _, P), part(P).


transportResourcesAvailable(F, T, P, N) :-
    activeFlow(F, T, _, P),
    N = #count { TR : possibleFlow(F, T, TR, P) }.


&dom { 0..Max } = maxTRLoad(F, T, P) :-
    transportResourcesAvailable(F, T, P, N), N > 1,
    totalSupply(P, Max).

% maxTRLoad must be at least the load on each individual TR
&sum { maxTRLoad(F, T, P); -load(F, T, TR, P) } >= 0 :-
    possibleFlow(F, T, TR, P),
    transportResourcesAvailable(F, T, P, N), N > 1.

% A TR is dominant if it carries more than the fair share
dominantTR(F, T, P) :-
    transportResourcesAvailable(F, T, P, N), N > 1,
    &sum { N*maxTRLoad(F, T, P); -arcLoad(F, T, P) } > 0.

_transCost(From, To, TR, C*Freq) :-
    routeFreq(From, To, TR, Freq, _),
    route(From, To, TR, _, C).

:~ dominantTR(F, T, P). [weight@1, div, F, T, P]
:~ _transCost(F, T, TR, V). [V@1, trans, F, T, TR]


#show.
&show { load/4 }.
#show dominantTR/3.
#show routeFreq/5.
#show maxItemsPerTrip/3.
#show requiredNet/3.
#show tRCapSmall/2.
#show partSizeSmall/2.
#show totalSupply/2.

#show activeFlow/4.